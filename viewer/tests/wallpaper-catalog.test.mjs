import assert from "node:assert/strict";
import fs from "node:fs/promises";
import path from "node:path";
import test from "node:test";
import { fileURLToPath } from "node:url";
import sharp from "sharp";

const testDir = path.dirname(fileURLToPath(import.meta.url));
const viewerDir = path.resolve(testDir, "..");
const projectRoot = path.resolve(viewerDir, "..");
const catalog = JSON.parse(await fs.readFile(path.join(viewerDir, "app", "data", "wallpaperCatalog.json"), "utf8"));
const manifest = JSON.parse(await fs.readFile(path.join(viewerDir, "public", "assets", "wallpapers", "texture_manifest.json"), "utf8"));

test("wallpaper catalog contains eight original, stable collections", () => {
  assert.equal(catalog.products.length, 8);
  assert.equal(new Set(catalog.products.map((product) => product.id)).size, 8);
  assert.equal(new Set(catalog.products.map((product) => product.family)).size, 8);
  assert.deepEqual(catalog.products.map((product) => product.order), [1, 2, 3, 4, 5, 6, 7, 8]);
  assert.equal(catalog.source_and_license.license, "project_owned");
});

test("catalog records physical repeat, installation match and intended use", () => {
  const modes = new Set(catalog.products.map((product) => product.match_type));
  assert.deepEqual(modes, new Set(["random_match", "straight_match", "half_drop_match", "panel_mural"]));
  for (const product of catalog.products) {
    assert.equal(product.repeat_size_m.length, 2);
    assert.ok(product.repeat_size_m.every((value) => value > 0));
    assert.ok(product.recommended_use.length >= 1);
  }
  const mural = catalog.products.find((product) => product.texture_mode === "panel_mural");
  assert.deepEqual(mural.repeat_size_m, [4.4, 2.8]);
  assert.equal(mural.panel_count, 5);
});

test("every approved source image and generated PBR set exists at the declared resolution", async () => {
  assert.equal(manifest.texture_count, 8);
  assert.deepEqual(
    manifest.textures.map((textureInfo) => textureInfo.id),
    catalog.products.map((product) => product.id),
  );
  for (const product of catalog.products) {
    await fs.access(path.join(projectRoot, product.source_file));
    const textureInfo = manifest.textures.find((item) => item.id === product.id);
    assert.ok(textureInfo);
    assert.deepEqual(textureInfo.resolution, product.output_resolution);
    for (const relativePath of Object.values(textureInfo.master_maps)) {
      await fs.access(path.join(projectRoot, relativePath));
    }
    const metadata = await sharp(path.join(projectRoot, textureInfo.master_maps.base_color)).metadata();
    assert.deepEqual([metadata.width, metadata.height], product.output_resolution);
    for (const filename of Object.values(textureInfo.runtime_maps)) {
      await fs.access(path.join(viewerDir, "public", "assets", "wallpapers", filename));
    }
  }
});

test("repeating textures have exact generated edge continuity", () => {
  for (const textureInfo of manifest.textures.filter((item) => item.texture_mode === "repeat")) {
    assert.equal(textureInfo.seam_mae_source_pixels.horizontal, 0, textureInfo.id);
    assert.equal(textureInfo.seam_mae_source_pixels.vertical, 0, textureInfo.id);
  }
});

test("runtime wallpaper payload contains only optimized on-demand maps", async () => {
  const directory = path.join(viewerDir, "public", "assets", "wallpapers");
  const entries = await fs.readdir(directory, { withFileTypes: true });
  const files = entries.filter((entry) => entry.isFile());
  assert.equal(files.some((entry) => /_(2k|4k)\./.test(entry.name)), false);
  let totalBytes = 0;
  for (const entry of files) totalBytes += (await fs.stat(path.join(directory, entry.name))).size;
  assert.ok(totalBytes < 24 * 1024 * 1024, `runtime wallpaper payload is ${(totalBytes / 1024 / 1024).toFixed(2)} MB`);
});
