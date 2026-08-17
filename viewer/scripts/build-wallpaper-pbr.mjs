import crypto from "node:crypto";
import fs from "node:fs/promises";
import path from "node:path";
import { fileURLToPath } from "node:url";
import sharp from "sharp";

const scriptDir = path.dirname(fileURLToPath(import.meta.url));
const projectRoot = path.resolve(scriptDir, "..", "..");
const catalogPath = path.join(projectRoot, "viewer", "app", "data", "wallpaperCatalog.json");
const destination = path.join(projectRoot, "viewer", "public", "assets", "wallpapers");
const manifestDir = path.join(projectRoot, "viewer", "public", "assets", "manifests");
const masterDestination = path.join(projectRoot, "output", "wallpapers_pbr");
const previewDestination = path.join(projectRoot, "output", "previews");
const imagegenDir = path.join(projectRoot, "output", "imagegen");
const processingMaxEdge = 2048;

const catalog = JSON.parse(await fs.readFile(catalogPath, "utf8"));
await fs.mkdir(destination, { recursive: true });
await fs.mkdir(manifestDir, { recursive: true });
await fs.mkdir(masterDestination, { recursive: true });
await fs.mkdir(previewDestination, { recursive: true });

const PROFILE = {
  woven_fiber: { high: 0.85, mid: 0.1, paper: 0.3, roughVariation: 15 },
  matte_print: { high: 0.04, mid: 0.0, paper: 0.4, roughVariation: 12 },
  linear_emboss: { high: 0.18, mid: 0.68, paper: 0.3, roughVariation: 13 },
  selective_emboss: { high: 0.12, mid: 0.72, paper: 0.3, roughVariation: 12 },
  ornamental_emboss: { high: 0.12, mid: 1.0, paper: 0.25, roughVariation: 14 },
  sculptural_fiber_relief: { high: 0.22, mid: 1.35, paper: 0.28, roughVariation: 18 },
  mineral_print: { high: 0.03, mid: 0.01, paper: 0.4, roughVariation: 14 },
  mural_print: { high: 0.02, mid: 0.0, paper: 0.4, roughVariation: 11 },
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
  if (!profile) throw new Error(`Unknown wallpaper surface profile: ${product.surface_profile}`);

  const heightValues = new Float32Array(width * height);
  let minimum = Number.POSITIVE_INFINITY;
  let maximum = Number.NEGATIVE_INFINITY;
  const physicalAspect = product.repeat_size_m[0] / product.repeat_size_m[1];
  const cellsX = 224;
  const cellsY = Math.max(24, Math.round(cellsX / physicalAspect));

  for (let y = 0; y < height; y += 1) {
    for (let x = 0; x < width; x += 1) {
      const index = y * width + x;
      const highPass = (luminance[index] - blurSmall[index]) / 255;
      const midPass = (blurSmall[index] - blurLarge[index]) / 255;
      const paper = periodicNoise(x, y, width, height, cellsX, cellsY, 73) - 0.5;
      const fiber = periodicNoise(x, y, width, height, 640, Math.max(96, Math.round(640 / physicalAspect)), 131) - 0.5;
      const value = highPass * profile.high + midPass * profile.mid + paper * profile.paper + fiber * 0.16;
      heightValues[index] = value;
      minimum = Math.min(minimum, value);
      maximum = Math.max(maximum, value);
    }
  }

  const span = Math.max(0.0001, maximum - minimum);
  const heightMap = Buffer.alloc(width * height);
  const normalMap = Buffer.alloc(width * height * 3);
  const roughnessMap = Buffer.alloc(width * height);
  const normalizedHeight = new Float32Array(width * height);

  for (let index = 0; index < heightValues.length; index += 1) {
    const value = (heightValues[index] - minimum) / span;
    normalizedHeight[index] = value;
    heightMap[index] = Math.round(24 + value * 207);
  }

  const sampleHeight = (x, y) => normalizedHeight[((y + height) % height) * width + ((x + width) % width)];
  const normalDeriveStrength = 2.25;
  const roughnessMean = product.roughness_mean * 255;

  for (let y = 0; y < height; y += 1) {
    for (let x = 0; x < width; x += 1) {
      const index = y * width + x;
      const dx = sampleHeight(x + 1, y) - sampleHeight(x - 1, y);
      const dy = sampleHeight(x, y + 1) - sampleHeight(x, y - 1);
      let nx = -dx * normalDeriveStrength;
      let ny = -dy * normalDeriveStrength;
      let nz = 1;
      const length = Math.hypot(nx, ny, nz) || 1;
      nx /= length;
      ny /= length;
      nz /= length;
      normalMap[index * 3] = Math.round((nx * 0.5 + 0.5) * 255);
      normalMap[index * 3 + 1] = Math.round((ny * 0.5 + 0.5) * 255);
      normalMap[index * 3 + 2] = Math.round((nz * 0.5 + 0.5) * 255);

      const fine = hash2(x, y, 197) - 0.5;
      const relief = normalizedHeight[index] - 0.5;
      roughnessMap[index] = Math.round(clamp(
        roughnessMean + relief * profile.roughVariation + fine * 5,
        184,
        250,
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
      horizontal += Math.abs(
        buffer[(y * width) * channels + channel]
        - buffer[(y * width + width - 1) * channels + channel],
      );
    }
  }
  for (let x = 0; x < width; x += 1) {
    for (let channel = 0; channel < channels; channel += 1) {
      vertical += Math.abs(
        buffer[x * channels + channel]
        - buffer[((height - 1) * width + x) * channels + channel],
      );
    }
  }
  return {
    horizontal: Number((horizontal / (height * channels)).toFixed(4)),
    vertical: Number((vertical / (width * channels)).toFixed(4)),
  };
}

async function sha256(filename) {
  const data = await fs.readFile(filename);
  return crypto.createHash("sha256").update(data).digest("hex");
}

async function buildWallpaper(product) {
  const source = path.join(projectRoot, product.source_file);
  const [outputWidth, outputHeight] = product.output_resolution;
  const processingScale = Math.min(1, processingMaxEdge / Math.max(outputWidth, outputHeight));
  const width = Math.max(256, Math.round(outputWidth * processingScale));
  const height = Math.max(256, Math.round(outputHeight * processingScale));
  const edgeBlend = Math.max(42, Math.round(Math.min(width, height) * 0.045));

  const { data, info } = await sharp(source)
    .resize(width, height, { fit: "cover", position: "centre", kernel: sharp.kernel.lanczos3 })
    .removeAlpha()
    .toColourspace("srgb")
    .raw()
    .toBuffer({ resolveWithObject: true });
  const baseColor = product.texture_mode === "repeat"
    ? makeSeamless(data, info.width, info.height, info.channels, edgeBlend)
    : data;

  const luminance = luminanceBuffer(baseColor, width, height);
  const [blurSmall, blurLarge] = await Promise.all([
    blurredGray(luminance, width, height, 2.1),
    blurredGray(luminance, width, height, 11.0),
  ]);
  const { heightMap, normalMap, roughnessMap } = createSurfaceMaps(
    luminance,
    blurSmall,
    blurLarge,
    width,
    height,
    product,
  );

  const basename = product.id;
  const basePath = path.join(masterDestination, `${basename}_basecolor_4k.jpg`);
  const normalPath = path.join(masterDestination, `${basename}_normal_gl_4k.png`);
  const roughnessPath = path.join(masterDestination, `${basename}_roughness_4k.png`);
  const heightPath = path.join(masterDestination, `${basename}_height_4k.png`);
  const runtimeBasePath = path.join(destination, `${basename}_basecolor_web.jpg`);
  const runtimeNormalPath = path.join(destination, `${basename}_normal_gl_web.webp`);
  const runtimeRoughnessPath = path.join(destination, `${basename}_roughness_web.webp`);
  const thumbnailPath = path.join(destination, `${basename}_thumb.webp`);
  const runtimeBaseScale = product.texture_mode === "panel_mural" ? 1 : 0.5;
  const runtimeBaseResolution = [
    Math.round(outputWidth * runtimeBaseScale),
    Math.round(outputHeight * runtimeBaseScale),
  ];
  // Linear maps carry low-amplitude relief, so 1.5K is sufficient for the
  // interactive viewer while the lossless 4K production masters stay intact.
  const runtimeLinearScale = Math.min(1, 1536 / Math.max(outputWidth, outputHeight));
  const runtimeLinearResolution = [
    Math.round(outputWidth * runtimeLinearScale),
    Math.round(outputHeight * runtimeLinearScale),
  ];

  await Promise.all([
    sharp(baseColor, { raw: { width, height, channels: 3 } })
      .resize(outputWidth, outputHeight, { kernel: sharp.kernel.lanczos3 })
      .jpeg({ quality: 95, chromaSubsampling: "4:4:4", mozjpeg: true })
      .toFile(basePath),
    sharp(normalMap, { raw: { width, height, channels: 3 } })
      .resize(outputWidth, outputHeight, { kernel: sharp.kernel.lanczos3 })
      .png({ compressionLevel: 6, adaptiveFiltering: true })
      .toFile(normalPath),
    sharp(roughnessMap, { raw: { width, height, channels: 1 } })
      .resize(outputWidth, outputHeight, { kernel: sharp.kernel.lanczos3 })
      .png({ compressionLevel: 6, adaptiveFiltering: true })
      .toFile(roughnessPath),
    sharp(heightMap, { raw: { width, height, channels: 1 } })
      .resize(outputWidth, outputHeight, { kernel: sharp.kernel.lanczos3 })
      .png({ compressionLevel: 6, adaptiveFiltering: true })
      .toFile(heightPath),
    sharp(baseColor, { raw: { width, height, channels: 3 } })
      .resize(runtimeBaseResolution[0], runtimeBaseResolution[1], { kernel: sharp.kernel.lanczos3 })
      .jpeg({ quality: 94, chromaSubsampling: "4:4:4", mozjpeg: true })
      .toFile(runtimeBasePath),
    sharp(normalMap, { raw: { width, height, channels: 3 } })
      .resize(runtimeLinearResolution[0], runtimeLinearResolution[1], { kernel: sharp.kernel.lanczos3 })
      .webp({ quality: 90, effort: 5, smartSubsample: true })
      .toFile(runtimeNormalPath),
    sharp(roughnessMap, { raw: { width, height, channels: 1 } })
      .resize(runtimeLinearResolution[0], runtimeLinearResolution[1], { kernel: sharp.kernel.lanczos3 })
      .webp({ quality: 88, effort: 5, smartSubsample: true })
      .toFile(runtimeRoughnessPath),
    sharp(baseColor, { raw: { width, height, channels: 3 } })
      .resize(384, 256, { fit: "cover", position: "centre", kernel: sharp.kernel.lanczos3 })
      .webp({ quality: 88, effort: 5, smartSubsample: true })
      .toFile(thumbnailPath),
  ]);

  let master = null;
  if (product.master_resolution) {
    const [masterWidth, masterHeight] = product.master_resolution;
    const masterPath = path.join(imagegenDir, `${basename}_master_8k.jpg`);
    await sharp(source)
      .resize(masterWidth, masterHeight, { fit: "cover", position: "centre", kernel: sharp.kernel.lanczos3 })
      .jpeg({ quality: 96, chromaSubsampling: "4:4:4", mozjpeg: true })
      .toFile(masterPath);
    master = path.relative(projectRoot, masterPath).replaceAll("\\", "/");
  }

  const fileStats = {};
  for (const [key, filename] of Object.entries({
    base_color: basePath,
    normal: normalPath,
    roughness: roughnessPath,
    height: heightPath,
  })) {
    const stats = await fs.stat(filename);
    fileStats[key] = { bytes: stats.size, sha256: await sha256(filename) };
  }
  const runtimeFileStats = {};
  for (const [key, filename] of Object.entries({
    base_color: runtimeBasePath,
    normal: runtimeNormalPath,
    roughness: runtimeRoughnessPath,
    thumbnail: thumbnailPath,
  })) {
    const stats = await fs.stat(filename);
    runtimeFileStats[key] = { bytes: stats.size, sha256: await sha256(filename) };
  }

  return {
    id: product.id,
    name_zh: product.name_zh,
    slug: product.slug,
    texture_mode: product.texture_mode,
    resolution: [outputWidth, outputHeight],
    repeat_size_m: product.repeat_size_m,
    match_type: product.match_type,
    surface_profile: product.surface_profile,
    master_maps: {
      base_color: path.relative(projectRoot, basePath).replaceAll("\\", "/"),
      normal: path.relative(projectRoot, normalPath).replaceAll("\\", "/"),
      roughness: path.relative(projectRoot, roughnessPath).replaceAll("\\", "/"),
      height: path.relative(projectRoot, heightPath).replaceAll("\\", "/"),
    },
    runtime_resolution: {
      base_color: runtimeBaseResolution,
      linear_maps: runtimeLinearResolution,
    },
    runtime_maps: {
      base_color: path.basename(runtimeBasePath),
      normal: path.basename(runtimeNormalPath),
      roughness: path.basename(runtimeRoughnessPath),
      thumbnail: path.basename(thumbnailPath),
    },
    source: product.source_file,
    master,
    seam_mae_source_pixels: product.texture_mode === "repeat"
      ? edgeMae(baseColor, width, height, 3)
      : null,
    files: { master: fileStats, runtime: runtimeFileStats },
  };
}

async function makeCatalogPreview(textures) {
  const cellWidth = 640;
  const cellHeight = 470;
  const imageHeight = 390;
  const columns = 4;
  const rows = Math.ceil(textures.length / columns);
  const canvas = sharp({
    create: {
      width: cellWidth * columns,
      height: cellHeight * rows,
      channels: 3,
      background: "#e8e2d7",
    },
  });
  const composites = [];
  for (let index = 0; index < textures.length; index += 1) {
    const textureInfo = textures[index];
    const product = catalog.products.find((item) => item.id === textureInfo.id);
    const left = (index % columns) * cellWidth;
    const top = Math.floor(index / columns) * cellHeight;
    const imageBuffer = await sharp(path.join(destination, textureInfo.runtime_maps.base_color))
      .resize(cellWidth, imageHeight, { fit: "cover", position: "centre" })
      .toBuffer();
    const label = Buffer.from(`<svg width="${cellWidth}" height="${cellHeight - imageHeight}">
      <rect width="100%" height="100%" fill="#f4f0e8"/>
      <text x="22" y="32" font-family="Microsoft YaHei, sans-serif" font-size="22" fill="#2e352f">${String(product.order).padStart(2, "0")} · ${product.name_zh}</text>
      <text x="22" y="58" font-family="Consolas, monospace" font-size="13" fill="#6f766f">${product.id} · ${product.repeat_size_m.join(" × ")} m</text>
    </svg>`);
    composites.push({ input: imageBuffer, left, top });
    composites.push({ input: label, left, top: top + imageHeight });
  }
  await canvas.composite(composites).png({ compressionLevel: 6 }).toFile(
    path.join(previewDestination, "wallpaper_catalog.png"),
  );
}

async function makeRepeatPreview(textures) {
  const repeating = textures.filter((textureInfo) => textureInfo.texture_mode === "repeat");
  const cell = 560;
  const tile = 260;
  const labelHeight = 40;
  const columns = 4;
  const rows = Math.ceil(repeating.length / columns);
  const canvas = sharp({
    create: {
      width: cell * columns,
      height: (tile * 2 + labelHeight) * rows,
      channels: 3,
      background: "#d8d3ca",
    },
  });
  const composites = [];
  for (let index = 0; index < repeating.length; index += 1) {
    const textureInfo = repeating[index];
    const left = (index % columns) * cell;
    const top = Math.floor(index / columns) * (tile * 2 + labelHeight);
    const tileBuffer = await sharp(path.join(destination, textureInfo.runtime_maps.base_color))
      .resize(tile, tile, { fit: "fill" })
      .toBuffer();
    for (let row = 0; row < 2; row += 1) {
      for (let column = 0; column < 2; column += 1) {
        composites.push({ input: tileBuffer, left: left + column * tile, top: top + row * tile });
      }
    }
    const label = Buffer.from(`<svg width="${tile * 2}" height="${labelHeight}"><rect width="100%" height="100%" fill="#f4f0e8"/><text x="12" y="26" font-family="Consolas, monospace" font-size="14" fill="#384039">${textureInfo.id}</text></svg>`);
    composites.push({ input: label, left, top: top + tile * 2 });
  }
  await canvas.composite(composites).png({ compressionLevel: 6 }).toFile(
    path.join(previewDestination, "wallpaper_repeat_check.png"),
  );
}

const textures = [];
for (const product of catalog.products) {
  console.log(`Building ${product.id}...`);
  textures.push(await buildWallpaper(product));
}

const manifest = {
  schema_version: "2.0.0",
  catalog_id: catalog.catalog_id,
  generated_at: new Date().toISOString(),
  generator: "viewer/scripts/build-wallpaper-pbr.mjs",
  color_space: { base_color: "sRGB", normal_roughness_height: "linear" },
  normal_convention: "OpenGL",
  texture_count: textures.length,
  textures,
  source_and_license: catalog.source_and_license,
};

await fs.writeFile(
  path.join(manifestDir, "wallpaper_manifest.json"),
  `${JSON.stringify(manifest, null, 2)}\n`,
  "utf8",
);
await Promise.all([makeCatalogPreview(textures), makeRepeatPreview(textures)]);
console.log(JSON.stringify({ destination, masterDestination, texture_count: textures.length }, null, 2));
