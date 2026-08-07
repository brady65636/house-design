import {
  getRoomCameraTrack,
  ROOM_CAMERA_TRACKS,
  type RoomCameraKeyframe,
  type RoomCameraTrack,
} from "./roomCameraTracksV4";

/**
 * These plans are evidence plans, not aesthetic judgments.  The visual model
 * receives the rendered images plus this grounding data, then makes its own
 * structured critique.  Keeping that split makes a failed render observable
 * instead of silently turning it into a design decision.
 */
export type RoomInspectionPurpose = "establish" | "return" | "coverage" | "detail";

export type RoomInspectionView = {
  id: string;
  purpose: RoomInspectionPurpose;
  sourceProgress: number;
  label: string;
  description: string;
  focusTargetIds: string[];
};

export type RoomObservationPlan = {
  tool: "observe_room";
  houseId: string;
  roomId: string;
  roomLabel: string;
  expectedTargetIds: string[];
  views: RoomInspectionView[];
  declaredCoverage: Record<string, string[]>;
  uncoveredTargetIds: string[];
};

export type HomeHarmonyTransition = {
  id: string;
  openingId: string;
  fromRoomId: string;
  fromProgress: number;
  toRoomId: string;
  toProgress: number;
  rationale: string;
};

export type HomeHarmonyPlan = {
  tool: "observe_home_harmony";
  houseId: string;
  roomHeroViews: Array<{
    roomId: string;
    roomLabel: string;
    sourceProgress: number;
    label: string;
  }>;
  transitions: HomeHarmonyTransition[];
};

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

function makeView(frame: RoomCameraKeyframe, index: number, purpose: RoomInspectionPurpose): RoomInspectionView {
  return {
    id: `inspection_${Math.round(frame.progress * 1000).toString().padStart(3, "0")}_${index + 1}`,
    purpose,
    sourceProgress: frame.progress,
    label: frame.label,
    description: frame.description,
    focusTargetIds: frame.focusTargetIds,
  };
}

/**
 * Select the smallest stable subset of the already-reviewed room track that
 * declares every design target.  This is intentionally deterministic: no LLM
 * decides where it has looked, and the returned coverage is labelled
 * "declared" until a future ID-pass can confirm pixel-level visibility.
 */
export function createRoomObservationPlan(roomId: string, requestedTargetIds: string[] = []): RoomObservationPlan {
  const track = getRoomCameraTrack(roomId);
  const expectedTargetIds = targetIds(track);
  const expectedSet = new Set(expectedTargetIds);
  const invalidRequestedTargetIds = requestedTargetIds.filter((targetId) => !expectedSet.has(targetId));
  if (invalidRequestedTargetIds.length > 0) {
    throw new Error(`${track.roomLabel}不包含可观察目标：${invalidRequestedTargetIds.join(", ")}`);
  }
  const selected = new Set<number>([0, track.keyframes.length - 1]);
  const covered = new Set<string>();

  for (const index of selected) {
    track.keyframes[index].focusTargetIds.forEach((targetId) => covered.add(targetId));
  }

  while (selected.size < 6) {
    const candidates = track.keyframes
      .map((frame, index) => ({ frame, index }))
      .filter(({ index }) => !selected.has(index));
    const next = candidates
      .map(({ frame, index }) => ({
        frame,
        index,
        uncovered: frame.focusTargetIds.filter((targetId) => expectedSet.has(targetId) && !covered.has(targetId)).length,
        requested: frame.focusTargetIds.filter((targetId) => requestedTargetIds.includes(targetId)).length,
      }))
      .sort((first, second) => second.uncovered - first.uncovered
        || second.requested - first.requested
        || inspectionPriority(second.frame) - inspectionPriority(first.frame)
        || first.index - second.index)[0];

    if (!next || (next.uncovered === 0 && next.requested === 0)) break;
    selected.add(next.index);
    next.frame.focusTargetIds.forEach((targetId) => covered.add(targetId));
  }

  // A visual critique needs more than one direction even in a two-target room.
  for (let index = 0; selected.size < 3 && index < track.keyframes.length; index += 1) {
    selected.add(index);
  }

  const selectedIndices = [...selected].sort((first, second) => first - second);
  const views = selectedIndices.map((index, selectedIndex) => {
    const frame = track.keyframes[index];
    const purpose: RoomInspectionPurpose = index === 0
      ? "establish"
      : index === track.keyframes.length - 1
        ? "return"
        : frame.intent === "detail"
          ? "detail"
          : "coverage";
    return makeView(frame, selectedIndex, purpose);
  });
  const declaredCoverage = Object.fromEntries(expectedTargetIds.map((targetId) => [
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
    declaredCoverage,
    uncoveredTargetIds: expectedTargetIds.filter((targetId) => !covered.has(targetId)),
  };
}

function keyframeAt(track: RoomCameraTrack, progress: number) {
  return track.keyframes.find((frame) => frame.progress === progress) ?? track.keyframes[0];
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
    fromProgress: 1,
    toRoomId: "open_public",
    toProgress: 0,
    rationale: "南次卧门洞两侧的墙面、地面与吊顶过渡。",
  },
  {
    id: "master_bedroom_to_open_public",
    openingId: "opening_master_suite_door",
    fromRoomId: "master_bedroom",
    fromProgress: 1,
    toRoomId: "open_public",
    toProgress: 1,
    rationale: "主卧套房门与横厅之间的私密区过渡。",
  },
  {
    id: "master_dressing_to_master_bedroom",
    openingId: "opening_master_dressing",
    fromRoomId: "master_dressing",
    fromProgress: 1,
    toRoomId: "master_bedroom",
    toProgress: 0,
    rationale: "主卧与衣帽间之间的地面、墙面连续性。",
  },
  {
    id: "master_bath_to_master_dressing",
    openingId: "opening_master_bath_door",
    fromRoomId: "master_bath",
    fromProgress: 1,
    toRoomId: "master_dressing",
    toProgress: 0,
    rationale: "主卫湿区与衣帽间干区之间的有意材质转换。",
  },
  {
    id: "bedroom_2_to_open_public",
    openingId: "opening_bed2_door",
    fromRoomId: "bedroom_2",
    fromProgress: 1,
    toRoomId: "open_public",
    toProgress: 1,
    rationale: "北次卧门洞两侧的私密区过渡。",
  },
  {
    id: "kitchen_to_open_public",
    openingId: "opening_kitchen_glass_slider",
    fromRoomId: "kitchen",
    fromProgress: 1,
    toRoomId: "open_public",
    toProgress: 0,
    rationale: "玻璃移门两侧的公共区与厨房湿区转换。",
  },
];

export function createHomeHarmonyPlan(): HomeHarmonyPlan {
  return {
    tool: "observe_home_harmony",
    houseId: "house_spacious_yunkuo_135_v4",
    roomHeroViews: ROOM_CAMERA_TRACKS.map((track) => {
      const frame = keyframeAt(track, 0);
      return {
        roomId: track.roomId,
        roomLabel: track.roomLabel,
        sourceProgress: frame.progress,
        label: frame.label,
      };
    }),
    transitions: HOME_HARMONY_TRANSITIONS,
  };
}
