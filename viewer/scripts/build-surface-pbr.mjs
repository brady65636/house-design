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
const manifestDir = path.join(projectRoot, "viewer", "public", "assets", "manifests");
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
  fs.mkdir(manifestDir, { recursive: true }),
  fs.mkdir(masterDestination, { recursive: true }),
  fs.mkdir(previewDestination, { recursive: true }),
]);

const PROFILE = {
  fine_wood: { high: 0.62, mid: 0.18, micro: 0.14, normal: 2.4, roughVariation: 18 },
  natural_wood: { high: 0.56, mid: 0.22, micro: 0.12, normal: 2.6, roughVariation: 18 },
  brushed_wood: { high: 0.68, mid: 0.28, micro: 0.16, normal: 3.0, roughVariation: 22 },
  character_wood: { high: 0.72, mid: 0.32, micro: 0.16, normal: 3.2, roughVariation: 24 },
  rift_linear_wood: { high: 0.50, mid: 0.12, micro: 0.12, normal: 2.0, roughVariation: 14 },
  endgrain_block: { high: 0.62, mid: 0.30, micro: 0.18, normal: 3.0, roughVariation: 23 },
  natural_cork: { high: 0.48, mid: 0.26, micro: 0.22, normal: 2.2, roughVariation: 22 },
  satin_ceramic: { high: 0.12, mid: 0.04, micro: 0.10, normal: 1.1, roughVariation: 10 },
  honed_stone: { high: 0.10, mid: 0.06, micro: 0.13, normal: 1.2, roughVariation: 12 },
  cleft_stone: { high: 0.36, mid: 0.22, micro: 0.18, normal: 2.1, roughVariation: 18 },
  microcement: { high: 0.25, mid: 0.20, micro: 0.16, normal: 1.45, roughVariation: 15 },
  terrazzo: { high: 0.22, mid: 0.08, micro: 0.12, normal: 1.35, roughVariation: 14 },
  matte_printed_ceramic: { high: 0.06, mid: 0.02, micro: 0.11, normal: 0.9, roughVariation: 10 },
  porous_terracotta: { high: 0.30, mid: 0.20, micro: 0.20, normal: 1.85, roughVariation: 20 },
  hand_glazed_ceramic: { high: 0.12, mid: 0.10, micro: 0.08, normal: 1.15, roughVariation: 13 },
  relief_ceramic: { high: 0.10, mid: 0.06, micro: 0.06, normal: 4.1, roughVariation: 17 },
  printed_honed_ceramic: { high: 0.02, mid: 0.00, micro: 0.10, normal: 0.85, roughVariation: 9 },
  fine_glazed_mosaic: { high: 0.10, mid: 0.04, micro: 0.08, normal: 2.6, roughVariation: 16 },
  matte_monochrome_ceramic: { high: 0.08, mid: 0.04, micro: 0.12, normal: 1.5, roughVariation: 10 },
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
  const checkerColors = product.synthetic_profile === "checker_black_ivory"
    ? product.checker_colors.map(parseHex)
    : null;
  const checkerGrout = product.synthetic_profile === "checker_black_ivory"
    ? parseHex(product.grout_color)
    : null;
  const fluted = product.synthetic_profile === "ivory_fluted_relief";
  const flutedGrout = fluted ? parseHex(product.grout_color) : null;
  const finger = product.synthetic_profile === "cool_finger_mosaic";
  const penny = product.synthetic_profile === "smoke_penny_mosaic";
  const deepMatte = product.synthetic_profile === "deep_matte_monochrome";
  const geometricGrout = finger || penny || deepMatte ? parseHex(product.grout_color) : null;
  for (let y = 0; y < height; y += 1) {
    for (let x = 0; x < width; x += 1) {
      if (finger && geometricGrout) {
        const columns = 24;
        const rows = 6;
        const cellWidth = width / columns;
        const cellHeight = height / rows;
        const localX = (x % cellWidth) / cellWidth;
        const localY = (y % cellHeight) / cellHeight;
        const grout = localX < 0.055 || localX > 0.945 || localY < 0.075 || localY > 0.925;
        const tileX = Math.floor(x / cellWidth);
        const tileY = Math.floor(y / cellHeight);
        const colour = grout ? geometricGrout : base;
        const tileVariation = (hash2(tileX, tileY, 521) - 0.5) * 17;
        const glaze = (periodicNoise(x, y, width, height, 72, 24, 541) - 0.5) * 3.2;
        const variation = grout ? glaze * 0.6 : tileVariation + glaze;
        const index = (y * width + x) * 3;
        rgb[index] = clamp(Math.round(colour[0] + variation * 0.75), 0, 255);
        rgb[index + 1] = clamp(Math.round(colour[1] + variation * 0.95), 0, 255);
        rgb[index + 2] = clamp(Math.round(colour[2] + variation * 1.12), 0, 255);
        continue;
      }
      if (penny && geometricGrout) {
        const columns = 12;
        const rows = 12;
        const cellWidth = width / columns;
        const cellHeight = height / rows;
        const row = Math.floor(y / cellHeight);
        const shiftedX = x + (row % 2) * cellWidth * 0.5;
        const column = Math.floor(shiftedX / cellWidth);
        const localX = ((shiftedX % cellWidth) + cellWidth) % cellWidth;
        const localY = y % cellHeight;
        const dx = (localX - cellWidth * 0.5) / cellWidth;
        const dy = (localY - cellHeight * 0.5) / cellHeight;
        const disc = Math.hypot(dx, dy) < 0.405;
        const colour = disc ? base : geometricGrout;
        const tileVariation = (hash2(column, row, 601) - 0.5) * 13;
        const glaze = (periodicNoise(x, y, width, height, 60, 60, 617) - 0.5) * 3;
        const variation = disc ? tileVariation + glaze : glaze * 0.45;
        const index = (y * width + x) * 3;
        rgb[index] = clamp(Math.round(colour[0] + variation * 0.86), 0, 255);
        rgb[index + 1] = clamp(Math.round(colour[1] + variation * 0.93), 0, 255);
        rgb[index + 2] = clamp(Math.round(colour[2] + variation), 0, 255);
        continue;
      }
      if (deepMatte && geometricGrout) {
        const columns = 2;
        const rows = 2;
        const cellWidth = width / columns;
        const cellHeight = height / rows;
        const localX = (x % cellWidth) / cellWidth;
        const localY = (y % cellHeight) / cellHeight;
        const grout = localX < 0.006 || localX > 0.994 || localY < 0.006 || localY > 0.994;
        const tileX = Math.floor(x / cellWidth);
        const tileY = Math.floor(y / cellHeight);
        const colour = grout ? geometricGrout : base;
        const tileVariation = (hash2(tileX, tileY, 683) - 0.5) * 5;
        const fine = (periodicNoise(x, y, width, height, 190, 190, 701) - 0.5) * 3.4;
        const variation = grout ? fine * 0.35 : tileVariation + fine;
        const index = (y * width + x) * 3;
        rgb[index] = clamp(Math.round(colour[0] + variation), 0, 255);
        rgb[index + 1] = clamp(Math.round(colour[1] + variation * 1.02), 0, 255);
        rgb[index + 2] = clamp(Math.round(colour[2] + variation * 1.05), 0, 255);
        continue;
      }
      if (fluted && flutedGrout) {
        const fluteCount = product.flute_count ?? 16;
        const moduleRows = 3;
        const phase = (x / width) * fluteCount;
        const local = phase - Math.floor(phase);
        const rowPhase = (y / height) * moduleRows;
        const rowLocal = rowPhase - Math.floor(rowPhase);
        const grout = rowLocal < 0.012 || rowLocal > 0.988;
        const colour = grout ? flutedGrout : base;
        const tileBand = periodicNoise(Math.floor(phase), Math.floor(rowPhase), fluteCount, moduleRows, fluteCount, moduleRows, 401) - 0.5;
        const fiber = periodicNoise(x, y, width, height, 180, 180, 419) - 0.5;
        const materialVariation = grout ? fiber * 2 : tileBand * 7 + fiber * 2 + (local - 0.5) * 1.2;
        const index = (y * width + x) * 3;
        rgb[index] = clamp(Math.round(colour[0] + materialVariation), 0, 255);
        rgb[index + 1] = clamp(Math.round(colour[1] + materialVariation * 0.96), 0, 255);
        rgb[index + 2] = clamp(Math.round(colour[2] + materialVariation * 0.9), 0, 255);
        continue;
      }
      if (checkerColors && checkerGrout) {
        const moduleCount = 8;
        const moduleWidth = width / moduleCount;
        const moduleHeight = height / moduleCount;
        const localX = x % moduleWidth;
        const localY = y % moduleHeight;
        const groutWidth = Math.max(3, Math.round(width * 0.003));
        const isGrout = localX < groutWidth || localX >= moduleWidth - groutWidth
          || localY < groutWidth || localY >= moduleHeight - groutWidth;
        const tileX = Math.floor(x / moduleWidth);
        const tileY = Math.floor(y / moduleHeight);
        const color = isGrout ? checkerGrout : checkerColors[(tileX + tileY) % 2];
        const broad = periodicNoise(x, y, width, height, 24, 24, 307) - 0.5;
        const fine = periodicNoise(x, y, width, height, 260, 260, 353) - 0.5;
        const variation = isGrout ? fine * 5 : broad * 7 + fine * 3;
        const index = (y * width + x) * 3;
        rgb[index] = clamp(Math.round(color[0] + variation), 0, 255);
        rgb[index + 1] = clamp(Math.round(color[1] + variation * 0.96), 0, 255);
        rgb[index + 2] = clamp(Math.round(color[2] + variation * 0.90), 0, 255);
        continue;
      }
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
      let value;
      if (product.synthetic_profile === "ivory_fluted_relief") {
        const fluteCount = product.flute_count ?? 16;
        const phase = (x / width) * fluteCount;
        const local = phase - Math.floor(phase);
        const ridge = Math.sin(Math.PI * local) ** 0.72;
        const rowLocal = ((y / height) * 3) % 1;
        const groutCut = rowLocal < 0.012 || rowLocal > 0.988 ? -0.28 : 0;
        value = ridge * 0.92 + groutCut + highPass * 0.05 + micro * 0.035;
      } else if (product.synthetic_profile === "cool_finger_mosaic") {
        const columns = 24;
        const rows = 6;
        const localX = ((x / width) * columns) % 1;
        const localY = ((y / height) * rows) % 1;
        const edge = Math.min(localX, 1 - localX, localY, 1 - localY);
        const tileTop = smoothstep(clamp(edge / 0.075, 0, 1));
        value = tileTop * 0.86 + highPass * 0.05 + micro * 0.028;
      } else if (product.synthetic_profile === "smoke_penny_mosaic") {
        const columns = 12;
        const rows = 12;
        const row = Math.floor((y / height) * rows);
        const localX = (((x / width) * columns + (row % 2) * 0.5) % 1 + 1) % 1;
        const localY = ((y / height) * rows) % 1;
        const radius = Math.hypot(localX - 0.5, localY - 0.5);
        const disc = 1 - smoothstep(clamp((radius - 0.37) / 0.045, 0, 1));
        value = disc * 0.82 + highPass * 0.04 + micro * 0.026;
      } else if (product.synthetic_profile === "deep_matte_monochrome") {
        const columns = 2;
        const rows = 2;
        const localX = ((x / width) * columns) % 1;
        const localY = ((y / height) * rows) % 1;
        const edge = Math.min(localX, 1 - localX, localY, 1 - localY);
        const tileTop = smoothstep(clamp(edge / 0.018, 0, 1));
        value = tileTop * 0.58 + highPass * 0.035 + micro * 0.05;
      } else {
        value = highPass * profile.high + midPass * profile.mid + micro * profile.micro;
      }
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

function lockPeriodicEdges(buffer, width, height, channels) {
  for (let y = 0; y < height; y += 1) {
    for (let channel = 0; channel < channels; channel += 1) {
      buffer[(y * width + width - 1) * channels + channel] = buffer[(y * width) * channels + channel];
    }
  }
  for (let x = 0; x < width; x += 1) {
    for (let channel = 0; channel < channels; channel += 1) {
      buffer[((height - 1) * width + x) * channels + channel] = buffer[x * channels + channel];
    }
  }
  return buffer;
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
  const seamEdgeBlend = product.seam_edge_blend_px ?? 84;
  const baseColor = product.already_seamless
    ? lockPeriodicEdges(source, processingSize, processingSize, 3)
    : makeSeamless(source, processingSize, processingSize, 3, seamEdgeBlend);
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

const requestedIds = (process.env.SURFACE_ASSET_IDS ?? "")
  .split(",")
  .map((value) => value.trim())
  .filter(Boolean);
const requestedIdSet = new Set(requestedIds);
const productsToBuild = requestedIds.length > 0
  ? products.filter((product) => requestedIdSet.has(product.id))
  : products;
if (requestedIds.length > 0 && productsToBuild.length !== requestedIdSet.size) {
  const knownIds = new Set(products.map((product) => product.id));
  const unknownIds = requestedIds.filter((id) => !knownIds.has(id));
  throw new Error(`Unknown SURFACE_ASSET_IDS: ${unknownIds.join(", ")}`);
}

const rebuiltTextures = [];
for (const product of productsToBuild) {
  console.log(`Building ${product.id}...`);
  rebuiltTextures.push(await buildProduct(product));
}

let textures = rebuiltTextures;
if (requestedIds.length > 0) {
  const manifestPath = path.join(manifestDir, "surface_manifest.json");
  const existingManifest = JSON.parse(await fs.readFile(manifestPath, "utf8"));
  const textureById = new Map(existingManifest.textures.map((texture) => [texture.id, texture]));
  for (const texture of rebuiltTextures) textureById.set(texture.id, texture);
  textures = products.map((product) => textureById.get(product.id));
  const missingIds = products.filter((product, index) => !textures[index]).map((product) => product.id);
  if (missingIds.length > 0) throw new Error(`Existing manifest is missing: ${missingIds.join(", ")}`);
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

await fs.writeFile(path.join(manifestDir, "surface_manifest.json"), `${JSON.stringify(manifest, null, 2)}\n`, "utf8");
await Promise.all([makeCatalogPreview(textures), makeRepeatPreview(textures)]);
console.log(JSON.stringify({ runtimeDestination, masterDestination, texture_count: textures.length }, null, 2));
