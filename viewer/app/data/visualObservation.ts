import {
  getRoomCameraTrack,
  ROOM_CAMERA_TRACKS,
  type RoomCameraKeyframe,
  type RoomCameraTrack,
} from "./roomCameraTracksV4";
import sceneManifest from "../../public/models/scene_manifest.json";

/**
 * These plans are evidence plans, not aesthetic judgments.  The visual model
 * receives the rendered images plus this grounding data, then makes its own
 * structured critique.  Keeping that split makes a failed render observable
 * instead of silently turning it into a design decision.
 */
export type RoomInspectionPurpose = "overview" | "establish" | "return" | "coverage" | "detail" | "transition" | "floor_isolated";

export type EvidenceCameraPose = {
  position: [number, number, number];
  target: [number, number, number];
  fov: number;
};

export type RoomInspectionView = {
  id: string;
  purpose: RoomInspectionPurpose;
  sourceProgress: number;
  label: string;
  description: string;
  focusTargetIds: string[];
  cameraPose: EvidenceCameraPose;
};

export type RoomObservationPlan = {
  tool: "observe_room";
  houseId: string;
  roomId: string;
  roomLabel: string;
  expectedTargetIds: string[];
  views: RoomInspectionView[];
  plannedCoverage: Record<string, string[]>;
  topologyAnomalyTargetIds: string[];
};

export type HomeHarmonyTransition = {
  id: string;
  openingId: string;
  fromRoomId: string;
  toRoomId: string;
  rationale: string;
  openingCenter: [number, number, number];
  fromView: RoomInspectionView;
  toView: RoomInspectionView;
};

export type HomeHarmonyPlan = {
  tool: "observe_home_harmony";
  houseId: string;
  roomHeroViews: Array<{
    roomId: string;
    roomLabel: string;
    sourceProgress: number;
    label: string;
    candidateViews: RoomInspectionView[];
  }>;
  transitions: HomeHarmonyTransition[];
};

export const HOME_HERO_MAX_CANDIDATES = 5;

/**
 * Provider-neutral function definitions.  An API adapter maps snake_case
 * arguments onto the browser bridge's camelCase methods and then forwards each
 * returned imageDataUrl as an actual image input block, never as plain text.
 */
export const VISUAL_OBSERVATION_TOOL_DEFINITIONS = [
  {
    type: "function",
    function: {
      name: "observe_room",
      description: "Render the current validated Scheme from enough stable room views to inspect its walls, floor and ceiling. Returns images and grounded target IDs; it never changes the Scheme.",
      parameters: {
        type: "object",
        additionalProperties: false,
        properties: {
          room_id: {
            type: "string",
            description: "A real active-house room ID returned by get_room_by_id.",
          },
          focus_target_ids: {
            type: "array",
            items: { type: "string" },
            maxItems: 3,
            description: "Optional real design target IDs in that same room. The tool rejects cross-room or unknown IDs.",
          },
        },
        required: ["room_id"],
      },
    },
  },
  {
    type: "function",
    function: {
      name: "observe_home_harmony",
      description: "Render a whole-home contact sheet plus evidence pairs across named real openings. It returns incomplete_observation instead of claiming all-home harmony when room coverage is incomplete.",
      parameters: {
        type: "object",
        additionalProperties: false,
        properties: {},
      },
    },
  },
] as const;

function targetIds(track: RoomCameraTrack) {
  return [track.surfaceTargets.floor, track.surfaceTargets.ceiling, ...track.surfaceTargets.walls]
    .filter((targetId): targetId is string => Boolean(targetId));
}

function inspectionPriority(frame: RoomCameraKeyframe) {
  if (frame.intent === "surface") return 4;
  if (frame.intent === "detail") return 3;
  if (frame.intent === "reveal") return 2;
  if (frame.intent === "return") return 1;
  return 0;
}

function cameraPose(frame: RoomCameraKeyframe): EvidenceCameraPose {
  return {
    position: [...frame.position] as [number, number, number],
    target: [...frame.target] as [number, number, number],
    fov: frame.fov,
  };
}

function makeView(frame: RoomCameraKeyframe, index: number, purpose: RoomInspectionPurpose): RoomInspectionView {
  return {
    id: `inspection_${Math.round(frame.progress * 1000).toString().padStart(3, "0")}_${index + 1}`,
    purpose,
    sourceProgress: frame.progress,
    label: frame.label,
    description: frame.description,
    focusTargetIds: frame.focusTargetIds,
    cameraPose: cameraPose(frame),
  };
}

function samePose(first: RoomCameraKeyframe, second: RoomCameraKeyframe) {
  return JSON.stringify([first.position, first.target, first.fov])
    === JSON.stringify([second.position, second.target, second.fov]);
}

function roomOverviewView(track: RoomCameraTrack): RoomInspectionView {
  const [x1, y1, x2, y2] = track.roomRect;
  const inset = Math.min(0.45, Math.max(0.22, Math.min(x2 - x1, y2 - y1) * 0.22));
  const entry = track.entryAnchor.position;
  const centerX = (x1 + x2) / 2;
  const centerY = (y1 + y2) / 2;
  const entryInsideX = Math.min(x2 - inset, Math.max(x1 + inset, entry[0]));
  const entryInsideY = Math.min(y2 - inset, Math.max(y1 + inset, entry[1]));
  // Pull the nominal doorway pose toward the room centre. Door jambs and short
  // return walls otherwise dominate small-room contact-sheet cells even though
  // the target behind them technically has enough pixels to pass an ID mask.
  const entryBlend = 0.58;
  const position: [number, number, number] = [
    centerX + (entryInsideX - centerX) * entryBlend,
    centerY + (entryInsideY - centerY) * entryBlend,
    1.58,
  ];
  const target: [number, number, number] = [
    centerX,
    centerY,
    1.05,
  ];
  return {
    id: "overview_verified_0",
    purpose: "overview",
    sourceProgress: 0,
    label: `${track.roomLabel}验收总览`,
    description: "从房间内部安全位置观察空间主体，而不是把门口轨迹首帧冒充总览。",
    focusTargetIds: targetIds(track),
    cameraPose: {
      position,
      target,
      fov: Math.min(62, Math.max(52, 66 - Math.min(x2 - x1, y2 - y1) * 3)),
    },
  };
}

function roomInteriorSweepViews(track: RoomCameraTrack): RoomInspectionView[] {
  const [x1, y1, x2, y2] = track.roomRect;
  const centerX = (x1 + x2) / 2;
  const centerY = (y1 + y2) / 2;
  const inset = Math.min(0.62, Math.max(0.34, Math.min(x2 - x1, y2 - y1) * 0.24));
  const z = 1.58;
  const targetZ = 1.08;
  const specs: Array<[string, [number, number, number], [number, number, number]]> = [
    ["south_to_north", [centerX, y1 + inset, z], [centerX, y2 - inset, targetZ]],
    ["north_to_south", [centerX, y2 - inset, z], [centerX, y1 + inset, targetZ]],
    ["west_to_east", [x1 + inset, centerY, z], [x2 - inset, centerY, targetZ]],
    ["east_to_west", [x2 - inset, centerY, z], [x1 + inset, centerY, targetZ]],
  ];
  return specs.map(([direction, position, target], index) => ({
    id: `interior_sweep_${direction}`,
    purpose: "overview",
    sourceProgress: -2 - index,
    label: `${track.roomLabel}内部${direction}`,
    description: "从房间内部净区反向检查，作为门框或短墙遮挡入口机位时的代表图候选。",
    focusTargetIds: targetIds(track),
    cameraPose: { position, target, fov: 56 },
  }));
}

/**
 * Build deterministic candidate evidence views.  These are only camera
 * candidates: the renderer performs a real object-ID pass and owns the final
 * visibility decision.  Duplicate entry/return poses are removed so image
 * count can no longer masquerade as evidence diversity.
 */
export function createRoomObservationPlan(roomId: string, requestedTargetIds: string[] = []): RoomObservationPlan {
  const track = getRoomCameraTrack(roomId);
  const expectedTargetIds = targetIds(track);
  const expectedSet = new Set(expectedTargetIds);
  const invalidRequestedTargetIds = requestedTargetIds.filter((targetId) => !expectedSet.has(targetId));
  if (invalidRequestedTargetIds.length > 0) {
    throw new Error(`${track.roomLabel}不包含可观察目标：${invalidRequestedTargetIds.join(", ")}`);
  }
  const uniqueFrames = track.keyframes.filter((frame, index, frames) => (
    frames.findIndex((candidate) => samePose(candidate, frame)) === index
  ));
  const rankedFrames = [...uniqueFrames].sort((first, second) => (
    second.focusTargetIds.filter((targetId) => requestedTargetIds.includes(targetId)).length
    - first.focusTargetIds.filter((targetId) => requestedTargetIds.includes(targetId)).length
    || inspectionPriority(second) - inspectionPriority(first)
    || first.progress - second.progress
  ));
  const selectedFrames = rankedFrames.slice(0, 7).sort((first, second) => first.progress - second.progress);
  const trackViews = [roomOverviewView(track), ...selectedFrames.map((frame, selectedIndex) => {
    const index = track.keyframes.indexOf(frame);
    const purpose: RoomInspectionPurpose = index === 0
      ? "establish"
      : index === track.keyframes.length - 1
        ? "return"
        : frame.intent === "detail"
          ? "detail"
          : "coverage";
    return makeView(frame, selectedIndex, purpose);
  })];
  const targetViews = [
    ...track.surfaceTargets.walls
      .map((targetId) => wallTargetView(track, targetId))
      .filter((view): view is RoomInspectionView => Boolean(view)),
    ...(track.surfaceTargets.ceiling ? [ceilingTargetView(track, track.surfaceTargets.ceiling)] : []),
  ];
  const views = [...trackViews, ...targetViews];
  const plannedCoverage = Object.fromEntries(expectedTargetIds.map((targetId) => [
    targetId,
    views.filter((view) => view.focusTargetIds.includes(targetId)).map((view) => view.id),
  ]));

  return {
    tool: "observe_room",
    houseId: "house_spacious_yunkuo_135_v4",
    roomId: track.roomId,
    roomLabel: track.roomLabel,
    expectedTargetIds,
    views,
    plannedCoverage,
    topologyAnomalyTargetIds: targetViews
      .filter((view) => view.description.includes("拓扑异常"))
      .flatMap((view) => view.focusTargetIds),
  };
}

type ManifestOpening = { id: string; start: number; end: number; bottom: number; top: number; host_wall_id: string };
type ManifestWallFace = {
  id?: string;
  host_wall_id: string;
  axis: "X" | "Y";
  wall_core_center_coordinate?: number;
  coordinate: number;
  start: number;
  end: number;
  orientation?: "north" | "south" | "east" | "west";
};
type ManifestRoom = {
  id: string;
  rect: [number, number, number, number];
  topology_rects?: Array<[number, number, number, number]>;
};

function observationRects(track: RoomCameraTrack) {
  const room = (sceneManifest.rooms as ManifestRoom[]).find((candidate) => candidate.id === track.roomId);
  return room?.topology_rects?.length ? room.topology_rects : [track.roomRect];
}

function wallTargetView(track: RoomCameraTrack, targetId: string): RoomInspectionView | null {
  const face = (sceneManifest.wall_faces as ManifestWallFace[])
    .find((candidate) => candidate.id === targetId);
  if (!face) return null;
  const coordinate = face.coordinate;
  const segmentCenter = (face.start + face.end) / 2;
  const tolerance = 0.3;
  const matchingRect = observationRects(track).find(([x1, y1, x2, y2]) => (
    face.axis === "X"
      ? segmentCenter >= x1 - tolerance && segmentCenter <= x2 + tolerance
        && Math.min(Math.abs(coordinate - y1), Math.abs(coordinate - y2)) <= tolerance
      : segmentCenter >= y1 - tolerance && segmentCenter <= y2 + tolerance
        && Math.min(Math.abs(coordinate - x1), Math.abs(coordinate - x2)) <= tolerance
  ));
  const adjacent = Boolean(matchingRect);
  const [x1, y1, x2, y2] = matchingRect ?? track.roomRect;
  const centerX = (x1 + x2) / 2;
  const centerY = (y1 + y2) / 2;
  const distance = Math.min(1.55, Math.max(0.72, (face.axis === "X" ? y2 - y1 : x2 - x1) * 0.42));
  const sign = adjacent
    ? face.axis === "X"
      ? (centerY >= coordinate ? 1 : -1)
      : (centerX >= coordinate ? 1 : -1)
    : face.orientation === "north" || face.orientation === "east" ? 1 : -1;
  const position: [number, number, number] = face.axis === "X"
    ? [adjacent ? Math.min(x2 - 0.28, Math.max(x1 + 0.28, segmentCenter)) : segmentCenter, coordinate + sign * distance, 1.58]
    : [coordinate + sign * distance, adjacent ? Math.min(y2 - 0.28, Math.max(y1 + 0.28, segmentCenter)) : segmentCenter, 1.58];
  const target: [number, number, number] = face.axis === "X"
    ? [segmentCenter, coordinate, 1.32]
    : [coordinate, segmentCenter, 1.32];
  return {
    id: `target_wall_${targetId}`,
    purpose: "coverage",
    sourceProgress: -10,
    label: `${track.roomLabel}墙面专项`,
    description: adjacent
      ? "由墙段几何和房间内法向生成，不依赖导览轨迹的焦点声明。"
      : "目标饰面不与房间矩形相邻；按饰面朝向生成专项证据，并保留此拓扑异常供审计。",
    focusTargetIds: [targetId],
    cameraPose: { position, target, fov: 55 },
  };
}

function ceilingTargetView(track: RoomCameraTrack, targetId: string): RoomInspectionView {
  const [x1, y1, x2, y2] = track.roomRect;
  const centerX = (x1 + x2) / 2;
  const centerY = (y1 + y2) / 2;
  return {
    id: `target_ceiling_${track.roomId}`,
    purpose: "coverage",
    sourceProgress: -11,
    label: `${track.roomLabel}吊顶专项`,
    description: "从房间净区抬头检查吊顶和墙顶收口，不以普通人眼导览帧代替顶面证据。",
    focusTargetIds: [targetId],
    cameraPose: {
      position: [centerX, centerY, 1.58],
      target: [centerX, Math.min(y2 - 0.2, centerY + 0.65), 2.88],
      fov: 58,
    },
  };
}

function openingGeometry(openingId: string) {
  const opening = (sceneManifest.openings as ManifestOpening[]).find((candidate) => candidate.id === openingId);
  if (!opening) throw new Error(`Unknown observation opening: ${openingId}`);
  const face = (sceneManifest.wall_faces as ManifestWallFace[])
    .find((candidate) => candidate.host_wall_id === opening.host_wall_id);
  if (!face) throw new Error(`Opening ${openingId} has no wall geometry`);
  const coordinate = face.wall_core_center_coordinate ?? face.coordinate;
  return {
    opening,
    axis: face.axis,
    center: face.axis === "X"
      ? [(opening.start + opening.end) / 2, coordinate, (opening.bottom + opening.top) / 2] as [number, number, number]
      : [coordinate, (opening.start + opening.end) / 2, (opening.bottom + opening.top) / 2] as [number, number, number],
  };
}

function openingSideView(
  roomId: string,
  openingId: string,
  id: string,
  label: string,
): RoomInspectionView {
  const track = getRoomCameraTrack(roomId);
  const [x1, y1, x2, y2] = track.roomRect;
  const roomCenter: [number, number] = [(x1 + x2) / 2, (y1 + y2) / 2];
  const geometry = openingGeometry(openingId);
  const [openingX, openingY] = geometry.center;
  const isXAxis = geometry.axis === "X";
  const boundaryTolerance = 0.3;
  const overlapsParallelSpan = isXAxis
    ? openingX >= x1 - boundaryTolerance && openingX <= x2 + boundaryTolerance
    : openingY >= y1 - boundaryTolerance && openingY <= y2 + boundaryTolerance;
  const touchesRoomBoundary = isXAxis
    ? Math.min(Math.abs(openingY - y1), Math.abs(openingY - y2)) <= boundaryTolerance
    : Math.min(Math.abs(openingX - x1), Math.abs(openingX - x2)) <= boundaryTolerance;
  if (!overlapsParallelSpan || !touchesRoomBoundary) {
    throw new Error(`Opening ${openingId} is not adjacent to observation room ${roomId}`);
  }
  const perpendicularDelta = isXAxis ? roomCenter[1] - openingY : roomCenter[0] - openingX;
  const sign = perpendicularDelta >= 0 ? 1 : -1;
  const available = isXAxis
    ? Math.abs((sign > 0 ? y2 : y1) - openingY)
    : Math.abs((sign > 0 ? x2 : x1) - openingX);
  const distance = Math.min(1.4, Math.max(0.65, available - 0.32));
  const parallelRoomCenter = isXAxis ? roomCenter[0] : roomCenter[1];
  const parallelOpening = isXAxis ? openingX : openingY;
  const parallelOffset = Math.max(-0.18, Math.min(0.18, parallelRoomCenter - parallelOpening));
  const position: [number, number, number] = isXAxis
    ? [openingX + parallelOffset, openingY + sign * distance, 1.56]
    : [openingX + sign * distance, openingY + parallelOffset, 1.56];
  return {
    id,
    purpose: "transition",
    sourceProgress: -1,
    label,
    description: `从${track.roomLabel}一侧正对真实门槛，画面同时保留本侧地面与门洞另一侧。`,
    focusTargetIds: [track.surfaceTargets.floor].filter((targetId): targetId is string => Boolean(targetId)),
    cameraPose: {
      position,
      target: [openingX, openingY, 0.48],
      fov: 60,
    },
  };
}

/**
 * Only transitions represented by a real, named opening are listed here.
 * Unmodelled circulation must not be fabricated as an adjacency fact.
 */
export const HOME_HARMONY_TRANSITIONS: HomeHarmonyTransition[] = [
  {
    id: "bedroom_3_to_open_public",
    openingId: "opening_bed3_door",
    fromRoomId: "bedroom_3",
    toRoomId: "open_public",
    rationale: "南次卧门洞两侧的墙面、地面与吊顶过渡。",
    openingCenter: openingGeometry("opening_bed3_door").center,
    fromView: openingSideView("bedroom_3", "opening_bed3_door", "opening_bed3_door_from", "南次卧门槛内侧"),
    toView: openingSideView("open_public", "opening_bed3_door", "opening_bed3_door_to", "横厅门槛外侧"),
  },
  {
    id: "master_dressing_to_open_public",
    openingId: "opening_master_suite_door",
    fromRoomId: "master_dressing",
    toRoomId: "open_public",
    rationale: "主卧套房入口处，横厅与衣帽间之间的私密区过渡。",
    openingCenter: openingGeometry("opening_master_suite_door").center,
    fromView: openingSideView("master_dressing", "opening_master_suite_door", "opening_master_suite_door_from", "衣帽间套房门槛内侧"),
    toView: openingSideView("open_public", "opening_master_suite_door", "opening_master_suite_door_to", "横厅门槛外侧"),
  },
  {
    id: "master_dressing_to_master_bedroom",
    openingId: "opening_master_dressing",
    fromRoomId: "master_dressing",
    toRoomId: "master_bedroom",
    rationale: "主卧与衣帽间之间的地面、墙面连续性。",
    openingCenter: openingGeometry("opening_master_dressing").center,
    fromView: openingSideView("master_dressing", "opening_master_dressing", "opening_master_dressing_from", "衣帽间门槛内侧"),
    toView: openingSideView("master_bedroom", "opening_master_dressing", "opening_master_dressing_to", "主卧门槛外侧"),
  },
  {
    id: "master_bath_to_master_dressing",
    openingId: "opening_master_bath_door",
    fromRoomId: "master_bath",
    toRoomId: "master_dressing",
    rationale: "主卫湿区与衣帽间干区之间的有意材质转换。",
    openingCenter: openingGeometry("opening_master_bath_door").center,
    fromView: openingSideView("master_bath", "opening_master_bath_door", "opening_master_bath_door_from", "主卫门槛内侧"),
    toView: openingSideView("master_dressing", "opening_master_bath_door", "opening_master_bath_door_to", "衣帽间门槛外侧"),
  },
  {
    id: "bedroom_2_to_open_public",
    openingId: "opening_bed2_door",
    fromRoomId: "bedroom_2",
    toRoomId: "open_public",
    rationale: "北次卧门洞两侧的私密区过渡。",
    openingCenter: openingGeometry("opening_bed2_door").center,
    fromView: openingSideView("bedroom_2", "opening_bed2_door", "opening_bed2_door_from", "北次卧门槛内侧"),
    toView: openingSideView("open_public", "opening_bed2_door", "opening_bed2_door_to", "横厅门槛外侧"),
  },
  {
    id: "kitchen_to_open_public",
    openingId: "opening_kitchen_glass_slider",
    fromRoomId: "kitchen",
    toRoomId: "open_public",
    rationale: "玻璃移门两侧的公共区与厨房湿区转换。",
    openingCenter: openingGeometry("opening_kitchen_glass_slider").center,
    fromView: openingSideView("kitchen", "opening_kitchen_glass_slider", "opening_kitchen_glass_slider_from", "厨房移门内侧"),
    toView: openingSideView("open_public", "opening_kitchen_glass_slider", "opening_kitchen_glass_slider_to", "横厅移门外侧"),
  },
];

export function createHomeHarmonyPlan(): HomeHarmonyPlan {
  return {
    tool: "observe_home_harmony",
    houseId: "house_spacious_yunkuo_135_v4",
    roomHeroViews: ROOM_CAMERA_TRACKS.map((track) => {
      const view = roomOverviewView(track);
      const heroTrackViews = [...track.keyframes]
        .filter((frame) => frame.focusTargetIds.some((targetId) => (
          targetId === track.surfaceTargets.floor || track.surfaceTargets.walls.includes(targetId)
        )))
        .sort((first, second) => inspectionPriority(second) - inspectionPriority(first))
        .slice(0, 2)
        .map((frame, index) => makeView(frame, index, frame.intent === "detail" ? "detail" : "coverage"));
      const candidateViews = [
        view,
        ...heroTrackViews,
        ...roomInteriorSweepViews(track).slice(0, 2),
      ].filter((candidate, index, candidates) => (
        candidates.findIndex((other) => JSON.stringify(other.cameraPose) === JSON.stringify(candidate.cameraPose)) === index
      )).slice(0, HOME_HERO_MAX_CANDIDATES);
      return {
        roomId: track.roomId,
        roomLabel: track.roomLabel,
        sourceProgress: view.sourceProgress,
        label: view.label,
        candidateViews,
      };
    }),
    transitions: HOME_HARMONY_TRANSITIONS,
  };
}
