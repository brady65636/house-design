import assert from "node:assert/strict";
import { access, readFile } from "node:fs/promises";
import path from "node:path";
import test from "node:test";

const projectRoot = path.resolve(import.meta.dirname, "..", "..");
const floorCatalog = JSON.parse(await readFile(path.join(projectRoot, "viewer/app/data/floorCatalog.json"), "utf8"));
const tileCatalog = JSON.parse(await readFile(path.join(projectRoot, "viewer/app/data/tileCatalog.json"), "utf8"));
const ceilingCatalog = JSON.parse(await readFile(path.join(projectRoot, "viewer/app/data/ceilingCatalog.json"), "utf8"));
const manifest = JSON.parse(await readFile(path.join(projectRoot, "viewer/public/assets/surfaces/texture_manifest.json"), "utf8"));

test("surface catalogs contain the approved complete representative set", () => {
  assert.equal(floorCatalog.products.length, 6);
  assert.equal(tileCatalog.products.length, 8);
  assert.equal(ceilingCatalog.products.length, 5);
  assert.equal(new Set([...floorCatalog.products, ...tileCatalog.products, ...ceilingCatalog.products].map((item) => item.id)).size, 19);
});

test("floor and tile products preserve physical scale and layout metadata", () => {
  for (const product of [...floorCatalog.products, ...tileCatalog.products]) {
    assert.match(product.id, /^(floor|tile)_[a-z0-9_]+_01$/);
    assert.equal(product.repeat_size_m.length, 2);
    assert.ok(product.repeat_size_m.every((value) => value > 0));
    assert.ok(product.supported_layouts.length > 0);
    assert.ok(product.roughness_mean >= 0.45 && product.roughness_mean <= 0.85);
    assert.ok(product.normal_scale > 0 && product.normal_scale <= 0.35);
  }
});

test("generated PBR manifest covers every floor and tile with seamless runtime maps", async () => {
  assert.equal(manifest.texture_count, 14);
  assert.deepEqual(manifest.category_counts, { wood_floor: 6, tile: 8 });
  const expectedIds = new Set([...floorCatalog.products, ...tileCatalog.products].map((item) => item.id));
  assert.deepEqual(new Set(manifest.textures.map((item) => item.id)), expectedIds);
  for (const texture of manifest.textures) {
    assert.ok(texture.seam_mae_source_pixels.horizontal <= 0.01, `${texture.id} horizontal seam`);
    assert.ok(texture.seam_mae_source_pixels.vertical <= 0.01, `${texture.id} vertical seam`);
    for (const filename of Object.values(texture.runtime_maps)) {
      await access(path.join(projectRoot, "viewer/public/assets/surfaces", filename));
    }
    for (const filename of Object.values(texture.master_maps)) {
      await access(path.join(projectRoot, filename));
    }
  }
});

test("ceiling presets encode constructible dimensions and wet-room applicability", () => {
  const modular = ceilingCatalog.products.find((product) => product.id === "ceiling_kitchen_bath_panel_01");
  assert.deepEqual(modular.module_size_mm, [600, 1200]);
  assert.ok(modular.suitable_rooms.includes("kitchen"));
  assert.ok(modular.suitable_rooms.includes("bathroom"));
  for (const product of ceilingCatalog.products) {
    assert.ok(product.drop_height_mm >= 20 && product.drop_height_mm <= 240);
  }
});
