import assert from "node:assert/strict";
import { readFile } from "node:fs/promises";
import test from "node:test";

const cameraCatalog = JSON.parse(
  await readFile(new URL("../app/data/roomCameraTracksV4.json", import.meta.url), "utf8"),
);
const sceneManifest = JSON.parse(
  await readFile(new URL("../public/models/scene_manifest.json", import.meta.url), "utf8"),
);

const designTargetIds = new Set(sceneManifest.design_targets.map((target) => target.id));
const roomIds = new Set(sceneManifest.rooms.map((room) => room.id));

function viewDirection(frame) {
  return frame.target.map((value, index) => value - frame.position[index]);
}

function angleDegrees(first, second) {
  const firstLength = Math.hypot(...first);
  const secondLength = Math.hypot(...second);
  const cosine = first.reduce((sum, value, index) => sum + value * second[index], 0)
    / (firstLength * secondLength);
  return Math.acos(Math.max(-1, Math.min(1, cosine))) * 180 / Math.PI;
}

test("camera catalog matches the active v4 house and all design spaces", () => {
  assert.equal(cameraCatalog.houseId, sceneManifest.house_id);
  assert.equal(cameraCatalog.revision, "hard-finish-realism-pass-v5-wall-coverage");
  assert.equal(sceneManifest.geometry_revision, cameraCatalog.revision);
  assert.equal(cameraCatalog.coordinateSystem, "blender_z_up_meters");
  assert.equal(cameraCatalog.tracks.length, sceneManifest.rooms.length);
  assert.deepEqual(
    new Set(cameraCatalog.tracks.map((track) => track.roomId)),
    roomIds,
  );
  assert.equal(new Set(cameraCatalog.tracks.map((track) => track.id)).size, cameraCatalog.tracks.length);
});

test("every room track has deterministic anchors and valid human-eye keyframes", () => {
  const doorwayMargin = 0.25;
  for (const track of cameraCatalog.tracks) {
    assert.ok(track.durationMs >= 6500 && track.durationMs <= 22000, `${track.roomId}: duration`);
    assert.ok(track.keyframes.length >= 5, `${track.roomId}: keyframe count`);
    assert.deepEqual(track.keyframes[0].position, track.entryAnchor.position, `${track.roomId}: entry position`);
    assert.deepEqual(track.keyframes[0].target, track.entryAnchor.target, `${track.roomId}: entry target`);
    assert.deepEqual(track.keyframes.at(-1).position, track.exitAnchor.position, `${track.roomId}: exit position`);
    assert.deepEqual(track.keyframes.at(-1).target, track.exitAnchor.target, `${track.roomId}: exit target`);
    assert.equal(track.keyframes[0].progress, 0, `${track.roomId}: starts at zero`);
    assert.equal(track.keyframes.at(-1).progress, 1, `${track.roomId}: ends at one`);

    let previousProgress = -1;
    const [x1, y1, x2, y2] = track.roomRect;
    for (const frame of track.keyframes) {
      assert.ok(frame.progress > previousProgress, `${track.roomId}: progress order`);
      previousProgress = frame.progress;
      assert.ok(frame.fov >= 46 && frame.fov <= 58, `${track.roomId}/${frame.label}: fov`);
      assert.ok(frame.position[2] >= 1.54 && frame.position[2] <= 1.63, `${track.roomId}/${frame.label}: eye height`);
      assert.ok(frame.position[0] >= x1 - doorwayMargin && frame.position[0] <= x2 + doorwayMargin, `${track.roomId}/${frame.label}: x bounds`);
      assert.ok(frame.position[1] >= y1 - doorwayMargin && frame.position[1] <= y2 + doorwayMargin, `${track.roomId}/${frame.label}: y bounds`);
      assert.ok(frame.intent && frame.label && frame.description, `${track.roomId}/${frame.label}: narrative metadata`);
      const direction = viewDirection(frame);
      const pitch = Math.asin(direction[2] / Math.hypot(...direction)) * 180 / Math.PI;
      assert.ok(Math.abs(pitch) <= 35, `${track.roomId}/${frame.label}: pitch ${pitch.toFixed(1)}°`);
    }
    for (let index = 1; index < track.keyframes.length; index += 1) {
      const turn = angleDegrees(
        viewDirection(track.keyframes[index - 1]),
        viewDirection(track.keyframes[index]),
      );
      assert.ok(turn <= 75, `${track.roomId}: turn ${turn.toFixed(1)}° before ${track.keyframes[index].label}`);
    }
  }
});

test("each room track covers every wall, floor and ceiling design target", () => {
  for (const track of cameraCatalog.tracks) {
    const room = sceneManifest.rooms.find((candidate) => candidate.id === track.roomId);
    assert.ok(room, `${track.roomId}: room missing from manifest`);
    assert.deepEqual(
      new Set(track.surfaceTargets.walls),
      new Set(room.wall_face_ids),
      `${track.roomId}: camera wall targets must equal manifest wall targets`,
    );
    const declaredTargets = [
      track.surfaceTargets.floor,
      track.surfaceTargets.ceiling,
      ...track.surfaceTargets.walls,
    ].filter(Boolean);
    const coveredTargets = new Set(track.keyframes.flatMap((frame) => frame.focusTargetIds));

    for (const targetId of declaredTargets) {
      assert.ok(designTargetIds.has(targetId), `${track.roomId}: unknown target ${targetId}`);
      assert.ok(coveredTargets.has(targetId), `${track.roomId}: uncovered target ${targetId}`);
    }
  }
});
