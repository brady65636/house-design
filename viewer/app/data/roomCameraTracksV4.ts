import trackData from "./roomCameraTracksV4.json";

export type CameraIntent = "establish" | "reveal" | "surface" | "detail" | "return";
export type CameraPoint = [number, number, number];
export type RoomRect = [number, number, number, number];

export type CameraAnchor = {
  position: CameraPoint;
  target: CameraPoint;
  fov: number;
};

export type RoomCameraKeyframe = CameraAnchor & {
  progress: number;
  label: string;
  description: string;
  intent: CameraIntent;
  holdMs?: number;
  focusTargetIds: string[];
};

export type RoomCameraTrack = {
  id: string;
  roomId: string;
  roomLabel: string;
  durationMs: number;
  roomRect: RoomRect;
  entryAnchor: CameraAnchor;
  exitAnchor: CameraAnchor;
  surfaceTargets: {
    floor: string;
    ceiling: string | null;
    walls: string[];
  };
  focusProgress: {
    wall: number;
    floor: number;
    ceiling: number;
  };
  keyframes: RoomCameraKeyframe[];
};

type RoomCameraCatalog = {
  houseId: string;
  revision: string;
  coordinateSystem: "blender_z_up_meters";
  tracks: RoomCameraTrack[];
};

export const ROOM_CAMERA_CATALOG = trackData as RoomCameraCatalog;
export const ROOM_CAMERA_TRACKS = ROOM_CAMERA_CATALOG.tracks;
export const DEFAULT_ROOM_ID = "open_public";
export const ROOM_CAMERA_TRACK_BY_ROOM = new Map(
  ROOM_CAMERA_TRACKS.map((track) => [track.roomId, track]),
);

export function getRoomCameraTrack(roomId: string) {
  return ROOM_CAMERA_TRACK_BY_ROOM.get(roomId)
    ?? ROOM_CAMERA_TRACK_BY_ROOM.get(DEFAULT_ROOM_ID)!;
}
