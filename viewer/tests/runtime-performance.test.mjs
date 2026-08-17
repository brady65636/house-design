import assert from "node:assert/strict";
import { readFile } from "node:fs/promises";
import test from "node:test";

const [experienceSource, bridgeWorkerSource, globalStyles] = await Promise.all([
  readFile(new URL("../app/components/RoomExperience.tsx", import.meta.url), "utf8"),
  readFile(new URL("../app/components/renderBridgeWorker.ts", import.meta.url), "utf8"),
  readFile(new URL("../app/globals.css", import.meta.url), "utf8"),
]);

test("interactive rendering keeps multipass GPU work within the intended budget", () => {
  assert.match(experienceSource, /MAX_RENDER_PIXEL_RATIO = 1\.25/);
  assert.match(experienceSource, /GTAO_RESOLUTION_SCALE = 0\.67/);
  assert.match(experienceSource, /THREE\.PCFSoftShadowMap/);
  assert.match(experienceSource, /renderer\.shadowMap\.autoUpdate = false/);
  assert.match(experienceSource, /renderer\.shadowMap\.needsUpdate = true/);
  assert.doesNotMatch(experienceSource, /THREE\.VSMShadowMap/);
});

test("repeated ceiling boxes are submitted as instanced batches", () => {
  assert.match(experienceSource, /new THREE\.InstancedMesh\(/);
  assert.match(experienceSource, /flushInstancedBoxes\(group\)/);
  assert.doesNotMatch(
    experienceSource,
    /new THREE\.Mesh\(new THREE\.BoxGeometry\(size\[0\], size\[1\], size\[2\]\)/,
  );
});

test("scheme application batches resource reconciliation and avoids duplicate initial work", () => {
  assert.match(experienceSource, /api\.applyAsset\(\[target\.id\], asset_id, assignment\.parameters \?\? null, false\)/);
  assert.match(experienceSource, /api\.reconcileAssets\(\)/);
  assert.match(experienceSource, /data\.scheme_id === currentSchemeRef\.current\?\.scheme_id/);
});

test("tour overlays stop re-blurring the moving WebGL frame", () => {
  assert.match(globalStyles, /\.room-experience\.tour-playing/);
  assert.match(globalStyles, /backdrop-filter:\s*none/);
});

test("render bridge polling does not duplicate its online refresh", () => {
  assert.doesNotMatch(bridgeWorkerSource, /\/heartbeat/);
  assert.match(bridgeWorkerSource, /setTimeout\(\(\) => void tick\(\), 2_000\)/);
});
