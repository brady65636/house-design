import { mkdir, readFile, writeFile } from "node:fs/promises";
import path from "node:path";
import { fileURLToPath } from "node:url";
import sharp from "sharp";

const scriptDir = path.dirname(fileURLToPath(import.meta.url));
const viewerDir = path.resolve(scriptDir, "..");
const projectRoot = path.resolve(viewerDir, "..");
const cardLibraryPath = path.join(projectRoot, "asset_cards.json");
const outputCardLibraryPath = path.join(projectRoot, "output", "asset_cards.json");
const outputDir = path.join(viewerDir, "public", "assets", "asset-cards");
const ceilingCatalogPath = path.join(projectRoot, "output", "previews", "ceiling_catalog.png");

function previewMetadata(card) {
  const parameterizedPaint = card.category === "wall_paint" && card.objective_facts?.parameter_schema;
  const depiction = card.category === "ceiling"
    ? "geometry_preview"
    : parameterizedPaint
      ? "parameter_swatch"
      : "material_thumbnail";
  const alt = card.category === "ceiling"
    ? `${card.name_zh}的目录几何预览；用于理解构造，不是施工节点图。`
    : parameterizedPaint
      ? `${card.name_zh}的浅、中、深参数色阶预览；屏幕色不替代实体色卡。`
      : `${card.name_zh}的材质目录预览；最终选择仍需在房间实时渲染中验证。`;
  return {
    path: `viewer/public/assets/asset-cards/${card.id}_preview.webp`,
    media_type: "image/webp",
    depiction,
    alt,
  };
}

function sourceThumbnail(card) {
  if (card.category === "wallpaper") {
    return path.join(viewerDir, "public", "assets", "wallpapers", `${card.id}_thumb.webp`);
  }
  if (card.category === "wood_floor" || card.category === "tile") {
    return path.join(viewerDir, "public", "assets", "surfaces", `${card.id}_thumb.webp`);
  }
  if (card.category === "wall_paint" && !card.objective_facts?.parameter_schema) {
    return path.join(viewerDir, "public", "assets", "paints", `${card.id}_thumb.webp`);
  }
  return null;
}

function paintSwatchSvg(card) {
  const colors = card.objective_facts.tone_color_anchors;
  const labels = [["LIGHT", colors.light], ["MID", colors.mid], ["DEEP", colors.deep]];
  const panels = labels.map(([label, color], index) => {
    const x = 34 + index * 196;
    return `<g><rect x="${x}" y="74" width="174" height="310" rx="14" fill="${color}"/><text x="${x + 87}" y="422" text-anchor="middle" fill="#e7e3dc" font-family="Arial" font-size="19">${label}</text></g>`;
  }).join("");
  return Buffer.from(`<svg width="640" height="480" xmlns="http://www.w3.org/2000/svg"><rect width="640" height="480" fill="#20252a"/><text x="32" y="42" fill="#f2eee7" font-family="Arial" font-size="22">${card.id}</text>${panels}</svg>`);
}

async function renderCardPreview(card) {
  const outputPath = path.join(outputDir, `${card.id}_preview.webp`);
  if (card.category === "wall_paint" && card.objective_facts?.parameter_schema) {
    await sharp(paintSwatchSvg(card)).webp({ quality: 88 }).toFile(outputPath);
    return;
  }
  if (card.category === "ceiling") {
    const order = Number(card.objective_facts.order) - 1;
    const columns = [188, 440, 691];
    const rows = [40, 232, 423];
    await sharp(ceilingCatalogPath)
      .extract({ left: columns[order % 3], top: rows[Math.floor(order / 3)], width: 218, height: 192 })
      .resize(640, 480, { fit: "contain", background: "#20252a" })
      .webp({ quality: 88 })
      .toFile(outputPath);
    return;
  }
  const source = sourceThumbnail(card);
  if (!source) throw new Error(`No preview source rule for ${card.id}`);
  await sharp(source)
    .resize(640, 480, { fit: "contain", background: "#20252a" })
    .webp({ quality: 86 })
    .toFile(outputPath);
}

const library = JSON.parse(await readFile(cardLibraryPath, "utf8"));
const cards = Object.values(library.cards ?? {});
if (cards.length !== library.card_count) throw new Error("asset card count mismatch");
await mkdir(outputDir, { recursive: true });
for (const card of cards) {
  card.preview_image = previewMetadata(card);
  await renderCardPreview(card);
}
library.schema_version = "1.1.0";
const serialized = `${JSON.stringify(library, null, 2)}\n`;
await writeFile(cardLibraryPath, serialized, "utf8");
await writeFile(outputCardLibraryPath, serialized, "utf8");
process.stdout.write(`Generated ${cards.length} asset-card previews in ${outputDir}\n`);
