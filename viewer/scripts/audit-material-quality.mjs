import fs from "node:fs/promises";
import path from "node:path";
import { fileURLToPath } from "node:url";
import sharp from "sharp";

const scriptDir = path.dirname(fileURLToPath(import.meta.url));
const viewerDir = path.resolve(scriptDir, "..");
const projectRoot = path.resolve(viewerDir, "..");
const paintDir = path.join(viewerDir, "public", "assets", "paints");
const reportPath = path.join(projectRoot, "output", "material_quality_report.json");

async function rgb(filename) {
  const { data, info } = await sharp(path.join(paintDir, filename))
    .resize(512, 512, { fit: "fill" })
    .removeAlpha()
    .raw()
    .toBuffer({ resolveWithObject: true });
  return { data, info };
}

function stats(values) {
  let sum = 0;
  for (const value of values) sum += value;
  const mean = sum / values.length;
  let variance = 0;
  for (const value of values) variance += (value - mean) ** 2;
  return { mean, std: Math.sqrt(variance / values.length) };
}

async function baseColorStats() {
  const { data } = await rgb("paint_micro_basecolor_4k.jpg");
  const luminance = new Float32Array(data.length / 3);
  for (let i = 0; i < luminance.length; i += 1) {
    luminance[i] = (data[i * 3] * 0.2126 + data[i * 3 + 1] * 0.7152 + data[i * 3 + 2] * 0.0722) / 255;
  }
  return stats(luminance);
}

async function normalStats() {
  const { data } = await rgb("paint_micro_normal_gl_4k.jpg");
  const xy = new Float32Array(data.length / 3);
  for (let i = 0; i < xy.length; i += 1) {
    const x = data[i * 3] / 255 * 2 - 1;
    const y = data[i * 3 + 1] / 255 * 2 - 1;
    xy[i] = Math.hypot(x, y);
  }
  return stats(xy);
}

async function roughnessStats(filename) {
  const { data } = await rgb(filename);
  const values = new Float32Array(data.length / 3);
  for (let i = 0; i < values.length; i += 1) values[i] = data[i * 3] / 255;
  return stats(values);
}

const metrics = {
  paint_basecolor: await baseColorStats(),
  paint_normal_xy: await normalStats(),
  paint_roughness_matte: await roughnessStats("paint_micro_roughness_matte_4k.jpg"),
  paint_roughness_eggshell: await roughnessStats("paint_micro_roughness_eggshell_4k.jpg"),
};

const checks = [
  { id: "paint_basecolor_multiscale_variation", passed: metrics.paint_basecolor.std >= 0.006 && metrics.paint_basecolor.std <= 0.03, value: metrics.paint_basecolor.std },
  { id: "paint_normal_readable_not_plaster", passed: metrics.paint_normal_xy.mean >= 0.06 && metrics.paint_normal_xy.mean <= 0.20, value: metrics.paint_normal_xy.mean },
  { id: "paint_matte_roughness_variation", passed: metrics.paint_roughness_matte.std >= 0.018, value: metrics.paint_roughness_matte.std },
  { id: "paint_eggshell_roughness_variation", passed: metrics.paint_roughness_eggshell.std >= 0.025, value: metrics.paint_roughness_eggshell.std },
  { id: "paint_finishes_remain_distinct", passed: metrics.paint_roughness_matte.mean - metrics.paint_roughness_eggshell.mean >= 0.18, value: metrics.paint_roughness_matte.mean - metrics.paint_roughness_eggshell.mean },
];

const report = {
  schema_version: "1.0.0",
  generated_at: new Date().toISOString(),
  scope: "paint_pbr_runtime_maps",
  metrics,
  checks,
  passed: checks.every((check) => check.passed),
};
await fs.writeFile(reportPath, `${JSON.stringify(report, null, 2)}\n`, "utf8");
console.log(JSON.stringify(report, null, 2));
if (!report.passed) process.exitCode = 1;
