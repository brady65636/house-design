"use client";

import { useEffect, useRef, useState } from "react";
import * as THREE from "three";
import { GLTFLoader } from "three/examples/jsm/loaders/GLTFLoader.js";
import { OrbitControls } from "three/examples/jsm/controls/OrbitControls.js";
import { HDRLoader } from "three/examples/jsm/loaders/HDRLoader.js";
import { EffectComposer } from "three/examples/jsm/postprocessing/EffectComposer.js";
import { RenderPass } from "three/examples/jsm/postprocessing/RenderPass.js";
import { GTAOPass } from "three/examples/jsm/postprocessing/GTAOPass.js";
import { OutputPass } from "three/examples/jsm/postprocessing/OutputPass.js";
import { RectAreaLightUniformsLib } from "three/examples/jsm/lights/RectAreaLightUniformsLib.js";
import { blenderPoint } from "./interiorScene";
import { enhanceHeroSurfaces } from "./heroLivingScene";
import {
  findPaintVariant,
  PAINT_APPEARANCE_CALIBRATION,
  PAINT_CATALOG,
  PAINT_VARIANT_BY_ID,
  PAINT_VARIANTS,
  type PaintFinishId,
  type PaintToneId,
} from "../data/paintCatalog";
import { WALLPAPERS } from "../data/wallpaperCatalog";
import { CEILINGS, FLOORS, TILES } from "../data/surfaceCatalog";
import type { Scheme } from "../data/schemeTypes";
import {
  DEFAULT_ROOM_ID,
  getRoomCameraTrack,
  ROOM_CAMERA_TRACKS,
  type RoomCameraTrack,
} from "../data/roomCameraTracksV4";
import {
  createHomeHarmonyPlan,
  createRoomObservationPlan,
  type HomeHarmonyTransition,
  type RoomInspectionView,
} from "../data/visualObservation";

// --- 方案来源解析:优先 agent-api(部署),回退同源静态文件(本地 dev) ---
const AGENT_API_URL = (() => {
  if (typeof window !== "undefined") {
    const fromQuery = new URLSearchParams(window.location.search).get("agent_api");
    if (fromQuery) return fromQuery.replace(/\/$/, "");
  }
  return (process.env.NEXT_PUBLIC_AGENT_API_URL ?? "").replace(/\/$/, "");
})();

async function fetchCurrentScheme(): Promise<Scheme> {
  if (AGENT_API_URL) {
    const response = await fetch(`${AGENT_API_URL}/api/scheme`, { cache: "no-store" });
    if (!response.ok) throw new Error(`Agent scheme fetch ${response.status}`);
    return response.json() as Promise<Scheme>;
  }
  const response = await fetch("/current_scheme.json", { cache: "no-store" });
  if (!response.ok) throw new Error(`Scheme fetch ${response.status}`);
  return response.json() as Promise<Scheme>;
}

type LoadState = "loading" | "ready" | "error";

type SelectedTarget = {
  targetId: string;
  targetKind: "wall_face" | "surface";
  assetId: string | null;
  displayCode: string | null;
  displayName: string | null;
  roomId: string | null;
};

type ExperienceApi = {
  applyAsset: (targetIds: string[], assetId: string) => void;
  setCeilingPreset: (roomId: string, presetId: string) => void;
  setDetailsVisible: (visible: boolean) => void;
  setActiveTrack: (roomId: string) => void;
  setTourProgress: (progress: number) => void;
  setTourPlaying: (playing: boolean) => void;
  observeRoom: (roomId: string, focusTargetIds?: string[]) => Promise<RoomObservationResult>;
  observeHomeHarmony: () => Promise<HomeHarmonyObservationResult>;
};

type VisualImage = {
  viewId: string;
  label: string;
  purpose: string;
  focusTargetIds: string[];
  imageDataUrl: string;
};

type RoomObservationResult = {
  tool: "observe_room";
  status: "ready" | "incomplete_observation";
  evidenceLevel: "declared_track_coverage";
  houseId: string;
  scheme: { schemeId: string | null; title: string | null };
  room: { id: string; label: string };
  views: VisualImage[];
  declaredCoverage: Record<string, string[]>;
  uncoveredTargetIds: string[];
};

type HomeHarmonyObservationResult = {
  tool: "observe_home_harmony";
  status: "ready" | "incomplete_observation";
  evidenceLevel: "declared_track_coverage";
  houseId: string;
  scheme: { schemeId: string | null; title: string | null };
  roomContactSheet: string;
  transitionPairs: Array<{
    id: string;
    openingId: string;
    rationale: string;
    from: VisualImage;
    to: VisualImage;
  }>;
  incompleteRooms: Array<{ roomId: string; uncoveredTargetIds: string[] }>;
};

type RenderCommand = {
  id: string;
  tool: "observe_room" | "observe_home_harmony";
  args: { room_id?: string; focus_target_ids?: string[] };
};

const ASSET_LABELS: Record<string, string> = {
  ...Object.fromEntries(PAINT_VARIANTS.map((variant) => [variant.id, variant.nameZh])),
  ...Object.fromEntries(WALLPAPERS.map((product) => [product.id, `${product.name_zh}墙纸`])),
  ...Object.fromEntries(FLOORS.map((product) => [product.id, product.name_zh])),
  ...Object.fromEntries(TILES.map((product) => [product.id, product.name_zh])),
  ...Object.fromEntries(CEILINGS.map((product) => [product.id, product.name_zh])),
};

const WET_ROOM_IDS = new Set(["kitchen", "guest_bath", "master_bath"]);

// The real-time renderer has no baked global illumination. Keep the indirect
// contribution neutral so a near-white wall in shade reads as its paint colour,
// rather than inheriting a brown cast from the virtual floor.
const INDIRECT_DAYLIGHT = {
  sky: "#f3f4f2",
  ground: "#aaa7a1",
  intensity: 0.55,
  environmentIntensity: 0.4,
} as const;

// 吊顶目标是 surface_real4_ceiling_<roomId> 的稳定 ID，房间切换后按房间各自显示吊顶。
function roomFromCeilingTarget(targetId: string) {
  return targetId.startsWith("surface_real4_ceiling_")
    ? targetId.slice("surface_real4_ceiling_".length)
    : targetId;
}

function tourStageAt(track: RoomCameraTrack, progress: number) {
  return [...track.keyframes].reverse().find((frame) => progress >= frame.progress)
    ?? track.keyframes[0];
}

function formatTourTime(progress: number, durationMs: number) {
  const seconds = Math.round((durationMs / 1000) * progress);
  return `00:${String(seconds).padStart(2, "0")}`;
}

function seeded(seed: number) {
  let value = seed >>> 0;
  return () => {
    value = (value * 1664525 + 1013904223) >>> 0;
    return value / 4294967296;
  };
}

function makeTexture(assetId: string, baseColor: string) {
  const canvas = document.createElement("canvas");
  canvas.width = 512;
  canvas.height = 512;
  const context = canvas.getContext("2d");
  if (!context) return null;
  context.fillStyle = baseColor;
  context.fillRect(0, 0, 512, 512);
  const random = seeded(assetId.length * 193);

  if (assetId.startsWith("floor_")) {
    for (let index = 0; index < 180; index += 1) {
      const y = random() * 512;
      context.beginPath();
      context.moveTo(0, y);
      for (let x = 0; x <= 512; x += 18) {
        context.lineTo(x, y + Math.sin(x * 0.026 + random() * 4) * (2 + random() * 6));
      }
      context.strokeStyle = `rgba(68, 35, 13, ${0.025 + random() * 0.075})`;
      context.lineWidth = 0.5 + random();
      context.stroke();
    }
    context.strokeStyle = "rgba(52, 30, 16, .28)";
    context.lineWidth = 2;
    for (let y = 0; y <= 512; y += 128) {
      context.beginPath();
      context.moveTo(0, y);
      context.lineTo(512, y);
      context.stroke();
    }
  } else if (assetId.includes("linen")) {
    for (let p = 0; p < 512; p += 5) {
      context.strokeStyle = "rgba(69, 53, 33, .07)";
      context.beginPath();
      context.moveTo(p, 0);
      context.lineTo(p + 2, 512);
      context.stroke();
      context.beginPath();
      context.moveTo(0, p);
      context.lineTo(512, p + 2);
      context.stroke();
    }
  } else if (assetId.includes("linear")) {
    for (let x = 0; x < 512; x += 22) {
      context.fillStyle = x % 44 === 0 ? "rgba(74, 59, 39, .22)" : "rgba(255,255,255,.12)";
      context.fillRect(x, 0, 3, 512);
    }
  } else if (assetId.startsWith("tile_")) {
    const image = context.getImageData(0, 0, 512, 512);
    for (let index = 0; index < image.data.length; index += 4) {
      const noise = Math.round((random() - 0.5) * 18);
      image.data[index] += noise;
      image.data[index + 1] += noise;
      image.data[index + 2] += noise;
    }
    context.putImageData(image, 0, 0);
    context.strokeStyle = "rgba(50, 48, 43, .25)";
    context.lineWidth = 3;
    context.strokeRect(1.5, 1.5, 509, 509);
  }

  const texture = new THREE.CanvasTexture(canvas);
  texture.colorSpace = THREE.SRGBColorSpace;
  texture.wrapS = texture.wrapT = THREE.RepeatWrapping;
  const repeatPerMeter = assetId.startsWith("floor_") ? 0.5 : assetId.startsWith("tile_") ? 1 / 0.6 : 2;
  texture.repeat.set(repeatPerMeter, repeatPerMeter);
  texture.anisotropy = 8;
  return texture;
}

function makeTileAuxTexture(assetId: string, kind: "normal" | "roughness") {
  const canvas = document.createElement("canvas");
  canvas.width = canvas.height = 512;
  const context = canvas.getContext("2d");
  if (!context) return null;
  const random = seeded(assetId.length * (kind === "normal" ? 379 : 521));
  if (kind === "normal") {
    context.fillStyle = "rgb(128,128,255)";
    context.fillRect(0, 0, 512, 512);
    context.strokeStyle = "rgb(128,128,205)";
    context.lineWidth = 8;
    context.strokeRect(4, 4, 504, 504);
  } else {
    const image = context.createImageData(512, 512);
    for (let index = 0; index < image.data.length; index += 4) {
      const value = Math.round(205 + random() * 28);
      image.data[index] = image.data[index + 1] = image.data[index + 2] = value;
      image.data[index + 3] = 255;
    }
    context.putImageData(image, 0, 0);
    context.strokeStyle = "rgb(245,245,245)";
    context.lineWidth = 8;
    context.strokeRect(4, 4, 504, 504);
  }
  const texture = new THREE.CanvasTexture(canvas);
  texture.wrapS = texture.wrapT = THREE.RepeatWrapping;
  texture.repeat.set(1 / 0.6, 1 / 0.6);
  texture.anisotropy = 8;
  return texture;
}

function buildSurfaceMaterials() {
  const library = new Map<string, THREE.MeshStandardMaterial>();
  const textureLoader = new THREE.TextureLoader();
  PAINT_VARIANTS.forEach((variant) => {
    const material = new THREE.MeshPhysicalMaterial({
      name: `WEB_${variant.id}`,
      // A paint selection must present its catalogue colour consistently on
      // every wall face. Keep a small physically-lit component for form, but
      // anchor most of the result to the selected standard colour.
      color: new THREE.Color(variant.color).multiplyScalar(PAINT_APPEARANCE_CALIBRATION.directLightShare),
      roughness: variant.roughnessMean,
      metalness: 0,
      ior: 1.5,
      emissive: new THREE.Color(variant.color).multiplyScalar(PAINT_APPEARANCE_CALIBRATION.colourStandardShare),
      emissiveIntensity: 1,
      side: THREE.DoubleSide,
    });
    material.userData.asset_id = variant.id;
    material.userData.paint_family_id = variant.familyId;
    material.userData.paint_tone = variant.tone;
    material.userData.paint_finish = variant.finish;
    library.set(variant.id, material);
  });
  WALLPAPERS.forEach((product) => {
    const material = new THREE.MeshPhysicalMaterial({
        name: `WEB_${product.id}`,
        color: product.tint,
        roughness: product.roughness_mean,
        side: THREE.DoubleSide,
        sheen: product.sheen ?? 0.04,
        sheenColor: new THREE.Color("#efe5d4"),
        sheenRoughness: 0.92,
      });
    material.userData.asset_id = product.id;
    library.set(product.id, material);
  });
  [...FLOORS, ...TILES].forEach((product) => {
    const material = new THREE.MeshStandardMaterial({
      name: `WEB_${product.id}`,
      color: product.tint,
      roughness: product.roughness_mean,
      metalness: 0,
      side: THREE.DoubleSide,
    });
    material.userData.asset_id = product.id;
    material.userData.pbrLoaded = false;
    material.userData.ensurePbr = () => {
      if (material.userData.pbrPromise) return material.userData.pbrPromise;
      const configure = (texture: THREE.Texture, color = false) => {
        texture.wrapS = texture.wrapT = THREE.RepeatWrapping;
        texture.repeat.set(1 / product.repeat_size_m[0], 1 / product.repeat_size_m[1]);
        texture.anisotropy = 8;
        if (color) texture.colorSpace = THREE.SRGBColorSpace;
        return texture;
      };
      const prefix = `/assets/surfaces/${product.id}`;
      material.userData.pbrPromise = Promise.all([
        textureLoader.loadAsync(`${prefix}_basecolor_web.jpg`).then((texture) => configure(texture, true)),
        textureLoader.loadAsync(`${prefix}_normal_gl_web.webp`).then((texture) => configure(texture)),
        textureLoader.loadAsync(`${prefix}_roughness_web.webp`).then((texture) => configure(texture)),
      ]).then(([map, normalMap, roughnessMap]) => {
        material.map = map;
        material.normalMap = normalMap;
        material.roughnessMap = roughnessMap;
        // The authored roughness map already contains this product's calibrated
        // mean value. Keeping `roughness_mean` as the material multiplier would
        // multiply it a second time (for example 0.70 × 0.70 ≈ 0.49), making a
        // matte floor or tile read as a glossy finish under the HDR environment.
        material.roughness = 1;
        // These are non-metallic architectural finishes: retain a soft material
        // response to the room HDR without letting it dominate the base colour.
        material.envMapIntensity = 0.14;
        material.normalScale.set(product.normal_scale, product.normal_scale);
        material.color.set("#ffffff");
        material.userData.pbrLoaded = true;
        material.needsUpdate = true;
        return material;
      }).catch((error) => {
        material.userData.pbrPromise = null;
        console.warn(`Failed to load PBR maps for ${product.id}`, error);
        return material;
      });
      return material.userData.pbrPromise;
    };
    material.userData.releasePbr = () => {
      material.map?.dispose();
      material.normalMap?.dispose();
      material.roughnessMap?.dispose();
      material.map = null;
      material.normalMap = null;
      material.roughnessMap = null;
      material.color.set(product.tint);
      material.roughness = product.roughness_mean;
      material.envMapIntensity = 1;
      material.userData.pbrLoaded = false;
      material.userData.pbrPromise = null;
      material.needsUpdate = true;
    };
    library.set(product.id, material);
  });
  return library;
}

function buildCeilingPresetRoot() {
  const root = new THREE.Group();
  root.name = "CEILING_PRESET_ROOT";
  const ceilingMaterial = new THREE.MeshStandardMaterial({
    name: "WEB_ceiling_dry_finish",
    color: "#e8e1d2",
    roughness: 0.92,
  });
  const panelMaterial = new THREE.MeshStandardMaterial({ color: "#c8cbc6", roughness: 0.68 });
  const shadowMaterial = new THREE.MeshStandardMaterial({ color: "#171918", roughness: 0.98 });
  const coveLightMaterial = new THREE.MeshStandardMaterial({
    color: "#ffd7a0",
    emissive: "#ff9c45",
    emissiveIntensity: 2.2,
    roughness: 0.58,
  });

  const addBox = (
    group: THREE.Group,
    name: string,
    size: [number, number, number],
    position: [number, number, number],
    material: THREE.Material,
    presetId: string,
    roomId: string,
  ) => {
    const mesh = new THREE.Mesh(new THREE.BoxGeometry(size[0], size[2], size[1]), material);
    mesh.name = name;
    mesh.position.copy(blenderPoint(position));
    mesh.castShadow = true;
    mesh.receiveShadow = true;
    mesh.userData.preset_id = presetId;
    mesh.userData.room_id = roomId;
    group.add(mesh);
  };

  CEILINGS.filter((product) => product.family !== "flat").forEach((product) => {
    const group = new THREE.Group();
    group.name = `CEILING_PRESET_${product.id}`;
    group.userData.preset_id = product.id;
    group.visible = false;
    ROOM_CAMERA_TRACKS
      .filter((track) => track.surfaceTargets.ceiling !== null)
      .filter((track) => product.family === "modular_panel" ? WET_ROOM_IDS.has(track.roomId) : !WET_ROOM_IDS.has(track.roomId))
      .forEach(({ roomId, roomRect: [x1, y1, x2, y2] }) => {
        const width = x2 - x1;
        const depth = y2 - y1;
        const centerX = (x1 + x2) / 2;
        const centerY = (y1 + y2) / 2;
        const height = product.drop_height_mm / 1000;
        const centerZ = 3.07 - height / 2;
        if (product.family === "perimeter_step" || product.family === "perimeter_cove") {
          const band = (product.perimeter_band_mm ?? 300) / 1000;
          addBox(group, `${roomId}_${product.id}_left`, [band, depth, height], [x1 + band / 2, centerY, centerZ], ceilingMaterial, product.id, roomId);
          addBox(group, `${roomId}_${product.id}_right`, [band, depth, height], [x2 - band / 2, centerY, centerZ], ceilingMaterial, product.id, roomId);
          addBox(group, `${roomId}_${product.id}_front`, [Math.max(width - band * 2, 0.2), band, height], [centerX, y1 + band / 2, centerZ], ceilingMaterial, product.id, roomId);
          addBox(group, `${roomId}_${product.id}_back`, [Math.max(width - band * 2, 0.2), band, height], [centerX, y2 - band / 2, centerZ], ceilingMaterial, product.id, roomId);
          if (product.family === "perimeter_cove") {
            const cove = (product.cove_width_mm ?? 90) / 1000;
            const lightZ = 3.07 - height + 0.012;
            addBox(group, `${roomId}_${product.id}_light_left`, [cove, Math.max(depth - band * 2, 0.2), 0.018], [x1 + band + cove / 2, centerY, lightZ], coveLightMaterial, product.id, roomId);
            addBox(group, `${roomId}_${product.id}_light_right`, [cove, Math.max(depth - band * 2, 0.2), 0.018], [x2 - band - cove / 2, centerY, lightZ], coveLightMaterial, product.id, roomId);
          }
        } else if (product.family === "floating_shadow_gap") {
          const gap = (product.shadow_gap_mm ?? 80) / 1000;
          addBox(group, `${roomId}_${product.id}_shadow`, [Math.max(width - gap * 2, 0.2), Math.max(depth - gap * 2, 0.2), 0.025], [centerX, centerY, 3.045], shadowMaterial, product.id, roomId);
          addBox(group, `${roomId}_${product.id}_plate`, [Math.max(width - gap * 4, 0.2), Math.max(depth - gap * 4, 0.2), height], [centerX, centerY, centerZ], ceilingMaterial, product.id, roomId);
        } else if (product.family === "modular_panel") {
          const [moduleWidthMm, moduleDepthMm] = product.module_size_mm ?? [600, 1200];
          const moduleWidth = moduleWidthMm / 1000;
          const moduleDepth = moduleDepthMm / 1000;
          const columns = Math.ceil(width / moduleWidth);
          const rows = Math.ceil(depth / moduleDepth);
          for (let column = 0; column < columns; column += 1) {
            for (let row = 0; row < rows; row += 1) {
              const px1 = x1 + column * moduleWidth;
              const py1 = y1 + row * moduleDepth;
              const panelWidth = Math.min(moduleWidth - 0.006, x2 - px1);
              const panelDepth = Math.min(moduleDepth - 0.006, y2 - py1);
              if (panelWidth <= 0 || panelDepth <= 0) continue;
              addBox(group, `${roomId}_${product.id}_${column}_${row}`, [panelWidth, panelDepth, 0.025], [px1 + panelWidth / 2, py1 + panelDepth / 2, 3.07 - height + 0.0125], panelMaterial, product.id, roomId);
            }
          }
        }
      });
    root.add(group);
    });

  return root;
}

function materialAssetId(material: THREE.Material | THREE.Material[]) {
  const first = Array.isArray(material) ? material[0] : material;
  const extra = first?.userData?.asset_id;
  if (typeof extra === "string") return extra;
  const normalized = first?.name?.replace(/^MAT_/, "").replace(/^WEB_/, "");
  return normalized && ASSET_LABELS[normalized] ? normalized : null;
}

function softenWindowFrameMaterial(object: THREE.Mesh) {
  if (object.userData.opening_type !== "window" || !object.name.includes("_frame_")) return;
  const material = new THREE.MeshPhysicalMaterial({
    name: "WEB_window_frame_powder_coated",
    color: "#66645f",
    roughness: 0.5,
    metalness: 0,
    clearcoat: 0.08,
    clearcoatRoughness: 0.62,
  });
  object.material = material;
}

function softenWindowGlassMaterial(object: THREE.Mesh) {
  if (object.userData.opening_type !== "window" || !object.name.endsWith("_glass")) return;
  const material = new THREE.MeshPhysicalMaterial({
    name: "WEB_window_glass_transmissive",
    color: "#d4dddc",
    roughness: 0.16,
    metalness: 0,
    ior: 1.5,
    transmission: 0.92,
    thickness: 0.008,
    envMapIntensity: 0.34,
    transparent: true,
    opacity: 1,
    depthWrite: false,
    side: THREE.DoubleSide,
  });
  object.material = material;
}

function makeExteriorBackdrop() {
  const canvas = document.createElement("canvas");
  canvas.width = 1024;
  canvas.height = 512;
  const context = canvas.getContext("2d")!;
  const sky = context.createLinearGradient(0, 0, 0, 512);
  sky.addColorStop(0, "#98adb1");
  sky.addColorStop(0.58, "#d8d6ca");
  sky.addColorStop(1, "#a7a293");
  context.fillStyle = sky;
  context.fillRect(0, 0, 1024, 512);
  context.fillStyle = "rgba(92,101,99,.16)";
  for (let index = 0; index < 18; index += 1) {
    const width = 24 + (index % 5) * 13;
    const height = 28 + (index * 37) % 92;
    context.fillRect(index * 62 - 20, 360 - height, width, height);
  }
  const texture = new THREE.CanvasTexture(canvas);
  texture.colorSpace = THREE.SRGBColorSpace;
  return texture;
}

function easeInOutCubic(value: number) {
  return value < 0.5 ? 4 * value * value * value : 1 - Math.pow(-2 * value + 2, 3) / 2;
}

export function RoomExperience() {
  const hostRef = useRef<HTMLDivElement>(null);
  const apiRef = useRef<ExperienceApi | null>(null);
  const currentSchemeRef = useRef<Scheme | null>(null);
  const [loadState, setLoadState] = useState<LoadState>("loading");
  const [progress, setProgress] = useState(0);
  const [panelOpen, setPanelOpen] = useState(false);
  const [detailsVisible, setDetailsVisible] = useState(false);
  const [activeRoomId, setActiveRoomId] = useState(DEFAULT_ROOM_ID);
  const [tourProgress, setTourProgress] = useState(0);
  const [tourPlaying, setTourPlaying] = useState(false);
  const [floorChoice, setFloorChoice] = useState<string | null>("floor_light_oak_matte_01");
  const [tileChoice, setTileChoice] = useState<string | null>(null);
  const [ceilingChoice, setCeilingChoice] = useState("ceiling_flat_01");
  const [paintFamilyId, setPaintFamilyId] = useState("warm_white");
  const [paintTone, setPaintTone] = useState<PaintToneId>("light");
  const [paintFinish, setPaintFinish] = useState<PaintFinishId>("matte");
  const [selected, setSelected] = useState<SelectedTarget | null>(null);
  const [currentScheme, setCurrentScheme] = useState<Scheme | null>(null);
  const activeTrack = getRoomCameraTrack(activeRoomId);
  const activeTourStage = tourStageAt(activeTrack, tourProgress);
  const wallTargetSelected = selected?.targetKind === "wall_face";
  const wetWallSelected = wallTargetSelected && selected?.roomId != null && WET_ROOM_IDS.has(selected.roomId);

  function applyScheme(scheme: Scheme) {
    const api = apiRef.current;
    if (!api) return;

    for (const assignment of scheme.assignments) {
      const { target, asset_id } = assignment;
      if (target.kind === "surface" && target.id.includes("ceiling")) {
        api.setCeilingPreset(roomFromCeilingTarget(target.id), asset_id);
      } else {
        api.applyAsset([target.id], asset_id);
      }
    }

    currentSchemeRef.current = scheme;
    setCurrentScheme(scheme);

    for (const a of scheme.assignments) {
      if (a.target.id === "surface_real4_floor_open_public") {
        if (a.asset_id.startsWith("floor_")) {
          setFloorChoice(a.asset_id);
          setTileChoice(null);
        } else if (a.asset_id.startsWith("tile_")) {
          setTileChoice(a.asset_id);
          setFloorChoice(null);
        }
      }
      if (a.target.id === "surface_real4_ceiling_open_public") {
        setCeilingChoice(a.asset_id);
      }
    }
  }

  useEffect(() => {
    // This page is only a renderer worker.  The backend owns tool registration,
    // timeout and the Agent-facing result; the page only executes its commands.
    // Heartbeat and command polling run in a Web Worker so a hidden/throttled
    // tab cannot starve the bridge's online-freshness window or delay commands.
    let cancelled = false;
    const query = new URLSearchParams(window.location.search);
    const sessionId = query.get("render_session") ?? "local-demo";
    // 生产同域托管：默认指向本站 /bridge；本地开发可显式传 ?render_bridge=
    const bridgeUrl = (query.get("render_bridge") ?? `${window.location.origin}/bridge`).replace(/\/$/, "");

    const postResult = async (command: RenderCommand, body: Record<string, unknown>) => {
      await fetch(`${bridgeUrl}/v1/render-sessions/${encodeURIComponent(sessionId)}/commands/${command.id}/result`, {
        method: "POST",
        headers: { "content-type": "application/json" },
        body: JSON.stringify(body),
      });
    };

    const execute = async (command: RenderCommand) => {
      const api = apiRef.current;
      if (!api) throw new Error("renderer_not_ready");
      if (command.tool === "observe_room") {
        if (typeof command.args.room_id !== "string") throw new Error("invalid_observe_room_command");
        return api.observeRoom(command.args.room_id, Array.isArray(command.args.focus_target_ids) ? command.args.focus_target_ids : []);
      }
      return api.observeHomeHarmony();
    };

    const bridgeWorker = new Worker(new URL("./renderBridgeWorker.ts", import.meta.url), { type: "module" });
    bridgeWorker.onmessage = (event: MessageEvent<unknown>) => {
      if (cancelled) return;
      const message = event.data as { type: string; command?: RenderCommand; message?: string };
      if (message.type === "warning") {
        // A disconnected bridge must not destabilize the interactive viewer.
        console.warn("Render bridge unavailable:", message.message);
        return;
      }
      if (message.type !== "command" || !message.command) return;
      const command = message.command;
      execute(command)
        .then((result) => postResult(command, { status: "completed", result }))
        .catch((error) => postResult(command, { status: "failed", error: error instanceof Error ? error.message : String(error) }));
    };
    bridgeWorker.postMessage({ type: "init", sessionId, bridgeUrl });

    return () => { cancelled = true; bridgeWorker.terminate(); };
  }, []);

  useEffect(() => {
    if (loadState !== "ready") return;

    let lastSchemeId = "";

    const poll = () => {
      fetchCurrentScheme()
        .then((data: Scheme) => {
          if (data.scheme_id === lastSchemeId) return;
          lastSchemeId = data.scheme_id;
          applyScheme(data);
        })
        .catch((err) => console.warn("Scheme 加载失败：", err));
    };

    poll(); // 首次立即拉取
    const timer = setInterval(poll, 5_000);
    return () => clearInterval(timer);
  }, [loadState]);

  useEffect(() => {
    if (!selected?.assetId) return;
    const variant = PAINT_VARIANT_BY_ID.get(selected.assetId);
    if (!variant) return;
    setPaintFamilyId(variant.familyId);
    setPaintTone(variant.tone);
    setPaintFinish(variant.finish);
  }, [selected?.assetId]);

  useEffect(() => {
    if (!currentScheme) return;
    const floorAssignment = currentScheme.assignments.find(
      (assignment) => assignment.target.id === activeTrack.surfaceTargets.floor,
    );
    if (floorAssignment?.asset_id.startsWith("floor_")) {
      setFloorChoice(floorAssignment.asset_id);
      setTileChoice(null);
    } else if (floorAssignment?.asset_id.startsWith("tile_")) {
      setTileChoice(floorAssignment.asset_id);
      setFloorChoice(null);
    }

    const ceilingId = activeTrack.surfaceTargets.ceiling;
    const ceilingAssignment = ceilingId
      ? currentScheme.assignments.find((assignment) => assignment.target.id === ceilingId)
      : null;
    if (ceilingAssignment) setCeilingChoice(ceilingAssignment.asset_id);
  }, [activeTrack, currentScheme]);

  useEffect(() => {
    const host = hostRef.current;
    if (!host) return;
    let disposed = false;
    let frame = 0;
    let modelRoot: THREE.Group | null = null;
    const activeCeilingPresets: Record<string, string> = {};
    let detailsVisibleValue = false;
    let activeTrackValue = getRoomCameraTrack(DEFAULT_ROOM_ID);
    let tourDurationMsValue = activeTrackValue.durationMs;
    let tourProgressValue = 0;
    let tourPlayingValue = false;
    let tourStartedAt = 0;
    let tourStartedFrom = 0;
    let lastTourUiUpdate = 0;
    let grid: THREE.GridHelper | null = null;

    const prepareTrack = (track: RoomCameraTrack) => track.keyframes.map((keyframe) => ({
      ...keyframe,
      positionVector: blenderPoint(keyframe.position),
      targetVector: blenderPoint(keyframe.target),
    }));
    let preparedTour = prepareTrack(activeTrackValue);

    const targetIndex = new Map<string, THREE.Mesh[]>();
    const scene = new THREE.Scene();
    const exteriorBackdrop = makeExteriorBackdrop();
    scene.background = exteriorBackdrop;
    scene.fog = new THREE.Fog("#aab5b2", 28, 60);
    scene.environmentIntensity = INDIRECT_DAYLIGHT.environmentIntensity;
    const ceilingPresetRoot = buildCeilingPresetRoot();
    scene.add(ceilingPresetRoot);

    const camera = new THREE.PerspectiveCamera(45, 1, 0.025, 80);
    // Visual-observation tools read the composited canvas after a stable frame.
    // Keeping this buffer makes an explicit tool call reproducible; normal
    // interaction remains on the same single renderer and camera.
    const renderer = new THREE.WebGLRenderer({ antialias: true, alpha: false, preserveDrawingBuffer: true });
    renderer.outputColorSpace = THREE.SRGBColorSpace;
    renderer.toneMapping = THREE.ACESFilmicToneMapping;
    // The old hero-room rig stacked a bright HDR, strong sun and high
    // exposure. In the v4 full-house model that clipped pale materials.
    renderer.toneMappingExposure = 0.86;
    renderer.shadowMap.enabled = true;
    renderer.shadowMap.type = THREE.VSMShadowMap;
    renderer.setPixelRatio(Math.min(window.devicePixelRatio, 2));
    renderer.domElement.className = "room-canvas";
    renderer.domElement.setAttribute("aria-label", "房间级可交互空间体验");
    host.appendChild(renderer.domElement);

    RectAreaLightUniformsLib.init();
    const surfaceMaterials = buildSurfaceMaterials();
    const architecturalRevealMaterial = new THREE.MeshStandardMaterial({
      name: "WEB_architectural_reveal_soft_neutral",
      color: "#aaa49a",
      roughness: 0.92,
      side: THREE.DoubleSide,
    });
    const heroSurfaceRuntime = enhanceHeroSurfaces(surfaceMaterials, renderer);

    const composer = new EffectComposer(renderer);
    composer.addPass(new RenderPass(scene, camera));
    const gtaoPass = new GTAOPass(scene, camera, 1, 1);
    // Keep AO at a real contact-shadow scale. The previous 18 cm radius turned
    // every wall/floor/window junction into a heavy black illustration outline.
    gtaoPass.blendIntensity = 0.17;
    gtaoPass.updateGtaoMaterial({ radius: 0.028, distanceExponent: 1.7, thickness: 0.42, distanceFallOff: 0.94, samples: 16 });
    gtaoPass.updatePdMaterial({ radius: 5, rings: 2, samples: 12, lumaPhi: 8, depthPhi: 2, normalPhi: 3 });
    composer.addPass(gtaoPass);
    composer.addPass(new OutputPass());

    let environmentTexture: THREE.Texture | null = null;
    const pmrem = new THREE.PMREMGenerator(renderer);
    pmrem.compileEquirectangularShader();
    new HDRLoader().load(
      "/assets/hero-living/cayley_interior_1k.hdr",
      (hdr) => {
        if (disposed) {
          hdr.dispose();
          return;
        }
        environmentTexture = pmrem.fromEquirectangular(hdr).texture;
        scene.environment = environmentTexture;
        hdr.dispose();
        pmrem.dispose();
      },
      undefined,
      (error) => console.warn("HDR environment failed to load", error),
    );

    const controls = new OrbitControls(camera, renderer.domElement);
    controls.enableDamping = true;
    controls.dampingFactor = 0.08;
    controls.enablePan = false;
    controls.minPolarAngle = Math.PI * 0.24;
    controls.maxPolarAngle = Math.PI * 0.56;
    controls.minDistance = 1.2;
    controls.maxDistance = 6.5;

    scene.add(new THREE.HemisphereLight(
      INDIRECT_DAYLIGHT.sky,
      INDIRECT_DAYLIGHT.ground,
      INDIRECT_DAYLIGHT.intensity,
    ));
    const sun = new THREE.DirectionalLight("#fff6e7", 1.18);
    sun.position.set(1.5, 10, 5.5);
    sun.castShadow = true;
    sun.shadow.mapSize.set(2048, 2048);
    sun.shadow.bias = -0.00012;
    sun.shadow.normalBias = 0.018;
    sun.shadow.radius = 8;
    sun.shadow.blurSamples = 24;
    sun.shadow.camera.left = -7;
    sun.shadow.camera.right = 7;
    sun.shadow.camera.top = 7;
    sun.shadow.camera.bottom = -7;
    scene.add(sun);
    scene.add(sun.target);
    const updateLightingForTrack = (track: RoomCameraTrack) => {
      const [x1, y1, x2, y2] = track.roomRect;
      const roomCenter = blenderPoint([(x1 + x2) / 2, (y1 + y2) / 2, 1.1]);
      sun.target.position.copy(roomCenter);
      sun.position.copy(roomCenter).add(new THREE.Vector3(-5.5, 8.5, -4.5));
      sun.target.updateMatrixWorld();
    };
    updateLightingForTrack(activeTrackValue);
    const blueFill = new THREE.DirectionalLight("#c4d9e4", 0.08);
    blueFill.position.set(-10, 5, -7);
    scene.add(blueFill);

    grid = new THREE.GridHelper(30, 30, "#35423b", "#202722");
    grid.position.y = -0.085;
    scene.add(grid);

    const resize = () => {
      const width = Math.max(host.clientWidth, 1);
      const height = Math.max(host.clientHeight, 1);
      camera.aspect = width / height;
      camera.updateProjectionMatrix();
      renderer.setSize(width, height, false);
      composer.setSize(width, height);
    };
    const resizeObserver = new ResizeObserver(resize);
    resizeObserver.observe(host);
    resize();

    const updateCeilingVisibility = () => {
      const roomId = activeTrackValue.roomId;
      const roomPreset = activeCeilingPresets[roomId] ?? "ceiling_flat_01";
      ceilingPresetRoot.children.forEach((presetGroup) => {
        const presetId = presetGroup.userData.preset_id as string;
        let hasVisibleBox = false;
        presetGroup.traverse((child) => {
          if (!(child instanceof THREE.Mesh)) return;
          const childRoom = child.userData.room_id;
          const visible = childRoom === roomId && presetId === roomPreset;
          child.visible = visible;
          if (visible) hasVisibleBox = true;
        });
        presetGroup.visible = hasVisibleBox;
      });
    };

    const applyPresentation = () => {
      if (!modelRoot) return;
      modelRoot.traverse((object) => {
        if (!(object instanceof THREE.Mesh)) return;
        const belongsToApartment = object.userData.frontend_scope_visible === true;
        const isReferenceFurniture = object.userData.reference_only === true;
        object.visible = belongsToApartment
          && (!isReferenceFurniture || detailsVisibleValue);
      });
      if (grid) grid.visible = false;
      updateCeilingVisibility();
    };

    const applyTourFrame = (progressValue: number) => {
      const clamped = THREE.MathUtils.clamp(progressValue, 0, 1);
      let nextIndex = preparedTour.findIndex((frameItem) => frameItem.progress >= clamped);
      if (nextIndex <= 0) nextIndex = 1;
      if (nextIndex < 0) nextIndex = preparedTour.length - 1;
      const from = preparedTour[nextIndex - 1];
      const to = preparedTour[nextIndex];
      const segmentProgress = (clamped - from.progress) / Math.max(to.progress - from.progress, 0.0001);
      const eased = easeInOutCubic(THREE.MathUtils.clamp(segmentProgress, 0, 1));
      camera.position.lerpVectors(from.positionVector, to.positionVector, eased);
      controls.target.lerpVectors(from.targetVector, to.targetVector, eased);
      camera.fov = THREE.MathUtils.lerp(from.fov, to.fov, eased);
      camera.updateProjectionMatrix();
      controls.update();
    };

    const setTourProgressValue = (nextProgress: number) => {
      tourProgressValue = THREE.MathUtils.clamp(nextProgress, 0, 1);
      applyTourFrame(tourProgressValue);
    };

    const setTourPlayingValue = (playing: boolean) => {
      tourPlayingValue = playing;
      controls.enabled = !playing;
      if (playing) {
        if (tourProgressValue >= 0.999) {
          tourProgressValue = 0;
          setTourProgress(0);
          applyTourFrame(0);
        }
        tourStartedAt = performance.now();
        tourStartedFrom = tourProgressValue;
      }
    };

    const waitForStableRender = () => new Promise<void>((resolve) => {
      // requestAnimationFrame is suspended in a hidden/backgrounded tab, which
      // would deadlock visual observation.  When the tab is (or becomes) hidden,
      // resolve on an unthrottled MessageChannel macrotask instead so the
      // explicit composer.render() below can still capture a frame.
      if (document.visibilityState === "hidden") {
        const channel = new MessageChannel();
        channel.port1.onmessage = () => resolve();
        channel.port2.postMessage(undefined);
        return;
      }
      let settled = false;
      const settle = () => { if (!settled) { settled = true; resolve(); } };
      const onVisibilityChange = () => { if (document.hidden) settle(); };
      document.addEventListener("visibilitychange", onVisibilityChange);
      requestAnimationFrame(() => requestAnimationFrame(() => {
        document.removeEventListener("visibilitychange", onVisibilityChange);
        settle();
      }));
    });

    const captureImageDataUrl = () => {
      // Keep the tool payload bounded and independent of the browser viewport.
      // The source has already passed through ACES, GTAO and OutputPass.
      const source = renderer.domElement;
      const width = 1280;
      const height = Math.max(1, Math.round(width * source.height / Math.max(source.width, 1)));
      const captureCanvas = document.createElement("canvas");
      captureCanvas.width = width;
      captureCanvas.height = height;
      const context = captureCanvas.getContext("2d");
      if (!context) throw new Error("浏览器不支持用于视觉观察的 2D Canvas。");
      context.drawImage(source, 0, 0, width, height);
      return captureCanvas.toDataURL("image/jpeg", 0.9);
    };

    const waitForActivePbr = async () => {
      const pending = new Set<Promise<unknown>>();
      targetIndex.forEach((meshes) => meshes.forEach((mesh) => {
        const ensured = (mesh.material as THREE.Material & { userData: { ensurePbr?: () => unknown } })
          .userData.ensurePbr?.();
        if (ensured instanceof Promise) pending.add(ensured);
      }));
      await Promise.all(pending);
      await waitForStableRender();
    };

    const captureInspectionViews = async (
      roomId: string,
      views: RoomInspectionView[],
    ): Promise<VisualImage[]> => {
      const previousTrack = activeTrackValue;
      const previousPreparedTour = preparedTour;
      const previousDuration = tourDurationMsValue;
      const previousProgress = tourProgressValue;
      const wasPlaying = tourPlayingValue;
      const previousDetailsVisible = detailsVisibleValue;

      setTourPlayingValue(false);
      activeTrackValue = getRoomCameraTrack(roomId);
      tourDurationMsValue = activeTrackValue.durationMs;
      preparedTour = prepareTrack(activeTrackValue);
      detailsVisibleValue = false;
      updateLightingForTrack(activeTrackValue);
      updateCeilingVisibility();
      applyPresentation();

      try {
        await waitForActivePbr();
        const captures: VisualImage[] = [];
        for (const view of views) {
          setTourProgressValue(view.sourceProgress);
          await waitForStableRender();
          composer.render();
          captures.push({
            viewId: view.id,
            label: view.label,
            purpose: view.purpose,
            focusTargetIds: view.focusTargetIds,
            imageDataUrl: captureImageDataUrl(),
          });
        }
        return captures;
      } finally {
        activeTrackValue = previousTrack;
        preparedTour = previousPreparedTour;
        tourDurationMsValue = previousDuration;
        detailsVisibleValue = previousDetailsVisible;
        updateLightingForTrack(previousTrack);
        updateCeilingVisibility();
        applyPresentation();
        setTourProgressValue(previousProgress);
        if (wasPlaying) setTourPlayingValue(true);
      }
    };

    const captureRoomObservation = async (
      roomId: string,
      focusTargetIds: string[] = [],
    ): Promise<RoomObservationResult> => {
      const plan = createRoomObservationPlan(roomId, focusTargetIds);
      const views = await captureInspectionViews(plan.roomId, plan.views);
      const scheme = currentSchemeRef.current;
      return {
        tool: "observe_room",
        status: plan.uncoveredTargetIds.length === 0 ? "ready" : "incomplete_observation",
        evidenceLevel: "declared_track_coverage",
        houseId: plan.houseId,
        scheme: { schemeId: scheme?.scheme_id ?? null, title: scheme?.title ?? null },
        room: { id: plan.roomId, label: plan.roomLabel },
        views,
        declaredCoverage: plan.declaredCoverage,
        uncoveredTargetIds: plan.uncoveredTargetIds,
      };
    };

    const composeRoomContactSheet = async (roomImages: Array<{ roomLabel: string; imageDataUrl: string }>) => {
      const columns = 3;
      const cellWidth = 320;
      const imageHeight = 180;
      const labelHeight = 34;
      const rows = Math.ceil(roomImages.length / columns);
      const sheet = document.createElement("canvas");
      sheet.width = columns * cellWidth;
      sheet.height = rows * (imageHeight + labelHeight);
      const context = sheet.getContext("2d");
      if (!context) throw new Error("浏览器不支持全屋总览图生成。");
      context.fillStyle = "#171816";
      context.fillRect(0, 0, sheet.width, sheet.height);

      await Promise.all(roomImages.map(async (roomImage, index) => {
        const image = new Image();
        image.src = roomImage.imageDataUrl;
        await image.decode();
        const column = index % columns;
        const row = Math.floor(index / columns);
        const x = column * cellWidth;
        const y = row * (imageHeight + labelHeight);
        context.drawImage(image, x, y, cellWidth, imageHeight);
        context.fillStyle = "rgba(16, 17, 15, .88)";
        context.fillRect(x, y + imageHeight, cellWidth, labelHeight);
        context.fillStyle = "#f2ecdf";
        context.font = "600 15px system-ui, sans-serif";
        context.fillText(roomImage.roomLabel, x + 12, y + imageHeight + 22);
      }));
      return sheet.toDataURL("image/jpeg", 0.9);
    };

    const viewAtProgress = (roomId: string, progressValue: number, purpose: string): RoomInspectionView => {
      const track = getRoomCameraTrack(roomId);
      const frame = track.keyframes.find((candidate) => candidate.progress === progressValue) ?? track.keyframes[0];
      return {
        id: `harmony_${roomId}_${Math.round(frame.progress * 1000)}`,
        purpose: purpose === "transition" ? "coverage" : "establish",
        sourceProgress: frame.progress,
        label: frame.label,
        description: frame.description,
        focusTargetIds: frame.focusTargetIds,
      };
    };

    const captureTransitionPair = async (transition: HomeHarmonyTransition) => {
      const [from] = await captureInspectionViews(transition.fromRoomId, [
        viewAtProgress(transition.fromRoomId, transition.fromProgress, "transition"),
      ]);
      const [to] = await captureInspectionViews(transition.toRoomId, [
        viewAtProgress(transition.toRoomId, transition.toProgress, "transition"),
      ]);
      return {
        id: transition.id,
        openingId: transition.openingId,
        rationale: transition.rationale,
        from,
        to,
      };
    };

    const captureHomeHarmony = async (): Promise<HomeHarmonyObservationResult> => {
      const plan = createHomeHarmonyPlan();
      const incompleteRooms = ROOM_CAMERA_TRACKS.map((track) => createRoomObservationPlan(track.roomId))
        .filter((roomPlan) => roomPlan.uncoveredTargetIds.length > 0)
        .map((roomPlan) => ({ roomId: roomPlan.roomId, uncoveredTargetIds: roomPlan.uncoveredTargetIds }));
      const scheme = currentSchemeRef.current;

      if (incompleteRooms.length > 0) {
        return {
          tool: "observe_home_harmony",
          status: "incomplete_observation",
          evidenceLevel: "declared_track_coverage",
          houseId: plan.houseId,
          scheme: { schemeId: scheme?.scheme_id ?? null, title: scheme?.title ?? null },
          roomContactSheet: "",
          transitionPairs: [],
          incompleteRooms,
        };
      }

      const heroImages: Array<{ roomLabel: string; imageDataUrl: string }> = [];
      for (const hero of plan.roomHeroViews) {
        const [image] = await captureInspectionViews(hero.roomId, [
          viewAtProgress(hero.roomId, hero.sourceProgress, "hero"),
        ]);
        heroImages.push({ roomLabel: hero.roomLabel, imageDataUrl: image.imageDataUrl });
      }

      const transitionPairs = [];
      for (const transition of plan.transitions) {
        transitionPairs.push(await captureTransitionPair(transition));
      }

      return {
        tool: "observe_home_harmony",
        status: "ready",
        evidenceLevel: "declared_track_coverage",
        houseId: plan.houseId,
        scheme: { schemeId: scheme?.scheme_id ?? null, title: scheme?.title ?? null },
        roomContactSheet: await composeRoomContactSheet(heroImages),
        transitionPairs,
        incompleteRooms: [],
      };
    };

    const applyAsset = (targetIds: string[], assetId: string) => {
      const material = surfaceMaterials.get(assetId);
      if (!material) return;
      material.userData.ensurePbr?.();
      targetIds.forEach((targetId) => {
        targetIndex.get(targetId)?.forEach((mesh) => {
          mesh.material = material;
          mesh.userData.currentAssetId = assetId;
        });
      });
      const activeAssetIds = new Set<string>();
      targetIndex.forEach((meshes) => meshes.forEach((mesh) => {
        const currentAssetId = mesh.userData.currentAssetId;
        if (typeof currentAssetId === "string") activeAssetIds.add(currentAssetId);
      }));
      heroSurfaceRuntime.releaseUnusedWallpaperMaps(activeAssetIds);
      surfaceMaterials.forEach((candidate, candidateId) => {
        if ((candidateId.startsWith("floor_") || candidateId.startsWith("tile_")) && !activeAssetIds.has(candidateId)) {
          candidate.userData.releasePbr?.();
        }
      });
      setSelected((current) => current && targetIds.includes(current.targetId) ? { ...current, assetId } : current);
    };

    const setCeilingPreset = (roomId: string, presetId: string) => {
      activeCeilingPresets[roomId] = presetId;
      updateCeilingVisibility();
      const targetId = `surface_real4_ceiling_${roomId}`;
      const meshes = targetIndex.get(targetId) ?? [];
      meshes.forEach((mesh) => { mesh.userData.currentAssetId = presetId; });
      setSelected((current) => current?.targetId.includes("_ceiling_") ? { ...current, assetId: presetId } : current);
    };

    apiRef.current = {
      applyAsset,
      setCeilingPreset,
      setDetailsVisible: (visible) => {
        detailsVisibleValue = visible;
        applyPresentation();
      },
      setActiveTrack: (roomId) => {
        activeTrackValue = getRoomCameraTrack(roomId);
        tourDurationMsValue = activeTrackValue.durationMs;
        preparedTour = prepareTrack(activeTrackValue);
        updateLightingForTrack(activeTrackValue);
        updateCeilingVisibility();
        setTourPlayingValue(false);
        setTourProgressValue(0);
        setSelected(null);
        renderer.domElement.setAttribute(
          "aria-label",
          `${activeTrackValue.roomLabel}可交互空间体验`,
        );
      },
      setTourProgress: (nextProgress) => {
        setTourPlayingValue(false);
        setTourProgressValue(nextProgress);
      },
      setTourPlaying: setTourPlayingValue,
      observeRoom: captureRoomObservation,
      observeHomeHarmony: captureHomeHarmony,
    };

    const loader = new GLTFLoader();
    loader.load(
      "/models/house_spacious_yunkuo_135_v4.glb?revision=hard-finish-realism-pass-v3-wall-sides",
      (gltf) => {
        if (disposed) return;
        modelRoot = gltf.scene;
        modelRoot.name = "house_spacious_yunkuo_135_v4";
        modelRoot.traverse((object) => {
          if (!(object instanceof THREE.Mesh)) return;
          const isContextOnly = object.userData.context_only === true;
          const isVisible = !isContextOnly;
          object.userData.frontend_scope_visible = isVisible;
          object.visible = isVisible;
          object.receiveShadow = true;
          object.castShadow = object.userData.reference_only === true
            || object.userData.surface_role === "wall_core"
            || typeof object.userData.opening_id === "string";
          if (object.userData.surface_role === "wall_core") {
            object.material = architecturalRevealMaterial;
          }
          softenWindowFrameMaterial(object);
          softenWindowGlassMaterial(object);
          const targetId = object.userData.wall_face_id ?? object.userData.surface_id;
          if (isVisible && typeof targetId === "string") {
            const entries = targetIndex.get(targetId) ?? [];
            entries.push(object);
            targetIndex.set(targetId, entries);
          }
          const assetId = materialAssetId(object.material);
          if (assetId && surfaceMaterials.has(assetId)) {
            object.material = surfaceMaterials.get(assetId)!;
            object.userData.currentAssetId = assetId;
            object.material.userData.ensurePbr?.();
          }
        });
        scene.add(modelRoot);
        applyPresentation();
        setTourProgressValue(0);
        setProgress(82);

        const finishInitialSurfaceLoad = async () => {
          try {
            const scheme = await fetchCurrentScheme();
            applyScheme(scheme);
            setProgress(90);
            const activePbrLoads = scheme.assignments
              .map((assignment) => surfaceMaterials.get(assignment.asset_id)?.userData.ensurePbr?.())
              .filter((pending): pending is Promise<unknown> => pending instanceof Promise);
            await Promise.all([heroSurfaceRuntime.ready, ...activePbrLoads]);
          } catch (error) {
            console.warn("初始材质方案加载失败：", error);
          }
          if (disposed) return;
          setProgress(100);
          setLoadState("ready");
        };
        void finishInitialSurfaceLoad();
      },
      (event) => event.total > 0 && setProgress(Math.round((event.loaded / event.total) * 100)),
      (error) => {
        console.error(error);
        if (!disposed) setLoadState("error");
      },
    );

    const pointer = new THREE.Vector2();
    const raycaster = new THREE.Raycaster();
    const onPointerUp = (event: PointerEvent) => {
      if (!modelRoot || event.button !== 0) return;
      const rect = renderer.domElement.getBoundingClientRect();
      pointer.set(
        ((event.clientX - rect.left) / rect.width) * 2 - 1,
        -((event.clientY - rect.top) / rect.height) * 2 + 1,
      );
      raycaster.setFromCamera(pointer, camera);
      const match = raycaster.intersectObject(modelRoot, true).find(
        (hit) => hit.object.visible && (
          typeof hit.object.userData.wall_face_id === "string"
          || typeof hit.object.userData.surface_id === "string"
        ),
      );
      if (!match || !(match.object instanceof THREE.Mesh)) return;
      const mesh = match.object;
      const assetId = mesh.userData.currentAssetId ?? materialAssetId(mesh.material);
      const wallFaceId = mesh.userData.wall_face_id;
      const targetId = typeof wallFaceId === "string" ? wallFaceId : mesh.userData.surface_id;
      if (typeof targetId !== "string") return;
      setSelected({
        targetId,
        targetKind: typeof wallFaceId === "string" ? "wall_face" : "surface",
        assetId: typeof assetId === "string" ? assetId : null,
        displayCode: typeof mesh.userData.wall_code === "string" ? mesh.userData.wall_code : null,
        displayName: typeof mesh.userData.wall_name_zh === "string" ? mesh.userData.wall_name_zh : null,
        roomId: typeof mesh.userData.room_id === "string" ? mesh.userData.room_id : null,
      });
    };
    renderer.domElement.addEventListener("pointerup", onPointerUp);

    const animate = (time: number) => {
      if (tourPlayingValue) {
        const elapsedProgress = (time - tourStartedAt) / tourDurationMsValue;
        const nextProgress = Math.min(1, tourStartedFrom + elapsedProgress);
        tourProgressValue = nextProgress;
        applyTourFrame(nextProgress);
        if (time - lastTourUiUpdate > 40 || nextProgress >= 1) {
          setTourProgress(nextProgress);
          lastTourUiUpdate = time;
        }
        if (nextProgress >= 1) {
          tourPlayingValue = false;
          controls.enabled = true;
          setTourPlaying(false);
        }
      }
      controls.update();
      composer.render();
      frame = requestAnimationFrame(animate);
    };
    frame = requestAnimationFrame(animate);

    return () => {
      disposed = true;
      cancelAnimationFrame(frame);
      resizeObserver.disconnect();
      renderer.domElement.removeEventListener("pointerup", onPointerUp);
      controls.dispose();
      composer.dispose();
      renderer.dispose();
      environmentTexture?.dispose();
      pmrem.dispose();
      heroSurfaceRuntime.dispose();
      exteriorBackdrop.dispose();
      architecturalRevealMaterial.dispose();
      ceilingPresetRoot.traverse((object) => {
        if (!(object instanceof THREE.Mesh)) return;
        object.geometry.dispose();
        if (Array.isArray(object.material)) object.material.forEach((material) => material.dispose());
        else object.material.dispose();
      });
      surfaceMaterials.forEach((material) => {
        material.map?.dispose();
        material.normalMap?.dispose();
        material.roughnessMap?.dispose();
        material.dispose();
      });
      if (host.contains(renderer.domElement)) host.removeChild(renderer.domElement);
      apiRef.current = null;
    };
  }, []);

  const jumpTour = (nextProgress: number) => {
    setTourPlaying(false);
    setTourProgress(nextProgress);
    apiRef.current?.setTourProgress(nextProgress);
  };

  const chooseRoom = (roomId: string) => {
    setTourPlaying(false);
    setTourProgress(0);
    setActiveRoomId(roomId);
    apiRef.current?.setActiveTrack(roomId);
  };

  const toggleTour = () => {
    const nextPlaying = !tourPlaying;
    setTourPlaying(nextPlaying);
    apiRef.current?.setTourPlaying(nextPlaying);
  };

  const chooseFloor = (assetId: string) => {
    setFloorChoice(assetId);
    setTileChoice(null);
    apiRef.current?.applyAsset([activeTrack.surfaceTargets.floor], assetId);
  };

  const chooseWallAsset = (assetId: string) => {
    if (selected?.targetKind !== "wall_face") return;
    apiRef.current?.applyAsset([selected.targetId], assetId);
  };

  const choosePaint = (
    nextFamilyId: string = paintFamilyId,
    nextTone: PaintToneId = paintTone,
    nextFinish: PaintFinishId = paintFinish,
  ) => {
    setPaintFamilyId(nextFamilyId);
    setPaintTone(nextTone);
    setPaintFinish(nextFinish);
    const variant = findPaintVariant(nextFamilyId, nextTone, nextFinish);
    if (variant) chooseWallAsset(variant.id);
  };

  const chooseTile = (assetId: string) => {
    setTileChoice(assetId);
    if (wetWallSelected && selected) {
      apiRef.current?.applyAsset([selected.targetId], assetId);
    } else {
      setFloorChoice(null);
      apiRef.current?.applyAsset([activeTrack.surfaceTargets.floor], assetId);
    }
  };

  const chooseCeiling = (assetId: string) => {
    setCeilingChoice(assetId);
    apiRef.current?.setCeilingPreset(activeRoomId, assetId);
  };

  const toggleDetails = () => {
    const next = !detailsVisible;
    setDetailsVisible(next);
    apiRef.current?.setDetailsVisible(next);
  };

  return (
    <main className="room-experience">
      <div ref={hostRef} className="room-canvas-host" />

      <header className="room-header">
        <div className="room-brand">
          <span>H</span>
          <div><small>HOUSE DESIGN LAB</small><strong>房间设计实验室</strong></div>
        </div>
        <div className={`model-status ${loadState}`}>
          <i />{loadState === "ready" ? `${activeTrack.roomLabel} · 实时场景` : loadState === "error" ? "加载失败" : `加载 ${progress}%`}
        </div>
        <div className="header-actions">
          <button type="button" className={panelOpen ? "active" : ""} onClick={() => setPanelOpen(!panelOpen)}>方案面板</button>
        </div>
      </header>

      <nav className="room-track-nav" aria-label="房间摄像机轨迹">
        {ROOM_CAMERA_TRACKS.map((track) => (
          <button
            type="button"
            key={track.roomId}
            className={activeRoomId === track.roomId ? "active" : ""}
            aria-pressed={activeRoomId === track.roomId}
            disabled={loadState !== "ready"}
            onClick={() => chooseRoom(track.roomId)}
          >
            {track.roomLabel}
          </button>
        ))}
      </nav>

      <section className="room-caption" aria-live="polite">
        <p>{activeTrack.roomLabel} · {formatTourTime(tourProgress, activeTrack.durationMs)}</p>
        <h1>{activeTourStage.label}</h1>
        <span>{activeTourStage.description}</span>
      </section>

      <section className="human-tour" aria-label={`${activeTrack.roomLabel}独立摄像机轨迹`}>
        <div className="tour-heading">
          <button type="button" disabled={loadState !== "ready"} aria-label={tourPlaying ? `暂停${activeTrack.roomLabel}导览` : `播放${activeTrack.roomLabel}导览`} onClick={toggleTour}>
            {tourPlaying ? "Ⅱ" : "▶"}
          </button>
          <div><small>ROOM CAMERA TRACK</small><strong>{activeTrack.roomLabel} · {activeTourStage.label}</strong></div>
          <span>{formatTourTime(tourProgress, activeTrack.durationMs)} / {formatTourTime(1, activeTrack.durationMs)}</span>
        </div>
        <input
          type="range"
          min="0"
          max="1000"
          step="1"
          value={Math.round(tourProgress * 1000)}
          style={{ background: `linear-gradient(90deg, #d9a25a 0 ${tourProgress * 100}%, rgba(255,255,255,.18) ${tourProgress * 100}% 100%)` }}
          aria-label={`${activeTrack.roomLabel}摄像机轨迹进度`}
          aria-valuetext={`${activeTourStage.label}，${formatTourTime(tourProgress, activeTrack.durationMs)}`}
          onPointerDown={() => {
            setTourPlaying(false);
            apiRef.current?.setTourPlaying(false);
          }}
          onInput={(event) => jumpTour(Number(event.currentTarget.value) / 1000)}
        />
        <div className="tour-stages" aria-hidden="true">
          {activeTrack.keyframes.map((frameItem) => <span key={frameItem.label} style={{ left: `${frameItem.progress * 100}%` }}>{frameItem.label}</span>)}
        </div>
        <p>每个空间独立验收 · 稳定视平线 · 入口与出口可串接 · 不做 360° 旋转</p>
      </section>

      <p className="room-gesture">暂停时可拖动环视 · 滚轮缩放 · 点击表面查看材料</p>

      {loadState !== "ready" && (
        <div className="room-loader" role="status">
          <div><i /></div>
          <p>{loadState === "error" ? "模型加载失败，请刷新重试。" : "正在加载场景与灯光…"}</p>
          {loadState === "loading" && <span><b style={{ width: `${progress}%` }} /></span>}
        </div>
      )}

      <aside className={`scheme-drawer ${panelOpen ? "open" : ""}`} aria-label="实时方案面板">
        <div className="drawer-head">
          <div>
            <small>LIVE SCHEME</small>
            <h2>{currentScheme?.title ?? "等待方案…"}</h2>
            <p>
              {currentScheme
                ? `${currentScheme.assignments.length} 项配置 · ${currentScheme.scheme_id}`
                : "5 品类 · 87 个资产 / 预设"}
            </p>
          </div>
          <button type="button" aria-label="关闭方案面板" onClick={() => setPanelOpen(false)}>×</button>
        </div>

        <section>
          <div className="drawer-title"><span>·</span><div><h3>家具与软装</h3><p>默认隐藏，仅硬装表面；可临时加载检查尺度</p></div></div>
          <button type="button" className={`detail-toggle ${detailsVisible ? "active" : ""}`} onClick={toggleDetails}>
            <i /><span>{detailsVisible ? "隐藏空间参照家具" : "显示空间参照家具"}</span>
          </button>
        </section>

        <section>
          <div className="drawer-title"><span>01</span><div><h3>墙漆 · 60</h3><p>{wetWallSelected ? "当前为湿区墙面，仅允许瓷砖" : "先点击墙面，再选择色系、明度与漆面"}</p></div></div>
          <div className="paint-family-grid" aria-label="墙漆色彩家族">
            {PAINT_CATALOG.families.map((family) => (
              <button
                type="button"
                key={family.id}
                disabled={!wallTargetSelected || wetWallSelected}
                aria-pressed={paintFamilyId === family.id}
                className={paintFamilyId === family.id ? "selected" : ""}
                title={family.description}
                onClick={() => choosePaint(family.id)}
              >
                <i style={{ background: family.colors[paintTone] }} />
                <span>{family.name_zh.split("与")[0].replace("、", " / ")}</span>
              </button>
            ))}
          </div>
          <div className="paint-parameters">
            <div><small>明度</small><div role="group" aria-label="墙漆明度">
              {PAINT_CATALOG.tones.map((tone) => <button type="button" key={tone.id} disabled={!wallTargetSelected || wetWallSelected} className={paintTone === tone.id ? "selected" : ""} onClick={() => choosePaint(paintFamilyId, tone.id)}>{tone.name_zh}</button>)}
            </div></div>
            <div><small>漆面</small><div role="group" aria-label="墙漆漆面">
              {PAINT_CATALOG.finishes.map((finish) => <button type="button" key={finish.id} disabled={!wallTargetSelected || wetWallSelected} className={paintFinish === finish.id ? "selected" : ""} onClick={() => choosePaint(paintFamilyId, paintTone, finish.id)}>{finish.name_zh}</button>)}
            </div></div>
          </div>
          <p className="paint-notice">4K 真实尺度微表面 · 屏幕预览不替代实体色卡</p>
        </section>

        <section>
          <div className="drawer-title"><span>02</span><div><h3>墙纸 · 8</h3><p>真实比例与对花规则，按需加载 PBR</p></div></div>
          <div className="material-options">
            {WALLPAPERS.map((product) => (
              <button
                type="button"
                key={product.id}
                disabled={!wallTargetSelected || wetWallSelected}
                aria-pressed={wallTargetSelected && selected?.assetId === product.id}
                className={wallTargetSelected && selected?.assetId === product.id ? "selected" : ""}
                title={`${product.description_zh} · ${product.repeat_size_m.join(" × ")}m · ${product.match_type}`}
                onClick={() => chooseWallAsset(product.id)}
              >
                <i style={{ background: `${product.tint} url('/assets/wallpapers/${product.id}_thumb.webp') center / cover` }} />
                <span>{product.name_zh}</span>
              </button>
            ))}
          </div>
          <p className="paint-notice">4K 母版 · 毫米级微表面 · 壁画为 4.40 × 2.80m 非循环分幅</p>
        </section>

        <section>
          <div className="drawer-title"><span>03</span><div><h3>地板 · 6</h3><p>真实板宽与铺法元数据，作用于当前房间地面</p></div></div>
          <div className="material-options">
            {FLOORS.map((product) => (
              <button type="button" key={product.id} aria-pressed={floorChoice === product.id} className={floorChoice === product.id ? "selected" : ""} title={`${product.repeat_size_m.join(" × ")}m · ${product.supported_layouts.join(" / ")}`} onClick={() => chooseFloor(product.id)}>
                <i style={{ background: `${product.tint} url('/assets/surfaces/${product.id}_thumb.webp') center / cover` }} />
                <span>{product.name_zh.replace("地板", "")}</span>
              </button>
            ))}
          </div>
        </section>

        <section>
          <div className="drawer-title"><span>04</span><div><h3>瓷砖 · 8</h3><p>{wetWallSelected ? "作用于当前选中的湿区墙面" : "与木地板互斥，切换当前房间地面"}</p></div></div>
          <div className="material-options">
            {TILES.map((product) => (
              <button type="button" key={product.id} aria-pressed={tileChoice === product.id} className={tileChoice === product.id ? "selected" : ""} title={`${product.repeat_size_m.join(" × ")}m · ${product.supported_layouts.join(" / ")}`} onClick={() => chooseTile(product.id)}>
                <i style={{ background: `${product.tint} url('/assets/surfaces/${product.id}_thumb.webp') center / cover` }} />
                <span>{product.name_zh.replace("瓷砖", "").replace("砖", "")}</span>
              </button>
            ))}
          </div>
        </section>

        <section>
          <div className="drawer-title"><span>05</span><div><h3>吊顶 · 5</h3><p>真实几何预设；厨卫大板仅适用于湿区</p></div></div>
          <div className="material-options">
            {CEILINGS.map((product) => {
              const suitable = product.family === "flat"
                || (product.family === "modular_panel" ? WET_ROOM_IDS.has(activeRoomId) : !WET_ROOM_IDS.has(activeRoomId));
              return (
                <button type="button" key={product.id} disabled={!suitable} aria-pressed={ceilingChoice === product.id} className={ceilingChoice === product.id ? "selected" : ""} title={`下降 ${product.drop_height_mm}mm`} onClick={() => chooseCeiling(product.id)}>
                  <i style={{ background: product.family === "modular_panel" ? "repeating-linear-gradient(90deg,#c8cbc6 0 32%,#7b7f7a 32% 33%)" : product.family === "floating_shadow_gap" ? "radial-gradient(circle,#ece7da 45%,#242725 47% 52%,#d8d2c4 54%)" : product.family === "perimeter_cove" ? "linear-gradient(135deg,#e8e1d2 48%,#f0ad62 50%,#2d302e 54%)" : "linear-gradient(135deg,#ece7da,#c8c0b0)" }} />
                  <span>{product.name_zh.replace("吊顶", "")}</span>
                </button>
              );
            })}
          </div>
        </section>

        <section className="surface-readout">
          <small>当前 Agent 目标</small>
          {selected ? (
            <>
              <strong>{selected.displayName ?? ASSET_LABELS[selected.assetId ?? ""] ?? "结构表面"}</strong>
              <p>{ASSET_LABELS[selected.assetId ?? ""] ?? "未配置 Asset"}</p>
              <code>{selected.displayCode ? `${selected.displayCode} · ` : ""}{selected.targetId}</code>
            </>
          ) : (
            <p>点击墙面读取 `wall_face_id`；墙漆和墙纸只修改这一面墙。</p>
          )}
        </section>
      </aside>
    </main>
  );
}
