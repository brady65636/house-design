import assert from "node:assert/strict";
import fs from "node:fs/promises";
import path from "node:path";
import test from "node:test";
import sharp from "sharp";

const viewerRoot = path.resolve(import.meta.dirname, "..");
const catalog = JSON.parse(await fs.readFile(path.join(viewerRoot, "app", "data", "paintCatalog.json"), "utf8"));
const manifest = JSON.parse(await fs.readFile(path.join(viewerRoot, "public", "assets", "manifests", "paint_manifest.json"), "utf8"));

function relativeLuminance(hex) {
  const channels = [1, 3, 5].map((offset) => Number.parseInt(hex.slice(offset, offset + 2), 16) / 255);
  const linear = channels.map((value) => value <= 0.04045 ? value / 12.92 : ((value + 0.055) / 1.055) ** 2.4);
  return linear[0] * 0.2126 + linear[1] * 0.7152 + linear[2] * 0.0722;
}

function rgb(hex) {
  return [1, 3, 5].map((offset) => Number.parseInt(hex.slice(offset, offset + 2), 16));
}

test("paint catalog exposes one Asset per paint plus three specialty coatings", () => {
  assert.equal(catalog.paints.length, 10);
  assert.equal(catalog.tones.length, 3);
  assert.equal(catalog.finishes.length, 2);
  const ids = catalog.paints.map((paint) => paint.asset_id);
  assert.equal(ids.length, 10);
  assert.equal(new Set(ids).size, 10);
  assert.ok(ids.includes("paint_warm_white_01"));
  assert.ok(ids.includes("paint_greige_01"));
  assert.ok(!ids.includes("paint_warm_cream_matte_01"));
  assert.equal(catalog.specialty_products.length, 3);
  const specialtyIds = catalog.specialty_products.map((product) => product.id);
  assert.equal(new Set([...ids, ...specialtyIds]).size, 13);
  assert.deepEqual(new Set(manifest.variants.map((variant) => variant.id)), new Set([...ids, ...specialtyIds]));
  assert.equal(manifest.asset_count, 13);
  assert.equal(manifest.parameterized_asset_count, 10);
  assert.equal(manifest.standard_variant_count, 10);
  assert.equal(manifest.specialty_variant_count, 3);
});

test("lightness, saturation and finish are parameters rather than Asset IDs", () => {
  assert.deepEqual(catalog.parameter_schema.lightness.values, ["light", "mid", "deep"]);
  assert.equal(catalog.parameter_schema.saturation.minimum, 0.35);
  assert.equal(catalog.parameter_schema.saturation.maximum, 1.25);
  assert.deepEqual(catalog.parameter_schema.finish.values, ["matte", "eggshell"]);
  for (const paint of catalog.paints) {
    assert.doesNotMatch(paint.asset_id, /_(light|mid|deep)_(matte|eggshell)_/);
  }
});

test("each paint has strictly descending screen-relative luminance", () => {
  for (const paint of catalog.paints) {
    const values = catalog.tones.map((tone) => relativeLuminance(paint.colors[tone.id]));
    assert.ok(values[0] > values[1] && values[1] > values[2], `${paint.id}: ${values.join(", ")}`);
  }
});

test("critical neutral paints preserve their intended undertone", () => {
  const color = (paintId, toneId) => catalog.paints.find((paint) => paint.id === paintId).colors[toneId];
  const [warmR, warmG, warmB] = rgb(color("warm_white", "light"));
  assert.ok(warmR > warmG && warmG > warmB, "warm white remains gently warm");
  assert.ok(warmR - warmB <= 12, "warm white must not become visibly yellow");

  const [coolR, coolG, coolB] = rgb(color("cool_white", "light"));
  assert.ok(coolB > coolG && coolG > coolR, "cool white remains gently cool");
  assert.ok(coolB - coolR <= 12, "cool white must not become visibly blue");

  for (const tone of ["light", "mid", "deep"]) {
    const [greyR, greyG, greyB] = rgb(color("charcoal", tone));
    assert.ok(Math.max(greyR, greyG, greyB) - Math.min(greyR, greyG, greyB) <= 2, `${tone} grey must remain neutral`);
  }

  const [beigeR, beigeG, beigeB] = rgb(color("greige", "light"));
  assert.ok(beigeR > beigeG && beigeG > beigeB, "greige remains a restrained beige-neutral");
  assert.ok(beigeR - beigeB <= 14, "greige must not become yellow-beige");
});

test("each paint keeps three calibrated lightness anchor colours", () => {
  for (const paint of catalog.paints) {
    for (const tone of catalog.tones) {
      assert.match(paint.colors[tone.id], /^#[0-9A-F]{6}$/i, `${paint.id}/${tone.id} needs one RGB standard`);
    }
  }
});

test("matte and eggshell finish envelopes remain physically distinct", () => {
  const matte = catalog.finishes.find((finish) => finish.id === "matte");
  const eggshell = catalog.finishes.find((finish) => finish.id === "eggshell");
  assert.ok(matte.roughness_range[0] > eggshell.roughness_range[1]);
  assert.ok(matte.normal_scale > 0 && matte.normal_scale < 0.1);
  assert.ok(eggshell.normal_scale > 0 && eggshell.normal_scale < 0.1);
});

test("all four shared PBR maps are genuine 4K square textures", async () => {
  const files = [
    "paint_micro_basecolor_4k.jpg",
    "paint_micro_normal_gl_4k.jpg",
    "paint_micro_roughness_matte_4k.jpg",
    "paint_micro_roughness_eggshell_4k.jpg",
  ];
  for (const filename of files) {
    const metadata = await sharp(path.join(viewerRoot, "public", "assets", "paints", filename)).metadata();
    assert.equal(metadata.width, 4096, filename);
    assert.equal(metadata.height, 4096, filename);
  }
});

test("specialty coatings have objective systems and dedicated 4K PBR maps", async () => {
  assert.deepEqual(
    new Set(catalog.specialty_products.map((product) => product.coating_system)),
    new Set(["limewash", "clay_plaster", "marmorino"]),
  );
  for (const product of catalog.specialty_products) {
    assert.ok(product.design_roles.length >= 2);
    assert.ok(product.relationship_tags.length >= 3);
    for (const suffix of ["basecolor_4k.jpg", "normal_gl_4k.jpg", "roughness_4k.jpg"]) {
      const metadata = await sharp(path.join(viewerRoot, "public", "assets", "paints", `${product.id}_${suffix}`)).metadata();
      assert.deepEqual([metadata.width, metadata.height], [4096, 4096]);
    }
  }
});
