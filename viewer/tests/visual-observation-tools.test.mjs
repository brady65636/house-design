import assert from "node:assert/strict";
import { readFile } from "node:fs/promises";
import test from "node:test";

const [observationSource, experienceSource, sceneManifest] = await Promise.all([
  readFile(new URL("../app/data/visualObservation.ts", import.meta.url), "utf8"),
  readFile(new URL("../app/components/RoomExperience.tsx", import.meta.url), "utf8"),
  readFile(new URL("../public/models/scene_manifest.json", import.meta.url), "utf8"),
]);
const scene = JSON.parse(sceneManifest);
const roomIds = new Set(scene.rooms.map((room) => room.id));
const openingIds = new Set(scene.openings.map((opening) => opening.id));

test("visual observation contracts keep evidence separate from design judgment", () => {
  assert.match(observationSource, /tool:\s*"observe_room"/);
  assert.match(observationSource, /tool:\s*"observe_home_harmony"/);
  assert.match(observationSource, /VISUAL_OBSERVATION_TOOL_DEFINITIONS/);
  assert.match(observationSource, /focus_target_ids/);
  assert.match(observationSource, /declaredCoverage/);
  assert.match(observationSource, /uncoveredTargetIds/);
  assert.match(observationSource, /invalidRequestedTargetIds/);
  assert.doesNotMatch(observationSource, /applyAsset|setCeilingPreset|update_scheme/);
});

test("whole-home transition evidence only references active-room openings", () => {
  const transitionBlock = observationSource.match(/HOME_HARMONY_TRANSITIONS:[\s\S]*?\n\];/)?.[0] ?? "";
  const referencedRoomIds = [...transitionBlock.matchAll(/(?:fromRoomId|toRoomId):\s*"([^"]+)"/g)]
    .map((match) => match[1]);
  const referencedOpeningIds = [...transitionBlock.matchAll(/openingId:\s*"([^"]+)"/g)]
    .map((match) => match[1]);

  assert.ok(referencedRoomIds.length >= 2, "transition graph should not be empty");
  assert.ok(referencedOpeningIds.length >= 1, "transition graph should include stable openings");
  referencedRoomIds.forEach((roomId) => assert.ok(roomIds.has(roomId), `unknown transition room: ${roomId}`));
  referencedOpeningIds.forEach((openingId) => assert.ok(openingIds.has(openingId), `unknown transition opening: ${openingId}`));
});

test("room renderer is a backend-command executor and exports JPEG evidence", () => {
  assert.match(experienceSource, /renderer worker/);
  assert.match(experienceSource, /render-sessions/);
  assert.match(experienceSource, /commands\/\$\{command\.id\}\/result/);
  assert.match(experienceSource, /command\.tool === "observe_room"/);
  assert.match(experienceSource, /observeRoom: captureRoomObservation/);
  assert.match(experienceSource, /observeHomeHarmony: captureHomeHarmony/);
  assert.match(experienceSource, /toDataURL\("image\/jpeg", 0\.9\)/);
  assert.match(experienceSource, /detailsVisibleValue = false/);
  assert.match(experienceSource, /preserveDrawingBuffer: true/);
  assert.doesNotMatch(experienceSource, /window\.houseDesignVisualTools/);
});

test("indirect daylight keeps shaded wall-paint previews free of a brown ground cast", () => {
  assert.match(experienceSource, /const INDIRECT_DAYLIGHT = \{/);
  assert.match(experienceSource, /sky: "#f3f4f2"/);
  assert.match(experienceSource, /ground: "#aaa7a1"/);
  assert.match(experienceSource, /intensity: 0\.55/);
  assert.doesNotMatch(experienceSource, /HemisphereLight\("#dce5e3", "#5a5146", 0\.3\)/);
});

test("wall paints anchor every wall face to its selected catalogue colour standard", () => {
  assert.match(experienceSource, /PAINT_APPEARANCE_CALIBRATION\.directLightShare/);
  assert.match(experienceSource, /PAINT_APPEARANCE_CALIBRATION\.colourStandardShare/);
  assert.match(experienceSource, /emissiveIntensity: 1/);
  assert.doesNotMatch(experienceSource, /emissiveIntensity: 0\.2/);
});
