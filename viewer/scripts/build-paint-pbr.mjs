import fs from "node:fs/promises";
import path from "node:path";
import { fileURLToPath } from "node:url";
import sharp from "sharp";

const scriptDir = path.dirname(fileURLToPath(import.meta.url));
const viewerDir = path.resolve(scriptDir, "..");
const catalogPath = path.join(viewerDir, "app", "data", "paintCatalog.json");
const destination = path.join(viewerDir, "public", "assets", "paints");
const sourceSize = 2048;
const outputSize = 4096;

const catalog = JSON.parse(await fs.readFile(catalogPath, "utf8"));
await fs.mkdir(destination, { recursive: true });

function hash2(x, y, seed) {
  let value = (Math.imul(x, 374761393) + Math.imul(y, 668265263) + Math.imul(seed, 1442695041)) | 0;
  value = Math.imul(value ^ (value >>> 13), 1274126177);
  return ((value ^ (value >>> 16)) >>> 0) / 4294967295;
}

function smooth(value) {
  return value * value * (3 - 2 * value);
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

await Promise.all([
  writeJpeg(baseColor, 3, "paint_micro_basecolor_4k.jpg", "srgb"),
  writeJpeg(normal, 3, "paint_micro_normal_gl_4k.jpg", "linear"),
  writeJpeg(roughMatte, 1, "paint_micro_roughness_matte_4k.jpg", "linear"),
  writeJpeg(roughEggshell, 1, "paint_micro_roughness_eggshell_4k.jpg", "linear"),
]);

const expandedVariants = catalog.families.flatMap((family) =>
  catalog.tones.flatMap((tone) =>
    catalog.finishes.map((finish) => {
      const override = family.id_overrides?.[`${tone.id}_${finish.id}`];
      return {
        id: override ?? `paint_${family.id}_${tone.id}_${finish.id}_01`,
        family_id: family.id,
        family_name_zh: family.name_zh,
        tone: tone.id,
        finish: finish.id,
        color_srgb: family.colors[tone.id],
        roughness_mean: finish.roughness_mean,
        roughness_range: finish.roughness_range,
        normal_scale: finish.normal_scale,
      };
    }),
  ),
);

const manifest = {
  schema_version: catalog.schema_version,
  catalog_id: catalog.catalog_id,
  generated_at: new Date().toISOString(),
  generator: catalog.texture_set.generator,
  texture_set: catalog.texture_set,
  variant_count: expandedVariants.length,
  variants: expandedVariants,
  color_notice: catalog.color_notice,
};
await fs.writeFile(path.join(destination, "paint_manifest.json"), `${JSON.stringify(manifest, null, 2)}\n`, "utf8");

console.log(JSON.stringify({ destination, texture_resolution: outputSize, variants: expandedVariants.length }, null, 2));
