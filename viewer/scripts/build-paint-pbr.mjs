import fs from "node:fs/promises";
import path from "node:path";
import { fileURLToPath } from "node:url";
import sharp from "sharp";

const scriptDir = path.dirname(fileURLToPath(import.meta.url));
const viewerDir = path.resolve(scriptDir, "..");
const catalogPath = path.join(viewerDir, "app", "data", "paintCatalog.json");
const destination = path.join(viewerDir, "public", "assets", "paints");
const manifestDir = path.join(viewerDir, "public", "assets", "manifests");
const sourceSize = 2048;
const outputSize = 4096;
// The 4K master is an upscale of the 2048 source; a web-sized variant costs no
// extra detail and cuts decode time + VRAM by ~4x in the real-time viewer.
const webSize = 2048;

const catalog = JSON.parse(await fs.readFile(catalogPath, "utf8"));
await fs.mkdir(destination, { recursive: true });
await fs.mkdir(manifestDir, { recursive: true });

function hash2(x, y, seed) {
  let value = (Math.imul(x, 374761393) + Math.imul(y, 668265263) + Math.imul(seed, 1442695041)) | 0;
  value = Math.imul(value ^ (value >>> 13), 1274126177);
  return ((value ^ (value >>> 16)) >>> 0) / 4294967295;
}

function smooth(value) {
  return value * value * (3 - 2 * value);
}

function clamp(value, minimum, maximum) {
  return Math.max(minimum, Math.min(maximum, value));
}

function parseHex(hex) {
  const value = Number.parseInt(hex.slice(1), 16);
  return [(value >> 16) & 255, (value >> 8) & 255, value & 255];
}

function periodicNoise(x, y, cells, seed) {
  const gx = (x / sourceSize) * cells;
  const gy = (y / sourceSize) * cells;
  const x0 = Math.floor(gx) % cells;
  const y0 = Math.floor(gy) % cells;
  const x1 = (x0 + 1) % cells;
  const y1 = (y0 + 1) % cells;
  const tx = smooth(gx - Math.floor(gx));
  const ty = smooth(gy - Math.floor(gy));
  const a = hash2(x0, y0, seed);
  const b = hash2(x1, y0, seed);
  const c = hash2(x0, y1, seed);
  const d = hash2(x1, y1, seed);
  const top = a + (b - a) * tx;
  const bottom = c + (d - c) * tx;
  return top + (bottom - top) * ty;
}

const height = new Float32Array(sourceSize * sourceSize);
const toneVariation = new Float32Array(sourceSize * sourceSize);
const roughnessVariation = new Float32Array(sourceSize * sourceSize);
let minHeight = Number.POSITIVE_INFINITY;
let maxHeight = Number.NEGATIVE_INFINITY;

for (let y = 0; y < sourceSize; y += 1) {
  for (let x = 0; x < sourceSize; x += 1) {
    // One tile represents one real metre. The separate frequency bands keep
    // the coating readable at room, wall-detail and grazing-light distances.
    const broad = periodicNoise(x, y, 3, 17) * 0.20;
    const roller = periodicNoise(x, y, 14, 29) * 0.27;
    const stipple = periodicNoise(x, y, 68, 43) * 0.34;
    const micro = periodicNoise(x, y, 210, 71) * 0.19;
    const directional = Math.sin(
      (x / sourceSize) * Math.PI * 2 * 19 + periodicNoise(x, y, 7, 97) * 2.2,
    ) * 0.032;
    const value = broad + roller + stipple + micro + directional;
    const index = y * sourceSize + x;
    height[index] = value;
    toneVariation[index] =
      (periodicNoise(x, y, 2, 131) - 0.5) * 0.58
      + (periodicNoise(x, y, 7, 149) - 0.5) * 0.30
      + directional * 1.8;
    roughnessVariation[index] =
      (periodicNoise(x, y, 5, 173) - 0.5) * 0.55
      + (periodicNoise(x, y, 31, 191) - 0.5) * 0.45;
    minHeight = Math.min(minHeight, value);
    maxHeight = Math.max(maxHeight, value);
  }
}

const baseColor = Buffer.alloc(sourceSize * sourceSize * 3);
const normal = Buffer.alloc(sourceSize * sourceSize * 3);
const roughMatte = Buffer.alloc(sourceSize * sourceSize);
const roughEggshell = Buffer.alloc(sourceSize * sourceSize);
const span = Math.max(maxHeight - minHeight, 0.0001);

for (let y = 0; y < sourceSize; y += 1) {
  const ym = (y - 1 + sourceSize) % sourceSize;
  const yp = (y + 1) % sourceSize;
  for (let x = 0; x < sourceSize; x += 1) {
    const xm = (x - 1 + sourceSize) % sourceSize;
    const xp = (x + 1) % sourceSize;
    const index = y * sourceSize + x;
    const normalized = (height[index] - minHeight) / span;
    const fine = hash2(x, y, 113) - 0.5;

    // The map remains neutral so one shared texture can tint all 60 paints,
    // but it is no longer a numerically near-flat white image. The 2-4%
    // multi-scale modulation represents substrate and roller coverage, not dirt.
    const colorValue = Math.max(240, Math.min(255, Math.round(
      249.8 + toneVariation[index] * 13.5 + (normalized - 0.5) * 3.0 + fine * 1.2,
    )));
    baseColor[index * 3] = colorValue;
    baseColor[index * 3 + 1] = colorValue;
    baseColor[index * 3 + 2] = colorValue;

    const dx = height[y * sourceSize + xp] - height[y * sourceSize + xm];
    const dy = height[yp * sourceSize + x] - height[ym * sourceSize + x];
    const normalStrength = 5.4;
    let nx = -dx * normalStrength;
    let ny = -dy * normalStrength;
    let nz = 1;
    const length = Math.hypot(nx, ny, nz);
    nx /= length;
    ny /= length;
    nz /= length;
    normal[index * 3] = Math.round((nx * 0.5 + 0.5) * 255);
    normal[index * 3 + 1] = Math.round((ny * 0.5 + 0.5) * 255);
    normal[index * 3 + 2] = Math.round((nz * 0.5 + 0.5) * 255);

    const relief = normalized - 0.5;
    const roughField = roughnessVariation[index];
    roughMatte[index] = Math.max(201, Math.min(247, Math.round(
      225 + relief * 25 + roughField * 34 + fine * 8,
    )));
    roughEggshell[index] = Math.max(128, Math.min(198, Math.round(
      161 + relief * 31 + roughField * 48 + fine * 11,
    )));
  }
}

async function writeJpeg(buffer, channels, filename, colourspace) {
  let pipeline = sharp(buffer, { raw: { width: sourceSize, height: sourceSize, channels } })
    .resize(outputSize, outputSize, { kernel: sharp.kernel.lanczos3 });
  if (colourspace === "srgb") pipeline = pipeline.toColourspace("srgb");
  await pipeline.jpeg({ quality: 94, chromaSubsampling: "4:4:4", mozjpeg: true }).toFile(path.join(destination, filename));
}

async function writeWebJpeg(buffer, channels, filename, colourspace) {
  let pipeline = sharp(buffer, { raw: { width: sourceSize, height: sourceSize, channels } })
    .resize(webSize, webSize, { kernel: sharp.kernel.lanczos3 });
  if (colourspace === "srgb") pipeline = pipeline.toColourspace("srgb");
  await pipeline.jpeg({ quality: 90, chromaSubsampling: "4:4:4", mozjpeg: true }).toFile(path.join(destination, filename));
}

await Promise.all([
  writeJpeg(baseColor, 3, "paint_micro_basecolor_4k.jpg", "srgb"),
  writeWebJpeg(baseColor, 3, "paint_micro_basecolor_web.jpg", "srgb"),
  writeJpeg(normal, 3, "paint_micro_normal_gl_4k.jpg", "linear"),
  writeWebJpeg(normal, 3, "paint_micro_normal_gl_web.jpg", "linear"),
  writeJpeg(roughMatte, 1, "paint_micro_roughness_matte_4k.jpg", "linear"),
  writeWebJpeg(roughMatte, 1, "paint_micro_roughness_matte_web.jpg", "linear"),
  writeJpeg(roughEggshell, 1, "paint_micro_roughness_eggshell_4k.jpg", "linear"),
  writeWebJpeg(roughEggshell, 1, "paint_micro_roughness_eggshell_web.jpg", "linear"),
]);

async function buildSpecialtyCoating(product, productIndex) {
  const productHeight = new Float32Array(sourceSize * sourceSize);
  const productTone = new Float32Array(sourceSize * sourceSize);
  const productRoughness = new Float32Array(sourceSize * sourceSize);
  const baseRgb = parseHex(product.color_srgb);
  let minimum = Number.POSITIVE_INFINITY;
  let maximum = Number.NEGATIVE_INFINITY;
  const seed = 1000 + productIndex * 137;

  for (let y = 0; y < sourceSize; y += 1) {
    for (let x = 0; x < sourceSize; x += 1) {
      const broad = periodicNoise(x, y, product.coating_system === "clay_plaster" ? 5 : 3, seed + 1) - 0.5;
      const medium = periodicNoise(x, y, product.coating_system === "clay_plaster" ? 24 : 11, seed + 7) - 0.5;
      const fine = periodicNoise(x, y, product.coating_system === "clay_plaster" ? 150 : 74, seed + 13) - 0.5;
      const micro = periodicNoise(x, y, 310, seed + 19) - 0.5;
      let trowel = 0;
      if (product.coating_system === "marmorino") {
        const sweepA = Math.sin((x / sourceSize) * Math.PI * 10 + broad * 4.8);
        const sweepB = Math.sin(((x + y * 0.38) / sourceSize) * Math.PI * 7 - medium * 3.2);
        trowel = sweepA * 0.045 + sweepB * 0.035;
      }
      const index = y * sourceSize + x;
      const reliefWeights = product.coating_system === "clay_plaster"
        ? [0.29, 0.31, 0.27, 0.13]
        : product.coating_system === "marmorino"
          ? [0.45, 0.24, 0.10, 0.05]
          : [0.57, 0.29, 0.09, 0.05];
      const value = broad * reliefWeights[0] + medium * reliefWeights[1]
        + fine * reliefWeights[2] + micro * reliefWeights[3] + trowel;
      productHeight[index] = value;
      productTone[index] = broad * (product.coating_system === "limewash" ? 1.0 : 0.65)
        + medium * 0.42 + trowel * 2.4;
      productRoughness[index] = broad * 0.34 + fine * 0.48 + micro * 0.18;
      minimum = Math.min(minimum, value);
      maximum = Math.max(maximum, value);
    }
  }

  const productBaseColor = Buffer.alloc(sourceSize * sourceSize * 3);
  const productNormal = Buffer.alloc(sourceSize * sourceSize * 3);
  const productRoughnessMap = Buffer.alloc(sourceSize * sourceSize);
  const span = Math.max(0.0001, maximum - minimum);
  const normalStrength = product.coating_system === "clay_plaster" ? 3.4 : product.coating_system === "marmorino" ? 1.65 : 1.9;
  const colourVariation = product.coating_system === "limewash" ? 0.105 : product.coating_system === "clay_plaster" ? 0.075 : 0.055;

  for (let y = 0; y < sourceSize; y += 1) {
    const ym = (y - 1 + sourceSize) % sourceSize;
    const yp = (y + 1) % sourceSize;
    for (let x = 0; x < sourceSize; x += 1) {
      const xm = (x - 1 + sourceSize) % sourceSize;
      const xp = (x + 1) % sourceSize;
      const index = y * sourceSize + x;
      const normalized = (productHeight[index] - minimum) / span;
      const tone = productTone[index] * colourVariation + (normalized - 0.5) * 0.018;
      for (let channel = 0; channel < 3; channel += 1) {
        productBaseColor[index * 3 + channel] = Math.round(clamp(baseRgb[channel] * (1 + tone), 0, 255));
      }
      const dx = productHeight[y * sourceSize + xp] - productHeight[y * sourceSize + xm];
      const dy = productHeight[yp * sourceSize + x] - productHeight[ym * sourceSize + x];
      let nx = -dx * normalStrength;
      let ny = -dy * normalStrength;
      let nz = 1;
      const length = Math.hypot(nx, ny, nz) || 1;
      nx /= length;
      ny /= length;
      nz /= length;
      productNormal[index * 3] = Math.round((nx * 0.5 + 0.5) * 255);
      productNormal[index * 3 + 1] = Math.round((ny * 0.5 + 0.5) * 255);
      productNormal[index * 3 + 2] = Math.round((nz * 0.5 + 0.5) * 255);
      productRoughnessMap[index] = Math.round(clamp(
        product.roughness_mean * 255 + productRoughness[index] * 34,
        product.roughness_range[0] * 255,
        product.roughness_range[1] * 255,
      ));
    }
  }

  const prefix = product.id;
  await Promise.all([
    writeJpeg(productBaseColor, 3, `${prefix}_basecolor_4k.jpg`, "srgb"),
    writeWebJpeg(productBaseColor, 3, `${prefix}_basecolor_web.jpg`, "srgb"),
    writeJpeg(productNormal, 3, `${prefix}_normal_gl_4k.jpg`, "linear"),
    writeWebJpeg(productNormal, 3, `${prefix}_normal_gl_web.jpg`, "linear"),
    writeJpeg(productRoughnessMap, 1, `${prefix}_roughness_4k.jpg`, "linear"),
    writeWebJpeg(productRoughnessMap, 1, `${prefix}_roughness_web.jpg`, "linear"),
    sharp(productBaseColor, { raw: { width: sourceSize, height: sourceSize, channels: 3 } })
      .resize(384, 256, { fit: "cover" }).webp({ quality: 88, effort: 5 })
      .toFile(path.join(destination, `${prefix}_thumb.webp`)),
  ]);
  return {
    ...product,
    is_specialty: true,
    maps: {
      base_color: `${prefix}_basecolor_web.jpg`,
      normal: `${prefix}_normal_gl_web.jpg`,
      roughness: `${prefix}_roughness_web.jpg`,
      thumbnail: `${prefix}_thumb.webp`,
    },
  };
}

const specialtyVariants = [];
for (let index = 0; index < (catalog.specialty_products ?? []).length; index += 1) {
  specialtyVariants.push(await buildSpecialtyCoating(catalog.specialty_products[index], index));
}

const parameterizedPaints = catalog.paints.map((paint) => ({
  id: paint.asset_id,
  slug: paint.id,
  name_zh: paint.name_zh,
  coating_system: "solid_paint",
  is_specialty: false,
  default_color_srgb: paint.colors[catalog.parameter_schema.lightness.default],
  tone_color_anchors: paint.colors,
  parameter_schema: catalog.parameter_schema,
  legacy_asset_ids: paint.legacy_asset_ids ?? [],
}));

const manifest = {
  schema_version: catalog.schema_version,
  catalog_id: catalog.catalog_id,
  generated_at: new Date().toISOString(),
  generator: catalog.texture_set.generator,
  texture_set: catalog.texture_set,
  asset_count: parameterizedPaints.length + specialtyVariants.length,
  variant_count: parameterizedPaints.length + specialtyVariants.length,
  parameterized_asset_count: parameterizedPaints.length,
  standard_variant_count: parameterizedPaints.length,
  specialty_variant_count: specialtyVariants.length,
  assets: [...parameterizedPaints, ...specialtyVariants],
  variants: [...parameterizedPaints, ...specialtyVariants],
  color_notice: catalog.color_notice,
};
await fs.writeFile(path.join(manifestDir, "paint_manifest.json"), `${JSON.stringify(manifest, null, 2)}\n`, "utf8");

console.log(JSON.stringify({
  destination,
  texture_resolution: outputSize,
  assets: parameterizedPaints.length + specialtyVariants.length,
  specialty_variants: specialtyVariants.length,
}, null, 2));
