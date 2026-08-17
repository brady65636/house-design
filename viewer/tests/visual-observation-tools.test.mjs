import assert from "node:assert/strict";
import { readFile } from "node:fs/promises";
import test from "node:test";

const [observationSource, experienceSource, heroSurfaceSource, wallpaperCatalogSource, surfaceCatalogSource, sceneManifest] = await Promise.all([
  readFile(new URL("../app/data/visualObservation.ts", import.meta.url), "utf8"),
  readFile(new URL("../app/components/RoomExperience.tsx", import.meta.url), "utf8"),
  readFile(new URL("../app/components/heroLivingScene.ts", import.meta.url), "utf8"),
  readFile(new URL("../app/data/wallpaperCatalog.ts", import.meta.url), "utf8"),
  readFile(new URL("../app/data/surfaceCatalog.ts", import.meta.url), "utf8"),
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
  assert.match(observationSource, /plannedCoverage/);
  assert.match(experienceSource, /verifiedCoverage/);
  assert.match(experienceSource, /evidenceLevel: "pixel_verified_coverage"/);
  assert.doesNotMatch(observationSource, /declaredCoverage/);
  assert.match(observationSource, /invalidRequestedTargetIds/);
  assert.match(observationSource, /wallTargetView\(track, targetId\)/);
  assert.match(observationSource, /ceilingTargetView\(track, track\.surfaceTargets\.ceiling\)/);
  assert.match(observationSource, /topologyAnomalyTargetIds/);
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
  assert.match(observationSource, /openingGeometry\(openingId\)/);
  assert.match(observationSource, /wall_core_center_coordinate/);
  assert.match(observationSource, /openingSideView\("master_dressing", "opening_master_dressing"/);
  assert.match(observationSource, /Opening \$\{openingId\} is not adjacent to observation room \$\{roomId\}/);
  assert.match(observationSource, /openingSideView\("master_dressing", "opening_master_suite_door"/);
  assert.doesNotMatch(transitionBlock, /openingSideView\("master_bedroom", "opening_master_suite_door"/);
  assert.doesNotMatch(transitionBlock, /fromProgress|toProgress/);
});

test("pixel visibility pass measures rendered targets behind real occluders", () => {
  assert.match(experienceSource, /const visibilityRenderTarget = new THREE\.WebGLRenderTarget/);
  assert.match(experienceSource, /renderer\.render\(scene, camera\)/);
  assert.match(experienceSource, /renderer\.readRenderTargetPixels\(/);
  assert.match(experienceSource, /targetIdForVisibilityMesh/);
  assert.match(experienceSource, /pixelRatio >= MIN_TARGET_PIXEL_RATIO/);
  assert.match(experienceSource, /scene\.background = new THREE\.Color\(0xff00ff\)/);
  assert.match(experienceSource, /occluderPixelRatio/);
  assert.match(experienceSource, /Math\.min\(boundingBox\.width, boundingBox\.height\) >= MIN_TARGET_BOUNDING_DIMENSION/);
  assert.match(experienceSource, /uncoveredTargetIds\.length === 0 && invalidViewIds\.length === 0/);
  assert.match(experienceSource, /visibilityRenderTarget\.dispose\(\)/);
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

test("evidence passes through an offscreen RenderPass+OutputPass chain so tone mapping matches the live viewer", () => {
  // A bare renderer.render() into a render target disables material tone
  // mapping and forces linear output (WebGLPrograms gates on
  // currentRenderTarget === null). Evidence must therefore go through an
  // OutputPass, which applies ACES + sRGB in its own shader.
  assert.match(experienceSource, /const evidenceComposer = new EffectComposer\(renderer, evidenceRenderTarget\)/);
  assert.match(experienceSource, /evidenceComposer\.renderToScreen = false/);
  assert.match(experienceSource, /evidenceComposer\.addPass\(new RenderPass\(scene, camera\)\)/);
  assert.match(experienceSource, /evidenceComposer\.addPass\(new OutputPass\(\)\)/);
  // Evidence is read back from the composer's offscreen buffer, never from the
  // live canvas (which could hand back a stale frame in a hidden tab).
  assert.match(experienceSource, /const \{ readBuffer \} = evidenceComposer/);
  assert.match(experienceSource, /readRenderTargetPixels\(readBuffer, 0, 0, width, height, samples\)/);
  assert.match(experienceSource, /HalfFloatType/);
  // Guard against regressing to the direct-render path (the original bug).
  assert.doesNotMatch(experienceSource, /setRenderTarget\(evidenceRenderTarget\)/);
  assert.doesNotMatch(experienceSource, /evidenceRenderTarget\.colorSpace/);
});

test("observe_room keeps true whole-scene views and adds a clearly-labelled floor-isolation supplement", () => {
  // The plan views must stay unscoped: a small room's track intentionally reads
  // e.g. "玄关地面和公共区材料的衔接", so the whole house must remain visible.
  assert.match(experienceSource, /const views = await captureInspectionViews\([\s\S]*?plan\.roomId,[\s\S]*?plan\.views,[\s\S]*?false,[\s\S]*?plan\.expectedTargetIds/);
  // The scoped floor supplement is appended, marked floor_isolated so a consumer
  // (Critic/grader) can tell it is NOT a true whole-scene capture.
  assert.match(experienceSource, /purpose: "floor_isolated"/);
  assert.match(experienceSource, /label: "地面隔离 · 仅本房间地面"/);
  assert.match(experienceSource, /floor_isolated_\$\{Math\.round\(floorKeyframe\.progress \* 1000\)\}/);
  assert.match(experienceSource, /const allViews = \[\.\.\.views, floorIsolated\]/);
});

test("whole-home evidence uses computed room overviews and verifies both sides of every opening", () => {
  assert.match(observationSource, /roomInteriorSweepViews\(track\)/);
  assert.match(observationSource, /interior_sweep_/);
  assert.match(experienceSource, /const scoreCandidate = \(candidate: VisualImage\)/);
  assert.match(experienceSource, /dominancePenalty/);
  assert.match(experienceSource, /occluderPenalty/);
  assert.match(experienceSource, /roomHeroDiagnostics/);
  assert.match(experienceSource, /occluderPixelRatio <= 0\.72/);
  assert.match(experienceSource, /candidatePassesHeroGate/);
  assert.match(experienceSource, /const seesBothSides = \(image: VisualImage\) => transitionTargets\.every/);
  assert.match(experienceSource, /pair\.status === "ready"/);
  assert.match(experienceSource, /invalidHeroRoomIds/);
  assert.match(observationSource, /HOME_HERO_MAX_CANDIDATES = 5/);
  assert.match(experienceSource, /HOME_HERO_WIDTH = 640/);
  assert.match(experienceSource, /captureDiagnostics/);
});

test("every room camera wall target is adjacent to a declared room topology zone", async () => {
  const tracks = JSON.parse(await readFile(new URL("../app/data/roomCameraTracksV4.json", import.meta.url), "utf8"));
  const tolerance = 0.3;
  for (const track of tracks.tracks) {
    const room = scene.rooms.find((candidate) => candidate.id === track.roomId);
    const rects = room.topology_rects?.length ? room.topology_rects : [track.roomRect];
    for (const targetId of track.surfaceTargets.walls) {
      const face = scene.wall_faces.find((candidate) => candidate.id === targetId);
      const segmentCenter = (face.start + face.end) / 2;
      const adjacent = rects.some(([x1, y1, x2, y2]) => (
        face.axis === "X"
          ? segmentCenter >= x1 - tolerance && segmentCenter <= x2 + tolerance
            && Math.min(Math.abs(face.coordinate - y1), Math.abs(face.coordinate - y2)) <= tolerance
          : segmentCenter >= y1 - tolerance && segmentCenter <= y2 + tolerance
            && Math.min(Math.abs(face.coordinate - x1), Math.abs(face.coordinate - x2)) <= tolerance
      ));
      assert.equal(adjacent, true, `${track.roomId}/${targetId} must touch a declared topology zone`);
    }
  }
});

test("flat GLB ceilings receive the same calibrated near-white finish as generated ceiling presets", () => {
  assert.match(experienceSource, /function makeCeilingFinishMaterial/);
  assert.match(experienceSource, /CEILING_APPEARANCE_CALIBRATION\.materialColourShare/);
  assert.match(experienceSource, /object\.userData\.surface_role === "ceiling"/);
  assert.match(experienceSource, /object\.material = flatCeilingMaterial/);
  assert.match(experienceSource, /object\.userData\.currentAssetId = "ceiling_flat_01"/);
  assert.match(experienceSource, /flatCeilingMaterial\.dispose\(\)/);
});

test("room switches remount the tour toggle with the active room's accessible name", () => {
  assert.match(experienceSource, /key=\{`tour-toggle-\$\{activeTrack\.roomId\}`\}/);
  assert.match(experienceSource, /`播放\$\{activeTrack\.roomLabel\}导览`/);
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

test("wallpapers keep one printed colour standard across differently oriented wall faces", () => {
  assert.match(wallpaperCatalogSource, /directionalLightShare: 0\.22/);
  assert.match(wallpaperCatalogSource, /printedColourShare: 0\.78/);
  assert.match(experienceSource, /WALLPAPER_APPEARANCE_CALIBRATION\.directionalLightShare/);
  assert.match(experienceSource, /WALLPAPER_APPEARANCE_CALIBRATION\.printedColourShare/);
  assert.match(heroSurfaceSource, /material\.emissiveMap = color/);
  assert.match(heroSurfaceSource, /material\.emissiveMap = null/);
});

test("wall tiles share one calibrated material colour across perpendicular wet-room walls", () => {
  assert.match(surfaceCatalogSource, /directionalLightShare: 0\.45/);
  assert.match(surfaceCatalogSource, /materialColourShare: 0\.55/);
  assert.match(experienceSource, /wallVariant\.map = map/);
  assert.match(experienceSource, /wallVariant\.emissiveMap = map/);
  assert.match(experienceSource, /typeof mesh\.userData\.wall_face_id === "string"/);
  assert.match(experienceSource, /wallVariant instanceof THREE\.Material/);
  assert.match(experienceSource, /wallVariant\.emissiveMap = null/);
});
