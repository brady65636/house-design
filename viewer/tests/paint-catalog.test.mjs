import assert from "node:assert/strict";
import fs from "node:fs/promises";
import path from "node:path";
import test from "node:test";
import sharp from "sharp";

const viewerRoot = path.resolve(import.meta.dirname, "..");
const catalog = JSON.parse(await fs.readFile(path.join(viewerRoot, "app", "data", "paintCatalog.json"), "utf8"));
const manifest = JSON.parse(await fs.readFile(path.join(viewerRoot, "public", "assets", "paints", "paint_manifest.json"), "utf8"));

function idFor(family, tone, finish) {
  return family.id_overrides?.[`${tone.id}_${finish.id}`]
    ?? `paint_${family.id}_${tone.id}_${finish.id}_01`;
}

function relativeLuminance(hex) {
  const channels = [1, 3, 5].map((offset) => Number.parseInt(hex.slice(offset, offset + 2), 16) / 255);
  const linear = channels.map((value) => value <= 0.04045 ? value / 12.92 : ((value + 0.055) / 1.055) ** 2.4);
  return linear[0] * 0.2126 + linear[1] * 0.7152 + linear[2] * 0.0722;
}

function rgb(hex) {
  return [1, 3, 5].map((offset) => Number.parseInt(hex.slice(offset, offset + 2), 16));
}

test("paint catalog expands to 60 stable, unique variants", () => {
  assert.equal(catalog.families.length, 10);
  assert.equal(catalog.tones.length, 3);
  assert.equal(catalog.finishes.length, 2);
  const ids = catalog.families.flatMap((family) =>
    catalog.tones.flatMap((tone) => catalog.finishes.map((finish) => idFor(family, tone, finish))),
  );
  assert.equal(ids.length, 60);
  assert.equal(new Set(ids).size, 60);
  assert.ok(ids.includes("paint_warm_cream_matte_01"));
  assert.ok(ids.includes("paint_light_greige_eggshell_01"));
  assert.deepEqual(new Set(manifest.variants.map((variant) => variant.id)), new Set(ids));
});

test("each family has strictly descending screen-relative luminance", () => {
  for (const family of catalog.families) {
    const values = catalog.tones.map((tone) => relativeLuminance(family.colors[tone.id]));
    assert.ok(values[0] > values[1] && values[1] > values[2], `${family.id}: ${values.join(", ")}`);
  }
});

test("critical neutral families preserve their intended undertone", () => {
  const color = (familyId, toneId) => catalog.families.find((family) => family.id === familyId).colors[toneId];
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

test("every paint variant is represented by one unambiguous catalogue standard", () => {
  for (const family of catalog.families) {
    for (const tone of catalog.tones) {
      assert.match(family.colors[tone.id], /^#[0-9A-F]{6}$/i, `${family.id}/${tone.id} needs one RGB standard`);
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
