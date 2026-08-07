import crypto from "node:crypto";
import fs from "node:fs/promises";
import path from "node:path";
import { fileURLToPath } from "node:url";
import sharp from "sharp";

const scriptDir = path.dirname(fileURLToPath(import.meta.url));
const projectRoot = path.resolve(scriptDir, "..", "..");
const floorCatalogPath = path.join(projectRoot, "viewer", "app", "data", "floorCatalog.json");
const tileCatalogPath = path.join(projectRoot, "viewer", "app", "data", "tileCatalog.json");
const runtimeDestination = path.join(projectRoot, "viewer", "public", "assets", "surfaces");
const masterDestination = path.join(projectRoot, "output", "surfaces_pbr");
const previewDestination = path.join(projectRoot, "output", "previews");
const processingSize = 2048;
const masterSize = 4096;
const runtimeSize = 1024;

const floorCatalog = JSON.parse(await fs.readFile(floorCatalogPath, "utf8"));
const tileCatalog = JSON.parse(await fs.readFile(tileCatalogPath, "utf8"));
const products = [
  ...floorCatalog.products.map((product) => ({ ...product, category: "wood_floor" })),
  ...tileCatalog.products.map((product) => ({ ...product, category: "tile" })),
];

await Promise.all([
  fs.mkdir(runtimeDestination, { recursive: true }),
  fs.mkdir(masterDestination, { recursive: true }),
  fs.mkdir(previewDestination, { recursive: true }),
]);

const PROFILE = {
  fine_wood: { high: 0.62, mid: 0.18, micro: 0.14, normal: 2.4, roughVariation: 18 },
  natural_wood: { high: 0.56, mid: 0.22, micro: 0.12, normal: 2.6, roughVariation: 18 },
  brushed_wood: { high: 0.68, mid: 0.28, micro: 0.16, normal: 3.0, roughVariation: 22 },
  satin_ceramic: { high: 0.12, mid: 0.04, micro: 0.10, normal: 1.1, roughVariation: 10 },
  honed_stone: { high: 0.10, mid: 0.06, micro: 0.13, normal: 1.2, roughVariation: 12 },
  cleft_stone: { high: 0.36, mid: 0.22, micro: 0.18, normal: 2.1, roughVariation: 18 },
  microcement: { high: 0.25, mid: 0.20, micro: 0.16, normal: 1.45, roughVariation: 15 },
  terrazzo: { high: 0.22, mid: 0.08, micro: 0.12, normal: 1.35, roughVariation: 14 },
  matte_printed_ceramic: { high: 0.06, mid: 0.02, micro: 0.11, normal: 0.9, roughVariation: 10 },
};

function clamp(value, minimum, maximum) {
  return Math.max(minimum, Math.min(maximum, value));
}

function smoothstep(value) {
  const clamped = clamp(value, 0, 1);
  return clamped * clamped * (3 - 2 * clamped);
}

function hash2(x, y, seed) {
  let value = (Math.imul(x, 374761393) + Math.imul(y, 668265263) + Math.imul(seed, 1442695041)) | 0;
  value = Math.imul(value ^ (value >>> 13), 1274126177);
  return ((value ^ (value >>> 16)) >>> 0) / 4294967295;
}

function periodicNoise(x, y, width, height, cellsX, cellsY, seed) {
  const gx = (x / Math.max(1, width - 1)) * cellsX;
  const gy = (y / Math.max(1, height - 1)) * cellsY;
  const fx = Math.floor(gx);
  const fy = Math.floor(gy);
  const x0 = ((fx % cellsX) + cellsX) % cellsX;
  const y0 = ((fy % cellsY) + cellsY) % cellsY;
  const x1 = (x0 + 1) % cellsX;
  const y1 = (y0 + 1) % cellsY;
  const tx = smoothstep(gx - fx);
  const ty = smoothstep(gy - fy);
  const top = hash2(x0, y0, seed) * (1 - tx) + hash2(x1, y0, seed) * tx;
  const bottom = hash2(x0, y1, seed) * (1 - tx) + hash2(x1, y1, seed) * tx;
  return top * (1 - ty) + bottom * ty;
}

function parseHex(hex) {
  const value = Number.parseInt(hex.slice(1), 16);
  return [(value >> 16) & 255, (value >> 8) & 255, value & 255];
}

function makeSyntheticSource(product, width, height) {
  const rgb = Buffer.alloc(width * height * 3);
  const base = parseHex(product.tint);
  for (let y = 0; y < height; y += 1) {
    for (let x = 0; x < width; x += 1) {
      const broad = periodicNoise(x, y, width, height, 7, 7, 31) - 0.5;
      const medium = periodicNoise(x, y, width, height, 29, 29, 67) - 0.5;
      const fine = periodicNoise(x, y, width, height, 181, 181, 109) - 0.5;
      let variation = broad * 16 + medium * 8 + fine * 3;
      if (product.synthetic_profile === "travertine") {
        const band = Math.sin((y / height) * Math.PI * 18 + broad * 2.2) * 0.5 + 0.5;
        variation += (band - 0.5) * 17;
      } else {
        variation = broad * 10 + medium * 7 + fine * 4;
      }
      const index = (y * width + x) * 3;
      rgb[index] = clamp(Math.round(base[0] + variation), 0, 255);
      rgb[index + 1] = clamp(Math.round(base[1] + variation * 0.96), 0, 255);
      rgb[index + 2] = clamp(Math.round(base[2] + variation * 0.88), 0, 255);
    }
  }
  return rgb;
}

function makeSeamless(source, width, height, channels, edgeBlend) {
  const horizontal = Buffer.alloc(source.length);
  const result = Buffer.alloc(source.length);
  for (let y = 0; y < height; y += 1) {
    for (let x = 0; x < width; x += 1) {
      const distance = Math.min(x, width - 1 - x);
      const keep = distance >= edgeBlend ? 1 : smoothstep(distance / edgeBlend);
      const oppositeX = width - 1 - x;
      for (let channel = 0; channel < channels; channel += 1) {
        const index = (y * width + x) * channels + channel;
        const opposite = (y * width + oppositeX) * channels + channel;
        const sharedEdge = (source[index] + source[opposite]) * 0.5;
        horizontal[index] = Math.round(sharedEdge * (1 - keep) + source[index] * keep);
      }
    }
  }
  for (let y = 0; y < height; y += 1) {
    const distance = Math.min(y, height - 1 - y);
    const keep = distance >= edgeBlend ? 1 : smoothstep(distance / edgeBlend);
    const oppositeY = height - 1 - y;
    for (let x = 0; x < width; x += 1) {
      for (let channel = 0; channel < channels; channel += 1) {
        const index = (y * width + x) * channels + channel;
        const opposite = (oppositeY * width + x) * channels + channel;
        const sharedEdge = (horizontal[index] + horizontal[opposite]) * 0.5;
        result[index] = Math.round(sharedEdge * (1 - keep) + horizontal[index] * keep);
      }
    }
  }
  return result;
}

function luminanceBuffer(rgb, width, height) {
  const luminance = Buffer.alloc(width * height);
  for (let index = 0; index < luminance.length; index += 1) {
    const rgbIndex = index * 3;
    luminance[index] = Math.round(
      rgb[rgbIndex] * 0.2126 + rgb[rgbIndex + 1] * 0.7152 + rgb[rgbIndex + 2] * 0.0722,
    );
  }
  return luminance;
}

async function blurredGray(gray, width, height, sigma) {
  return sharp(gray, { raw: { width, height, channels: 1 } }).blur(sigma).raw().toBuffer();
}

function createSurfaceMaps(luminance, blurSmall, blurLarge, width, height, product) {
  const profile = PROFILE[product.surface_profile];
  if (!profile) throw new Error(`Unknown surface profile: ${product.surface_profile}`);
  const heightValues = new Float32Array(width * height);
  let minimum = Number.POSITIVE_INFINITY;
  let maximum = Number.NEGATIVE_INFINITY;
  for (let y = 0; y < height; y += 1) {
    for (let x = 0; x < width; x += 1) {
      const index = y * width + x;
      const highPass = (luminance[index] - blurSmall[index]) / 255;
      const midPass = (blurSmall[index] - blurLarge[index]) / 255;
      const micro = periodicNoise(x, y, width, height, 420, 420, 173) - 0.5;
      const value = highPass * profile.high + midPass * profile.mid + micro * profile.micro;
      heightValues[index] = value;
      minimum = Math.min(minimum, value);
      maximum = Math.max(maximum, value);
    }
  }
  const span = Math.max(0.0001, maximum - minimum);
  const normalizedHeight = new Float32Array(width * height);
  const heightMap = Buffer.alloc(width * height);
  const normalMap = Buffer.alloc(width * height * 3);
  const roughnessMap = Buffer.alloc(width * height);
  for (let index = 0; index < heightValues.length; index += 1) {
    const value = (heightValues[index] - minimum) / span;
    normalizedHeight[index] = value;
    heightMap[index] = Math.round(22 + value * 211);
  }
  const sample = (x, y) => normalizedHeight[((y + height) % height) * width + ((x + width) % width)];
  const roughnessMean = product.roughness_mean * 255;
  for (let y = 0; y < height; y += 1) {
    for (let x = 0; x < width; x += 1) {
      const index = y * width + x;
      let nx = -(sample(x + 1, y) - sample(x - 1, y)) * profile.normal;
      let ny = -(sample(x, y + 1) - sample(x, y - 1)) * profile.normal;
      let nz = 1;
      const length = Math.hypot(nx, ny, nz) || 1;
      nx /= length;
      ny /= length;
      nz /= length;
      normalMap[index * 3] = Math.round((nx * 0.5 + 0.5) * 255);
      normalMap[index * 3 + 1] = Math.round((ny * 0.5 + 0.5) * 255);
      normalMap[index * 3 + 2] = Math.round((nz * 0.5 + 0.5) * 255);
      const relief = normalizedHeight[index] - 0.5;
      const fine = hash2(x, y, 229) - 0.5;
      roughnessMap[index] = Math.round(clamp(
        roughnessMean + relief * profile.roughVariation + fine * 5,
        110,
        246,
      ));
    }
  }
  return { heightMap, normalMap, roughnessMap };
}

function edgeMae(buffer, width, height, channels) {
  let horizontal = 0;
  let vertical = 0;
  for (let y = 0; y < height; y += 1) {
    for (let channel = 0; channel < channels; channel += 1) {
      horizontal += Math.abs(buffer[(y * width) * channels + channel] - buffer[(y * width + width - 1) * channels + channel]);
    }
  }
  for (let x = 0; x < width; x += 1) {
    for (let channel = 0; channel < channels; channel += 1) {
      vertical += Math.abs(buffer[x * channels + channel] - buffer[((height - 1) * width + x) * channels + channel]);
    }
  }
  return {
    horizontal: Number((horizontal / (height * channels)).toFixed(4)),
    vertical: Number((vertical / (width * channels)).toFixed(4)),
  };
}

async function sha256(filename) {
  return crypto.createHash("sha256").update(await fs.readFile(filename)).digest("hex");
}

async function readSource(product) {
  if (product.synthetic_profile) {
    return makeSyntheticSource(product, processingSize, processingSize);
  }
  const source = path.join(projectRoot, product.source_file);
  let pipeline = sharp(source).resize(processingSize, processingSize, {
    fit: "cover",
    position: "centre",
    kernel: sharp.kernel.lanczos3,
  });
  if (product.modulate) pipeline = pipeline.modulate(product.modulate);
  const { data, info } = await pipeline.removeAlpha().toColourspace("srgb").raw().toBuffer({ resolveWithObject: true });
  if (!product.colorize) return data;
  const tint = parseHex(product.tint);
  const colorized = Buffer.alloc(processingSize * processingSize * 3);
  for (let index = 0; index < processingSize * processingSize; index += 1) {
    const sourceIndex = index * info.channels;
    const luminance = (
      data[sourceIndex] * 0.2126
      + data[sourceIndex + Math.min(1, info.channels - 1)] * 0.7152
      + data[sourceIndex + Math.min(2, info.channels - 1)] * 0.0722
    ) / 255;
    const grain = 0.52 + luminance * 0.72;
    colorized[index * 3] = clamp(Math.round(tint[0] * grain), 0, 255);
    colorized[index * 3 + 1] = clamp(Math.round(tint[1] * grain), 0, 255);
    colorized[index * 3 + 2] = clamp(Math.round(tint[2] * grain), 0, 255);
  }
  return colorized;
}

async function buildProduct(product) {
  const source = await readSource(product);
  const baseColor = makeSeamless(source, processingSize, processingSize, 3, 84);
  const luminance = luminanceBuffer(baseColor, processingSize, processingSize);
  const [blurSmall, blurLarge] = await Promise.all([
    blurredGray(luminance, processingSize, processingSize, 2.0),
    blurredGray(luminance, processingSize, processingSize, 13.0),
  ]);
  const { heightMap, normalMap, roughnessMap } = createSurfaceMaps(
    luminance,
    blurSmall,
    blurLarge,
    processingSize,
    processingSize,
    product,
  );
  const basename = product.id;
  const masterPaths = {
    base_color: path.join(masterDestination, `${basename}_basecolor_4k.jpg`),
    normal: path.join(masterDestination, `${basename}_normal_gl_4k.png`),
    roughness: path.join(masterDestination, `${basename}_roughness_4k.png`),
    height: path.join(masterDestination, `${basename}_height_4k.png`),
  };
  const runtimePaths = {
    base_color: path.join(runtimeDestination, `${basename}_basecolor_web.jpg`),
    normal: path.join(runtimeDestination, `${basename}_normal_gl_web.webp`),
    roughness: path.join(runtimeDestination, `${basename}_roughness_web.webp`),
    thumbnail: path.join(runtimeDestination, `${basename}_thumb.webp`),
  };
  await Promise.all([
    sharp(baseColor, { raw: { width: processingSize, height: processingSize, channels: 3 } }).resize(masterSize, masterSize).jpeg({ quality: 94, chromaSubsampling: "4:4:4", mozjpeg: true }).toFile(masterPaths.base_color),
    sharp(normalMap, { raw: { width: processingSize, height: processingSize, channels: 3 } }).resize(masterSize, masterSize).png({ compressionLevel: 6 }).toFile(masterPaths.normal),
    sharp(roughnessMap, { raw: { width: processingSize, height: processingSize, channels: 1 } }).resize(masterSize, masterSize).png({ compressionLevel: 6 }).toFile(masterPaths.roughness),
    sharp(heightMap, { raw: { width: processingSize, height: processingSize, channels: 1 } }).resize(masterSize, masterSize).png({ compressionLevel: 6 }).toFile(masterPaths.height),
    sharp(baseColor, { raw: { width: processingSize, height: processingSize, channels: 3 } }).resize(runtimeSize, runtimeSize).jpeg({ quality: 91, chromaSubsampling: "4:4:4", mozjpeg: true }).toFile(runtimePaths.base_color),
    sharp(normalMap, { raw: { width: processingSize, height: processingSize, channels: 3 } }).resize(runtimeSize, runtimeSize).webp({ quality: 90, effort: 5 }).toFile(runtimePaths.normal),
    sharp(roughnessMap, { raw: { width: processingSize, height: processingSize, channels: 1 } }).resize(runtimeSize, runtimeSize).webp({ quality: 88, effort: 5 }).toFile(runtimePaths.roughness),
    sharp(baseColor, { raw: { width: processingSize, height: processingSize, channels: 3 } }).resize(384, 256, { fit: "cover" }).webp({ quality: 86, effort: 5 }).toFile(runtimePaths.thumbnail),
  ]);
  const files = { master: {}, runtime: {} };
  for (const [key, filename] of Object.entries(masterPaths)) {
    const stat = await fs.stat(filename);
    files.master[key] = { bytes: stat.size, sha256: await sha256(filename) };
  }
  for (const [key, filename] of Object.entries(runtimePaths)) {
    const stat = await fs.stat(filename);
    files.runtime[key] = { bytes: stat.size, sha256: await sha256(filename) };
  }
  return {
    ...product,
    resolution: [masterSize, masterSize],
    runtime_resolution: [runtimeSize, runtimeSize],
    master_maps: Object.fromEntries(Object.entries(masterPaths).map(([key, filename]) => [key, path.relative(projectRoot, filename).replaceAll("\\", "/")])),
    runtime_maps: Object.fromEntries(Object.entries(runtimePaths).map(([key, filename]) => [key, path.basename(filename)])),
    seam_mae_source_pixels: edgeMae(baseColor, processingSize, processingSize, 3),
    files,
  };
}

async function makeCatalogPreview(textures) {
  const cellWidth = 560;
  const cellHeight = 390;
  const imageHeight = 320;
  const columns = 4;
  const rows = Math.ceil(textures.length / columns);
  const canvas = sharp({ create: { width: cellWidth * columns, height: cellHeight * rows, channels: 3, background: "#d8d2c8" } });
  const composites = [];
  for (let index = 0; index < textures.length; index += 1) {
    const product = textures[index];
    const left = (index % columns) * cellWidth;
    const top = Math.floor(index / columns) * cellHeight;
    const image = await sharp(path.join(runtimeDestination, product.runtime_maps.base_color)).resize(cellWidth, imageHeight, { fit: "cover" }).toBuffer();
    const label = Buffer.from(`<svg width="${cellWidth}" height="${cellHeight - imageHeight}"><rect width="100%" height="100%" fill="#f3efe7"/><text x="18" y="29" font-family="Microsoft YaHei, sans-serif" font-size="20" fill="#30362f">${String(product.order).padStart(2, "0")} · ${product.name_zh}</text><text x="18" y="53" font-family="Consolas, monospace" font-size="12" fill="#697069">${product.id}</text></svg>`);
    composites.push({ input: image, left, top });
    composites.push({ input: label, left, top: top + imageHeight });
  }
  await canvas.composite(composites).png({ compressionLevel: 6 }).toFile(path.join(previewDestination, "surface_catalog.png"));
}

async function makeRepeatPreview(textures) {
  const tile = 260;
  const labelHeight = 34;
  const cellWidth = tile * 2;
  const cellHeight = tile * 2 + labelHeight;
  const columns = 4;
  const rows = Math.ceil(textures.length / columns);
  const canvas = sharp({ create: { width: cellWidth * columns, height: cellHeight * rows, channels: 3, background: "#d4cec4" } });
  const composites = [];
  for (let index = 0; index < textures.length; index += 1) {
    const product = textures[index];
    const left = (index % columns) * cellWidth;
    const top = Math.floor(index / columns) * cellHeight;
    const image = await sharp(path.join(runtimeDestination, product.runtime_maps.base_color)).resize(tile, tile).toBuffer();
    for (let row = 0; row < 2; row += 1) for (let column = 0; column < 2; column += 1) composites.push({ input: image, left: left + column * tile, top: top + row * tile });
    const label = Buffer.from(`<svg width="${cellWidth}" height="${labelHeight}"><rect width="100%" height="100%" fill="#f3efe7"/><text x="10" y="23" font-family="Consolas, monospace" font-size="13" fill="#384039">${product.id}</text></svg>`);
    composites.push({ input: label, left, top: top + tile * 2 });
  }
  await canvas.composite(composites).png({ compressionLevel: 6 }).toFile(path.join(previewDestination, "surface_repeat_check.png"));
}

const textures = [];
for (const product of products) {
  console.log(`Building ${product.id}...`);
  textures.push(await buildProduct(product));
}

const manifest = {
  schema_version: "1.0.0",
  catalog_ids: [floorCatalog.catalog_id, tileCatalog.catalog_id],
  generated_at: new Date().toISOString(),
  generator: "viewer/scripts/build-surface-pbr.mjs",
  color_space: { base_color: "sRGB", normal_roughness_height: "linear" },
  normal_convention: "OpenGL",
  texture_count: textures.length,
  category_counts: {
    wood_floor: textures.filter((item) => item.category === "wood_floor").length,
    tile: textures.filter((item) => item.category === "tile").length,
  },
  textures,
  source_and_license: {
    floors: floorCatalog.source_and_license,
    tiles: tileCatalog.source_and_license,
  },
};

await fs.writeFile(path.join(runtimeDestination, "texture_manifest.json"), `${JSON.stringify(manifest, null, 2)}\n`, "utf8");
await Promise.all([makeCatalogPreview(textures), makeRepeatPreview(textures)]);
console.log(JSON.stringify({ runtimeDestination, masterDestination, texture_count: textures.length }, null, 2));
