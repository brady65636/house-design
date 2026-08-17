import assert from "node:assert/strict";
import { access, readFile } from "node:fs/promises";
import path from "node:path";
import test from "node:test";
import sharp from "sharp";

const projectRoot = path.resolve(import.meta.dirname, "..", "..");
const floorCatalog = JSON.parse(await readFile(path.join(projectRoot, "viewer/app/data/floorCatalog.json"), "utf8"));
const tileCatalog = JSON.parse(await readFile(path.join(projectRoot, "viewer/app/data/tileCatalog.json"), "utf8"));
const ceilingCatalog = JSON.parse(await readFile(path.join(projectRoot, "viewer/app/data/ceilingCatalog.json"), "utf8"));
const configurations = JSON.parse(await readFile(path.join(projectRoot, "viewer/app/data/designConfigurations.json"), "utf8"));
const manifest = JSON.parse(await readFile(path.join(projectRoot, "viewer/public/assets/manifests/surface_manifest.json"), "utf8"));

test("surface catalogs contain the approved complete representative set", () => {
  assert.equal(floorCatalog.products.length, 13);
  assert.equal(tileCatalog.products.length, 21);
  assert.equal(ceilingCatalog.products.length, 9);
  assert.equal(new Set([...floorCatalog.products, ...tileCatalog.products, ...ceilingCatalog.products].map((item) => item.id)).size, 43);
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
  assert.equal(manifest.texture_count, 34);
  assert.deepEqual(manifest.category_counts, { wood_floor: 13, tile: 21 });
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

test("strictly periodic checker source bypasses generic edge averaging", () => {
  const checker = tileCatalog.products.find((product) => product.id === "tile_checker_black_ivory_01");
  assert.equal(checker.synthetic_profile, "checker_black_ivory");
  assert.equal(checker.already_seamless, true);
  assert.equal(checker.checker_colors.length, 2);
});

test("fluted relief tile uses deterministic unlit geometry-derived PBR", () => {
  const fluted = tileCatalog.products.find((product) => product.id === "tile_ivory_fluted_relief_01");
  assert.equal(fluted.synthetic_profile, "ivory_fluted_relief");
  assert.equal(fluted.already_seamless, true);
  assert.ok(fluted.flute_count >= 12);
  assert.equal(fluted.surface_profile, "relief_ceramic");
});

test("new ceiling presets add timber, coffer, raw-concrete and curved languages", () => {
  assert.deepEqual(
    new Set(ceilingCatalog.products.map((product) => product.preset)),
    new Set([
      "flat", "perimeter_step", "perimeter_cove", "floating_shadow_gap", "modular_panel",
      "timber_slatted", "shallow_coffer_grid", "exposed_concrete_track", "curved_cove",
    ]),
  );
});

test("D2 additions cover cork, cool fine modules and deep quiet tile without adding a category", () => {
  const cork = floorCatalog.products.find((product) => product.id === "floor_natural_cork_01");
  assert.equal(cork.material_type, "cork");
  assert.equal(cork.surface_profile, "natural_cork");
  const newTiles = tileCatalog.products.filter((product) => product.order >= 19);
  assert.deepEqual(new Set(newTiles.map((product) => product.synthetic_profile)), new Set([
    "cool_finger_mosaic", "smoke_penny_mosaic", "deep_matte_monochrome",
  ]));
  assert.ok(newTiles.every((product) => product.design_roles.length >= 2));
});

test("light wood base colours stay neutral enough for bright low-yellow schemes", async () => {
  for (const assetId of ["floor_ash_maple_light_matte_01", "floor_light_oak_matte_01"]) {
    const product = floorCatalog.products.find((candidate) => candidate.id === assetId);
    assert.match(product.runtime_color_multiplier, /^#[0-9a-f]{6}$/i);
    const stats = await sharp(path.join(
      projectRoot,
      "viewer/public/assets/surfaces",
      `${assetId}_basecolor_web.jpg`,
    )).stats();
    const [red, , blue] = stats.channels;
    assert.ok(red.mean - blue.mean < 32, `${assetId} is still too yellow/orange`);
  }
});

test("partial surface builds validate requested IDs without rejecting a full build", async () => {
  const source = await readFile(path.join(projectRoot, "viewer/scripts/build-surface-pbr.mjs"), "utf8");
  assert.match(source, /requestedIds\.length > 0 && productsToBuild\.length !== requestedIdSet\.size/);
});

test("relationship systems remain configurations rather than a sixth asset category", () => {
  assert.equal(configurations.systems.length, 4);
  assert.deepEqual(new Set(configurations.systems.map((system) => system.id)), new Set([
    "skirting_system", "joint_grout_system", "threshold_transition_system", "edge_profile_system",
  ]));
  assert.match(configurations.notice, /不是.*第六类 Asset/);
});
