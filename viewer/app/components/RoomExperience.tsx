"use client";

import Link from "next/link";
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
  SPECIALTY_PAINTS,
  resolvePaintSelection,
  type PaintParameters,
  type PaintFinishId,
  type PaintToneId,
} from "../data/paintCatalog";
import { WALLPAPER_APPEARANCE_CALIBRATION, WALLPAPERS } from "../data/wallpaperCatalog";
import { CEILINGS, FLOORS, TILES, FLOOR_TILE_APPEARANCE_CALIBRATION, WALL_TILE_APPEARANCE_CALIBRATION } from "../data/surfaceCatalog";
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
  HOME_HERO_MAX_CANDIDATES,
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

function designRunIdFromLocation(): string | null {
  if (typeof window === "undefined") return null;
  return new URLSearchParams(window.location.search).get("design_run_id");
}

async function fetchCurrentScheme(designRunId?: string | null): Promise<Scheme> {
  if (AGENT_API_URL || designRunId) {
    const base = AGENT_API_URL ? `${AGENT_API_URL}/api` : "/chat-proxy";
    const query = designRunId
      ? `?design_run_id=${encodeURIComponent(designRunId)}`
      : "";
    const response = await fetch(`${base}/scheme${query}`, { cache: "no-store" });
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
  applyAsset: (
    targetIds: string[],
    assetId: string,
    parameters?: PaintParameters | null,
    reconcile?: boolean,
  ) => void;
  reconcileAssets: () => void;
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
  quality: {
    valid: boolean;
    meanLuminance: number;
    luminanceStdDev: number;
    darkPixelRatio: number;
    reasons: string[];
  };
  targetVisibility: Array<{
    targetId: string;
    pixelCount: number;
    pixelRatio: number;
    boundingBox: { x: number; y: number; width: number; height: number } | null;
    readable: boolean;
  }>;
  maskQuality: {
    occluderPixelRatio: number;
    backgroundPixelRatio: number;
  };
};

type RoomObservationResult = {
  tool: "observe_room";
  status: "ready" | "incomplete_observation";
  evidenceLevel: "pixel_verified_coverage";
  houseId: string;
  scheme: { schemeId: string | null; title: string | null };
  room: { id: string; label: string };
  views: VisualImage[];
  plannedCoverage: Record<string, string[]>;
  verifiedCoverage: Record<string, string[]>;
  uncoveredTargetIds: string[];
  invalidViewIds: string[];
  topologyAnomalyTargetIds: string[];
};

type HomeHarmonyObservationResult = {
  tool: "observe_home_harmony";
  status: "ready" | "incomplete_observation";
  evidenceLevel: "pixel_verified_coverage";
  houseId: string;
  scheme: { schemeId: string | null; title: string | null };
  roomContactSheet: string;
  transitionPairs: Array<{
    id: string;
    openingId: string;
    rationale: string;
    status: "ready" | "incomplete_observation";
    openingCenter: [number, number, number];
    from: VisualImage;
    to: VisualImage;
  }>;
  incompleteRooms: Array<{ roomId: string; uncoveredTargetIds: string[]; invalidViewIds: string[] }>;
  invalidHeroRoomIds: string[];
  roomHeroDiagnostics: Array<{
    roomId: string;
    selectedViewId: string;
    score: number;
    quality: VisualImage["quality"];
    targetVisibility: VisualImage["targetVisibility"];
    maskQuality: VisualImage["maskQuality"];
  }>;
  captureDiagnostics: {
    durationMs: number;
    heroCandidateCount: number;
    heroCandidateLimitPerRoom: number;
    transitionImageCount: number;
  };
};

type RenderCommand = {
  id: string;
  tool: "observe_room" | "observe_home_harmony";
  args: { room_id?: string; focus_target_ids?: string[]; design_run_id?: string };
};

const ASSET_LABELS: Record<string, string> = {
  ...Object.fromEntries(PAINT_VARIANTS.map((variant) => [variant.id, variant.nameZh])),
  ...Object.fromEntries(WALLPAPERS.map((product) => [product.id, `${product.name_zh}墙纸`])),
  ...Object.fromEntries(FLOORS.map((product) => [product.id, product.name_zh])),
  ...Object.fromEntries(TILES.map((product) => [product.id, product.name_zh])),
  ...Object.fromEntries(CEILINGS.map((product) => [product.id, product.name_zh])),
};

const WET_ROOM_IDS = new Set(["kitchen", "guest_bath", "master_bath"]);

// Visual-observation captures must not depend on the on-screen canvas size.
// The live canvas is normally ≥340px wide; if it ever collapses (3D panel
// hidden in a way that leaves the host at ~0px), render the evidence at this
// fixed minimum instead of upscaling a 1px strip into a degenerate image.
const EVIDENCE_WIDTH = 1280;
const EVIDENCE_HEIGHT = 720;
const VISIBILITY_WIDTH = 320;
const VISIBILITY_HEIGHT = 180;
const MIN_TARGET_PIXEL_RATIO = 0.004;
const MIN_TARGET_BOUNDING_DIMENSION = 8;
const MAX_RENDER_PIXEL_RATIO = 1.25;
const GTAO_RESOLUTION_SCALE = 0.67;
const HOME_HERO_WIDTH = 640;
const HOME_HERO_HEIGHT = 360;

const CEILING_APPEARANCE_CALIBRATION = {
  baseColour: "#eee9de",
  directionalLightShare: 0.38,
  materialColourShare: 0.62,
} as const;

function makeCeilingFinishMaterial(name: string) {
  return new THREE.MeshStandardMaterial({
    name,
    color: new THREE.Color(CEILING_APPEARANCE_CALIBRATION.baseColour).multiplyScalar(
      CEILING_APPEARANCE_CALIBRATION.directionalLightShare,
    ),
    emissive: new THREE.Color(CEILING_APPEARANCE_CALIBRATION.baseColour).multiplyScalar(
      CEILING_APPEARANCE_CALIBRATION.materialColourShare,
    ),
    emissiveIntensity: 1,
    roughness: 0.92,
    metalness: 0,
    side: THREE.DoubleSide,
  });
}

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
    material.userData.paint_parameters = variant.parameters;
    material.userData.coating_system = variant.coatingSystem;
    library.set(variant.id, material);
  });
  WALLPAPERS.forEach((product) => {
    const material = new THREE.MeshPhysicalMaterial({
        name: `WEB_${product.id}`,
        color: new THREE.Color(product.tint).multiplyScalar(
          WALLPAPER_APPEARANCE_CALIBRATION.directionalLightShare,
        ),
        roughness: product.roughness_mean,
        metalness: 0,
        emissive: new THREE.Color(product.tint).multiplyScalar(
          WALLPAPER_APPEARANCE_CALIBRATION.printedColourShare,
        ),
        emissiveIntensity: 1,
        side: THREE.DoubleSide,
        sheen: product.sheen ?? 0.04,
        sheenColor: new THREE.Color("#efe5d4"),
        sheenRoughness: 0.92,
      });
    material.userData.asset_id = product.id;
    library.set(product.id, material);
  });
  [...FLOORS, ...TILES].forEach((product) => {
    const isTile = product.id.startsWith("tile_");
    const material = new THREE.MeshStandardMaterial({
      name: `WEB_${product.id}`,
      color: isTile
        ? new THREE.Color(product.tint).multiplyScalar(
          FLOOR_TILE_APPEARANCE_CALIBRATION.directionalLightShare,
        )
        : product.tint,
      roughness: product.roughness_mean,
      metalness: 0,
      side: THREE.DoubleSide,
    });
    if (isTile) {
      // Floor tiles get the same tint anchor as wall tiles; otherwise a neutral
      // tile floor (e.g. light microcement) reads warm under the room's warm
      // sun/HDR/hemisphere light instead of its catalogue colour.
      material.emissive = new THREE.Color(product.tint).multiplyScalar(
        FLOOR_TILE_APPEARANCE_CALIBRATION.materialColourShare,
      );
      material.emissiveIntensity = 1;
    }
    const wallVariant = isTile
      ? new THREE.MeshStandardMaterial({
        name: `WEB_${product.id}_WALL_APPEARANCE`,
        color: new THREE.Color(product.tint).multiplyScalar(
          WALL_TILE_APPEARANCE_CALIBRATION.directionalLightShare,
        ),
        emissive: new THREE.Color(product.tint).multiplyScalar(
          WALL_TILE_APPEARANCE_CALIBRATION.materialColourShare,
        ),
        emissiveIntensity: 1,
        roughness: product.roughness_mean,
        metalness: 0,
        side: THREE.DoubleSide,
      })
      : null;
    material.userData.asset_id = product.id;
    if (wallVariant) {
      wallVariant.userData.asset_id = product.id;
      wallVariant.userData.wallAppearanceVariant = true;
      material.userData.wallVariant = wallVariant;
    }
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
        if (isTile) {
          material.color.set(product.runtime_color_multiplier ?? "#ffffff").multiplyScalar(
            FLOOR_TILE_APPEARANCE_CALIBRATION.directionalLightShare,
          );
          material.emissive.set(product.runtime_color_multiplier ?? "#ffffff").multiplyScalar(
            FLOOR_TILE_APPEARANCE_CALIBRATION.materialColourShare,
          );
          material.emissiveMap = map;
        } else {
          material.color.set(product.runtime_color_multiplier ?? "#ffffff");
        }
        if (wallVariant) {
          wallVariant.map = map;
          wallVariant.normalMap = normalMap;
          wallVariant.roughnessMap = roughnessMap;
          wallVariant.roughness = 1;
          wallVariant.envMapIntensity = 0.14;
          wallVariant.normalScale.set(product.normal_scale, product.normal_scale);
          wallVariant.color.set("#ffffff").multiplyScalar(
            WALL_TILE_APPEARANCE_CALIBRATION.directionalLightShare,
          );
          wallVariant.emissive.set("#ffffff").multiplyScalar(
            WALL_TILE_APPEARANCE_CALIBRATION.materialColourShare,
          );
          wallVariant.emissiveMap = map;
          wallVariant.needsUpdate = true;
        }
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
      // Do not tear down an in-flight load. It may still be referenced by the
      // current scheme and cannot be cancelled safely by TextureLoader.
      if (material.userData.pbrLoaded !== true) return;
      material.map?.dispose();
      material.normalMap?.dispose();
      material.roughnessMap?.dispose();
      material.map = null;
      material.normalMap = null;
      material.roughnessMap = null;
      if (wallVariant) {
        wallVariant.map = null;
        wallVariant.normalMap = null;
        wallVariant.roughnessMap = null;
        wallVariant.emissiveMap = null;
        wallVariant.color.set(product.tint).multiplyScalar(
          WALL_TILE_APPEARANCE_CALIBRATION.directionalLightShare,
        );
        wallVariant.emissive.set(product.tint).multiplyScalar(
          WALL_TILE_APPEARANCE_CALIBRATION.materialColourShare,
        );
        wallVariant.roughness = product.roughness_mean;
        wallVariant.needsUpdate = true;
      }
      if (isTile) {
        material.color.set(product.tint).multiplyScalar(
          FLOOR_TILE_APPEARANCE_CALIBRATION.directionalLightShare,
        );
        material.emissive.set(product.tint).multiplyScalar(
          FLOOR_TILE_APPEARANCE_CALIBRATION.materialColourShare,
        );
        material.emissiveMap = null;
      } else {
        material.color.set(product.tint);
      }
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
  const ceilingMaterial = makeCeilingFinishMaterial("WEB_ceiling_dry_finish");
  const panelMaterial = new THREE.MeshStandardMaterial({ color: "#c8cbc6", roughness: 0.68 });
  const shadowMaterial = new THREE.MeshStandardMaterial({ color: "#171918", roughness: 0.98 });
  const timberMaterial = new THREE.MeshStandardMaterial({ color: "#9a6f43", roughness: 0.72 });
  const concreteMaterial = new THREE.MeshStandardMaterial({ color: "#8d8b84", roughness: 0.88 });
  const trackMaterial = new THREE.MeshStandardMaterial({ color: "#202322", roughness: 0.82 });
  const coveLightMaterial = new THREE.MeshStandardMaterial({
    color: "#ffd7a0",
    emissive: "#ff9c45",
    emissiveIntensity: 2.2,
    roughness: 0.58,
  });

  type CeilingBoxSpec = {
    name: string;
    size: [number, number, number];
    position: [number, number, number];
    material: THREE.Material;
    presetId: string;
    roomId: string;
  };
  const pendingBoxes = new WeakMap<THREE.Group, CeilingBoxSpec[]>();

  const addBox = (
    group: THREE.Group,
    name: string,
    size: [number, number, number],
    position: [number, number, number],
    material: THREE.Material,
    presetId: string,
    roomId: string,
  ) => {
    const specs = pendingBoxes.get(group) ?? [];
    specs.push({ name, size, position, material, presetId, roomId });
    pendingBoxes.set(group, specs);
  };

  const flushInstancedBoxes = (group: THREE.Group) => {
    const specs = pendingBoxes.get(group) ?? [];
    const batches = new Map<string, CeilingBoxSpec[]>();
    specs.forEach((spec) => {
      // Room-level batches preserve the existing visibility contract while
      // collapsing tens or hundreds of identical boxes into one draw call.
      const key = `${spec.roomId}:${spec.material.uuid}`;
      const batch = batches.get(key) ?? [];
      batch.push(spec);
      batches.set(key, batch);
    });

    batches.forEach((batch) => {
      const first = batch[0];
      const mesh = new THREE.InstancedMesh(
        new THREE.BoxGeometry(1, 1, 1),
        first.material,
        batch.length,
      );
      mesh.name = `${first.roomId}_${first.presetId}_${first.material.name || "material"}_batch`;
      mesh.castShadow = true;
      mesh.receiveShadow = true;
      mesh.userData.preset_id = first.presetId;
      mesh.userData.room_id = first.roomId;
      const matrix = new THREE.Matrix4();
      const quaternion = new THREE.Quaternion();
      batch.forEach((spec, index) => {
        const position = blenderPoint(spec.position);
        // Blender Z-up boxes were previously constructed as X/Z/Y in Three.
        const scale = new THREE.Vector3(spec.size[0], spec.size[2], spec.size[1]);
        matrix.compose(position, quaternion, scale);
        mesh.setMatrixAt(index, matrix);
      });
      mesh.instanceMatrix.setUsage(THREE.StaticDrawUsage);
      mesh.instanceMatrix.needsUpdate = true;
      mesh.computeBoundingBox();
      mesh.computeBoundingSphere();
      group.add(mesh);
    });
    pendingBoxes.delete(group);
  };

  CEILINGS.filter((product) => product.preset !== "flat").forEach((product) => {
    const group = new THREE.Group();
    group.name = `CEILING_PRESET_${product.id}`;
    group.userData.preset_id = product.id;
    group.visible = false;
    ROOM_CAMERA_TRACKS
      .filter((track) => track.surfaceTargets.ceiling !== null)
      .filter((track) => product.preset === "modular_panel" ? WET_ROOM_IDS.has(track.roomId) : !WET_ROOM_IDS.has(track.roomId))
      .forEach(({ roomId, roomRect: [x1, y1, x2, y2] }) => {
        const width = x2 - x1;
        const depth = y2 - y1;
        const centerX = (x1 + x2) / 2;
        const centerY = (y1 + y2) / 2;
        const height = product.drop_height_mm / 1000;
        const centerZ = 3.07 - height / 2;
        if (product.preset === "perimeter_step" || product.preset === "perimeter_cove") {
          const band = (product.perimeter_band_mm ?? 300) / 1000;
          addBox(group, `${roomId}_${product.id}_left`, [band, depth, height], [x1 + band / 2, centerY, centerZ], ceilingMaterial, product.id, roomId);
          addBox(group, `${roomId}_${product.id}_right`, [band, depth, height], [x2 - band / 2, centerY, centerZ], ceilingMaterial, product.id, roomId);
          addBox(group, `${roomId}_${product.id}_front`, [Math.max(width - band * 2, 0.2), band, height], [centerX, y1 + band / 2, centerZ], ceilingMaterial, product.id, roomId);
          addBox(group, `${roomId}_${product.id}_back`, [Math.max(width - band * 2, 0.2), band, height], [centerX, y2 - band / 2, centerZ], ceilingMaterial, product.id, roomId);
          if (product.preset === "perimeter_cove") {
            const cove = (product.cove_width_mm ?? 90) / 1000;
            const lightZ = 3.07 - height + 0.012;
            addBox(group, `${roomId}_${product.id}_light_left`, [cove, Math.max(depth - band * 2, 0.2), 0.018], [x1 + band + cove / 2, centerY, lightZ], coveLightMaterial, product.id, roomId);
            addBox(group, `${roomId}_${product.id}_light_right`, [cove, Math.max(depth - band * 2, 0.2), 0.018], [x2 - band - cove / 2, centerY, lightZ], coveLightMaterial, product.id, roomId);
          }
        } else if (product.preset === "floating_shadow_gap") {
          const gap = (product.shadow_gap_mm ?? 80) / 1000;
          addBox(group, `${roomId}_${product.id}_shadow`, [Math.max(width - gap * 2, 0.2), Math.max(depth - gap * 2, 0.2), 0.025], [centerX, centerY, 3.045], shadowMaterial, product.id, roomId);
          addBox(group, `${roomId}_${product.id}_plate`, [Math.max(width - gap * 4, 0.2), Math.max(depth - gap * 4, 0.2), height], [centerX, centerY, centerZ], ceilingMaterial, product.id, roomId);
        } else if (product.preset === "timber_slatted") {
          const slatWidth = (product.slat_width_mm ?? 38) / 1000;
          const slatGap = (product.slat_gap_mm ?? 22) / 1000;
          const pitch = slatWidth + slatGap;
          const count = Math.max(1, Math.floor((width - 0.08) / pitch));
          const usedWidth = count * pitch - slatGap;
          const startX = centerX - usedWidth / 2 + slatWidth / 2;
          addBox(group, `${roomId}_${product.id}_shadow_backing`, [Math.max(width - 0.08, 0.2), Math.max(depth - 0.08, 0.2), 0.02], [centerX, centerY, 3.035], shadowMaterial, product.id, roomId);
          for (let index = 0; index < count; index += 1) {
            addBox(group, `${roomId}_${product.id}_slat_${index}`, [slatWidth, Math.max(depth - 0.08, 0.2), 0.045], [startX + index * pitch, centerY, 3.07 - height + 0.0225], timberMaterial, product.id, roomId);
          }
        } else if (product.preset === "shallow_coffer_grid") {
          const beamWidth = (product.beam_width_mm ?? 90) / 1000;
          const module = (product.grid_module_mm ?? 900) / 1000;
          addBox(group, `${roomId}_${product.id}_base`, [Math.max(width - 0.04, 0.2), Math.max(depth - 0.04, 0.2), 0.035], [centerX, centerY, 3.0525], ceilingMaterial, product.id, roomId);
          const beamZ = 3.07 - height / 2;
          for (let x = x1 + module; x < x2 - module * 0.35; x += module) {
            addBox(group, `${roomId}_${product.id}_beam_x_${x.toFixed(2)}`, [beamWidth, Math.max(depth - 0.08, 0.2), height], [x, centerY, beamZ], ceilingMaterial, product.id, roomId);
          }
          for (let y = y1 + module; y < y2 - module * 0.35; y += module) {
            addBox(group, `${roomId}_${product.id}_beam_y_${y.toFixed(2)}`, [Math.max(width - 0.08, 0.2), beamWidth, height], [centerX, y, beamZ], ceilingMaterial, product.id, roomId);
          }
        } else if (product.preset === "exposed_concrete_track") {
          addBox(group, `${roomId}_${product.id}_slab`, [Math.max(width - 0.04, 0.2), Math.max(depth - 0.04, 0.2), 0.035], [centerX, centerY, 3.0525], concreteMaterial, product.id, roomId);
          const trackWidth = (product.track_width_mm ?? 28) / 1000;
          const offset = Math.min((product.track_offset_mm ?? 420) / 1000, width * 0.28);
          [-offset, offset].forEach((trackOffset, index) => {
            addBox(group, `${roomId}_${product.id}_track_${index}`, [trackWidth, Math.max(depth - 0.12, 0.2), 0.028], [centerX + trackOffset, centerY, 3.021], trackMaterial, product.id, roomId);
          });
        } else if (product.preset === "curved_cove") {
          const bandTotal = Math.min((product.perimeter_band_mm ?? 420) / 1000, width * 0.22, depth * 0.22);
          const steps = 5;
          const stepBand = bandTotal / steps;
          for (let step = 0; step < steps; step += 1) {
            const inset = step * stepBand;
            const ringWidth = stepBand + 0.012;
            const progress = step / Math.max(1, steps - 1);
            const underside = 3.07 - height * (1 - progress * progress);
            addBox(group, `${roomId}_${product.id}_curve_left_${step}`, [ringWidth, Math.max(depth - inset * 2, 0.2), 0.04], [x1 + inset + ringWidth / 2, centerY, underside], ceilingMaterial, product.id, roomId);
            addBox(group, `${roomId}_${product.id}_curve_right_${step}`, [ringWidth, Math.max(depth - inset * 2, 0.2), 0.04], [x2 - inset - ringWidth / 2, centerY, underside], ceilingMaterial, product.id, roomId);
            addBox(group, `${roomId}_${product.id}_curve_front_${step}`, [Math.max(width - (inset + ringWidth) * 2, 0.2), ringWidth, 0.04], [centerX, y1 + inset + ringWidth / 2, underside], ceilingMaterial, product.id, roomId);
            addBox(group, `${roomId}_${product.id}_curve_back_${step}`, [Math.max(width - (inset + ringWidth) * 2, 0.2), ringWidth, 0.04], [centerX, y2 - inset - ringWidth / 2, underside], ceilingMaterial, product.id, roomId);
          }
          const cove = (product.cove_width_mm ?? 100) / 1000;
          addBox(group, `${roomId}_${product.id}_cove_light`, [Math.max(width - bandTotal * 2, 0.2), Math.max(depth - bandTotal * 2, 0.2), 0.012], [centerX, centerY, 3.07 - height + cove * 0.3], coveLightMaterial, product.id, roomId);
        } else if (product.preset === "modular_panel") {
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
    flushInstancedBoxes(group);
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
  const [paintAssetId, setPaintAssetId] = useState("paint_warm_white_01");
  const [paintTone, setPaintTone] = useState<PaintToneId>("light");
  const [paintSaturation, setPaintSaturation] = useState(1);
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
        api.applyAsset([target.id], asset_id, assignment.parameters ?? null, false);
      }
    }
    api.reconcileAssets();

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
      if (command.args.design_run_id) {
        const scheme = await fetchCurrentScheme(command.args.design_run_id);
        if (scheme.scheme_id !== currentSchemeRef.current?.scheme_id) {
          applyScheme(scheme);
        }
      }
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

    const poll = () => {
      fetchCurrentScheme(designRunIdFromLocation())
        .then((data: Scheme) => {
          if (data.scheme_id === currentSchemeRef.current?.scheme_id) return;
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
    const asset = PAINT_VARIANT_BY_ID.get(selected.assetId);
    if (!asset) return;
    setPaintAssetId(asset.id);
    const assignment = currentScheme?.assignments.find((item) => item.target.id === selected.targetId);
    const parameters = assignment?.parameters ?? asset.parameters;
    if (parameters) {
      setPaintTone(parameters.lightness);
      setPaintSaturation(parameters.saturation);
      setPaintFinish(parameters.finish);
    }
  }, [selected?.assetId, selected?.targetId, currentScheme]);

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
    // Render-on-demand: the GTAO + VSM chain is the costliest work in the app.
    // Run it only when the camera moved, a surface changed, or a texture landed;
    // an idle frame (e.g. a hidden chat iframe) then costs ~0 instead of two
    // fullscreen passes at every RAF.
    let needsRender = true;
    let lastFrameKey = "";
    const markDirty = () => { needsRender = true; };
    const frameKey = () => `${camera.position.x.toFixed(4)},${camera.position.y.toFixed(4)},${camera.position.z.toFixed(4)},${controls.target.x.toFixed(4)},${controls.target.y.toFixed(4)},${controls.target.z.toFixed(4)},${camera.fov.toFixed(3)}`;
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
    const flatCeilingMaterial = makeCeilingFinishMaterial("WEB_ceiling_flat_finish");
    scene.add(ceilingPresetRoot);

    const camera = new THREE.PerspectiveCamera(45, 1, 0.025, 80);
    // Visual-observation evidence must remain readable after background renders.
    // Keep the established capture contract; interaction savings come from the
    // lower-cost shadow/AO path and render-on-demand below.
    const renderer = new THREE.WebGLRenderer({ antialias: true, alpha: false, preserveDrawingBuffer: true });
    renderer.outputColorSpace = THREE.SRGBColorSpace;
    renderer.toneMapping = THREE.ACESFilmicToneMapping;
    // The old hero-room rig stacked a bright HDR, strong sun and high
    // exposure. In the v4 full-house model that clipped pale materials.
    renderer.toneMappingExposure = 0.86;
    renderer.shadowMap.enabled = true;
    renderer.shadowMap.type = THREE.PCFSoftShadowMap;
    // Camera motion is the hot path. At 1.5 DPR a 1280x720 viewport becomes a
    // 1920x1080 multi-pass render; 1.25 is still sharp while cutting fragments
    // by roughly 31% from the previous cap.
    const renderPixelRatio = Math.min(window.devicePixelRatio, MAX_RENDER_PIXEL_RATIO);
    renderer.setPixelRatio(renderPixelRatio);
    // The sun and apartment geometry are static while a camera tour plays.
    // Rebuild the shadow map only when the room, ceiling or furniture changes.
    renderer.shadowMap.autoUpdate = false;
    renderer.shadowMap.needsUpdate = true;
    renderer.domElement.className = "room-canvas";
    renderer.domElement.setAttribute("aria-label", "房间级可交互空间体验");
    // With render-on-demand, an idle tab may have skipped every frame when the
    // context is lost; redraw as soon as the driver hands it back.
    renderer.domElement.addEventListener("webglcontextrestored", markDirty);
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
    gtaoPass.updateGtaoMaterial({ radius: 0.028, distanceExponent: 1.7, thickness: 0.42, distanceFallOff: 0.94, samples: 8 });
    gtaoPass.updatePdMaterial({ radius: 5, rings: 2, samples: 6, lumaPhi: 8, depthPhi: 2, normalPhi: 3 });
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
        markDirty();
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
    sun.shadow.mapSize.set(1024, 1024);
    sun.shadow.bias = -0.00012;
    sun.shadow.normalBias = 0.018;
    sun.shadow.radius = 3;
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
      renderer.shadowMap.needsUpdate = true;
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
      gtaoPass.setSize(
        Math.max(1, Math.round(width * renderPixelRatio * GTAO_RESOLUTION_SCALE)),
        Math.max(1, Math.round(height * renderPixelRatio * GTAO_RESOLUTION_SCALE)),
      );
      markDirty();
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
      renderer.shadowMap.needsUpdate = true;
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
      markDirty();
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

    // Evidence renders through a lightweight RenderPass + OutputPass chain into
    // a dedicated offscreen target, then reads it back with readRenderTargetPixels.
    // Two properties make this the correct evidence path:
    //  - It is decoupled from the live canvas, so a hidden/backgrounded tab can
    //    never hand back a stale frame (the "Scheme 是瓷砖但截图像木地板" symptom).
    //  - OutputPass applies the same ACES tone mapping and sRGB output as the
    //    interactive viewer. A bare renderer.render() into a render target would
    //    disable material tone mapping and force linear output (WebGLPrograms
    //    gates toneMapping/outputColorSpace on currentRenderTarget === null), so
    //    the evidence must go through OutputPass. Its targets stay NoColorSpace
    //    (linear) so the shader's own sRGBTransferOETF is not double-encoded.
    //    GTAO is deliberately skipped — it was the dominant per-view GPU cost
    //    (~12s on software WebGL) and the reason observe_home_harmony timed out.
    const evidenceRenderTarget = new THREE.WebGLRenderTarget(
      EVIDENCE_WIDTH,
      EVIDENCE_HEIGHT,
      // HalfFloat matches the interactive composer's HDR intermediates, so bright
      // highlights are not clamped before OutputPass tone maps them.
      { type: THREE.HalfFloatType },
    );
    const evidenceComposer = new EffectComposer(renderer, evidenceRenderTarget);
    evidenceComposer.renderToScreen = false;
    evidenceComposer.addPass(new RenderPass(scene, camera));
    evidenceComposer.addPass(new OutputPass());

    const visibilityRenderTarget = new THREE.WebGLRenderTarget(
      VISIBILITY_WIDTH,
      VISIBILITY_HEIGHT,
      {
        type: THREE.UnsignedByteType,
        minFilter: THREE.NearestFilter,
        magFilter: THREE.NearestFilter,
        depthBuffer: true,
        stencilBuffer: false,
      },
    );

    type RenderedEvidenceFrame = Pick<VisualImage, "imageDataUrl" | "quality">;

    const renderEvidenceFrame = (): RenderedEvidenceFrame => {
      evidenceComposer.render();
      const { readBuffer } = evidenceComposer;
      const { width, height } = readBuffer;
      // HalfFloat readback: the buffer holds 16-bit half-float bit patterns, so
      // decode each channel back to [0,1] before writing bytes.
      const samples = new Uint16Array(width * height * 4);
      renderer.readRenderTargetPixels(readBuffer, 0, 0, width, height, samples);
      const captureCanvas = document.createElement("canvas");
      captureCanvas.width = width;
      captureCanvas.height = height;
      const context = captureCanvas.getContext("2d");
      if (!context) throw new Error("浏览器不支持用于视觉观察的 2D Canvas。");
      const image = context.createImageData(width, height);
      let luminanceSum = 0;
      let luminanceSquaredSum = 0;
      let darkPixels = 0;
      // readRenderTargetPixels returns rows bottom-up; flip so the JPEG matches
      // the camera's upright view.
      const clampByte = (value: number) => Math.max(0, Math.min(255, Math.round(value * 255)));
      for (let row = 0; row < height; row += 1) {
        const src = (height - 1 - row) * width * 4;
        const dst = row * width * 4;
        for (let offset = 0; offset < width * 4; offset += 4) {
          const red = clampByte(THREE.DataUtils.fromHalfFloat(samples[src + offset]));
          const green = clampByte(THREE.DataUtils.fromHalfFloat(samples[src + offset + 1]));
          const blue = clampByte(THREE.DataUtils.fromHalfFloat(samples[src + offset + 2]));
          image.data[dst + offset] = red;
          image.data[dst + offset + 1] = green;
          image.data[dst + offset + 2] = blue;
          image.data[dst + offset + 3] = 255;
          const luminance = (0.2126 * red + 0.7152 * green + 0.0722 * blue) / 255;
          luminanceSum += luminance;
          luminanceSquaredSum += luminance * luminance;
          if (luminance < 0.02) darkPixels += 1;
        }
      }
      context.putImageData(image, 0, 0);
      const pixelCount = width * height;
      const meanLuminance = luminanceSum / pixelCount;
      const luminanceStdDev = Math.sqrt(Math.max(0, luminanceSquaredSum / pixelCount - meanLuminance ** 2));
      const darkPixelRatio = darkPixels / pixelCount;
      const reasons: string[] = [];
      if (meanLuminance < 0.015 || darkPixelRatio > 0.995) reasons.push("FRAME_EFFECTIVELY_BLACK");
      if (luminanceStdDev < 0.0025) reasons.push("FRAME_HAS_NO_SPATIAL_INFORMATION");
      return {
        imageDataUrl: captureCanvas.toDataURL("image/jpeg", 0.9),
        quality: {
          valid: reasons.length === 0,
          meanLuminance: Number(meanLuminance.toFixed(5)),
          luminanceStdDev: Number(luminanceStdDev.toFixed(5)),
          darkPixelRatio: Number(darkPixelRatio.toFixed(5)),
          reasons,
        },
      };
    };

    const targetIdForVisibilityMesh = (mesh: THREE.Mesh) => {
      const direct = mesh.userData.wall_face_id ?? mesh.userData.surface_id;
      if (typeof direct === "string") return direct;
      if (typeof mesh.userData.room_id === "string" && typeof mesh.userData.preset_id === "string") {
        return `surface_real4_ceiling_${mesh.userData.room_id}`;
      }
      return null;
    };

    const renderTargetVisibility = (targetIds: string[]): {
      targets: VisualImage["targetVisibility"];
      maskQuality: VisualImage["maskQuality"];
    } => {
      const uniqueTargetIds = [...new Set(targetIds)];
      if (uniqueTargetIds.length === 0) {
        return { targets: [], maskQuality: { occluderPixelRatio: 0, backgroundPixelRatio: 1 } };
      }
      const colorByTarget = new Map<string, [number, number, number]>();
      const targetByColor = new Map<number, string>();
      uniqueTargetIds.forEach((targetId, index) => {
        const code = index + 1;
        const color: [number, number, number] = [
          (code >> 16) & 255,
          (code >> 8) & 255,
          code & 255,
        ];
        colorByTarget.set(targetId, color);
        targetByColor.set((color[0] << 16) | (color[1] << 8) | color[2], targetId);
      });
      const black = new THREE.MeshBasicMaterial({ color: 0x000000, toneMapped: false, side: THREE.DoubleSide });
      const idMaterials = new Map<string, THREE.MeshBasicMaterial>();
      colorByTarget.forEach(([red, green, blue], targetId) => {
        const material = new THREE.MeshBasicMaterial({ toneMapped: false, side: THREE.DoubleSide });
        material.color.setRGB(red / 255, green / 255, blue / 255, THREE.LinearSRGBColorSpace);
        idMaterials.set(targetId, material);
      });
      const saved: Array<{ mesh: THREE.Mesh; material: THREE.Material | THREE.Material[]; visible: boolean }> = [];
      const previousBackground = scene.background;
      const previousTarget = renderer.getRenderTarget();
      scene.traverse((object) => {
        if (!(object instanceof THREE.Mesh) || !object.visible) return;
        saved.push({ mesh: object, material: object.material, visible: object.visible });
        const isTransparentOpening = object.name.endsWith("_glass")
          || (object.material instanceof THREE.MeshPhysicalMaterial && object.material.transmission > 0.05);
        if (isTransparentOpening) {
          object.visible = false;
          return;
        }
        const targetId = targetIdForVisibilityMesh(object);
        object.material = targetId && idMaterials.has(targetId) ? idMaterials.get(targetId)! : black;
      });
      const samples = new Uint8Array(VISIBILITY_WIDTH * VISIBILITY_HEIGHT * 4);
      try {
        // Magenta is reserved for open background. Opaque non-target geometry
        // stays black, which lets hero selection penalize a door jamb or wall
        // return that blocks the frame without pretending it is empty space.
        scene.background = new THREE.Color(0xff00ff);
        renderer.setRenderTarget(visibilityRenderTarget);
        renderer.clear(true, true, true);
        renderer.render(scene, camera);
        renderer.readRenderTargetPixels(
          visibilityRenderTarget,
          0,
          0,
          VISIBILITY_WIDTH,
          VISIBILITY_HEIGHT,
          samples,
        );
      } finally {
        renderer.setRenderTarget(previousTarget);
        scene.background = previousBackground;
        saved.forEach(({ mesh, material, visible }) => {
          mesh.material = material;
          mesh.visible = visible;
        });
        black.dispose();
        idMaterials.forEach((material) => material.dispose());
      }
      const stats = new Map<string, { count: number; minX: number; minY: number; maxX: number; maxY: number }>();
      uniqueTargetIds.forEach((targetId) => stats.set(targetId, {
        count: 0,
        minX: VISIBILITY_WIDTH,
        minY: VISIBILITY_HEIGHT,
        maxX: -1,
        maxY: -1,
      }));
      let occluderPixels = 0;
      let backgroundPixels = 0;
      for (let pixel = 0; pixel < VISIBILITY_WIDTH * VISIBILITY_HEIGHT; pixel += 1) {
        const offset = pixel * 4;
        const key = (samples[offset] << 16) | (samples[offset + 1] << 8) | samples[offset + 2];
        if (key === 0) occluderPixels += 1;
        if (key === 0xff00ff) backgroundPixels += 1;
        const targetId = targetByColor.get(key);
        if (!targetId) continue;
        const x = pixel % VISIBILITY_WIDTH;
        const y = VISIBILITY_HEIGHT - 1 - Math.floor(pixel / VISIBILITY_WIDTH);
        const item = stats.get(targetId)!;
        item.count += 1;
        item.minX = Math.min(item.minX, x);
        item.minY = Math.min(item.minY, y);
        item.maxX = Math.max(item.maxX, x);
        item.maxY = Math.max(item.maxY, y);
      }
      const targets = uniqueTargetIds.map((targetId) => {
        const item = stats.get(targetId)!;
        const boundingBox = item.count > 0 ? {
          x: item.minX,
          y: item.minY,
          width: item.maxX - item.minX + 1,
          height: item.maxY - item.minY + 1,
        } : null;
        const pixelRatio = item.count / (VISIBILITY_WIDTH * VISIBILITY_HEIGHT);
        return {
          targetId,
          pixelCount: item.count,
          pixelRatio: Number(pixelRatio.toFixed(6)),
          boundingBox,
          readable: Boolean(
            boundingBox
            && pixelRatio >= MIN_TARGET_PIXEL_RATIO
            && Math.min(boundingBox.width, boundingBox.height) >= MIN_TARGET_BOUNDING_DIMENSION
          ),
        };
      });
      const maskPixelCount = VISIBILITY_WIDTH * VISIBILITY_HEIGHT;
      return {
        targets,
        maskQuality: {
          occluderPixelRatio: Number((occluderPixels / maskPixelCount).toFixed(6)),
          backgroundPixelRatio: Number((backgroundPixels / maskPixelCount).toFixed(6)),
        },
      };
    };

    const waitForActivePbr = async () => {
      const pending = new Set<Promise<unknown>>();
      targetIndex.forEach((meshes) => meshes.forEach((mesh) => {
        const ensured = (mesh.material as THREE.Material & { userData: { ensurePbr?: () => unknown } })
          .userData.ensurePbr?.();
        if (ensured instanceof Promise) pending.add(ensured);
      }));
      await Promise.all(pending);
    };

    const captureInspectionViews = async (
      roomId: string,
      views: RoomInspectionView[],
      scopeToRoom = false,
      resolution: [number, number] = [EVIDENCE_WIDTH, EVIDENCE_HEIGHT],
      visibilityTargetIds: string[] = [],
    ): Promise<VisualImage[]> => {
      const previousTrack = activeTrackValue;
      const previousPreparedTour = preparedTour;
      const previousDuration = tourDurationMsValue;
      const previousProgress = tourProgressValue;
      const wasPlaying = tourPlayingValue;
      const previousDetailsVisible = detailsVisibleValue;
      const previousAspect = camera.aspect;

      setTourPlayingValue(false);
      activeTrackValue = getRoomCameraTrack(roomId);
      tourDurationMsValue = activeTrackValue.durationMs;
      preparedTour = prepareTrack(activeTrackValue);
      detailsVisibleValue = false;
      updateLightingForTrack(activeTrackValue);
      updateCeilingVisibility();
      applyPresentation();

      // Evidence renders into its own target; home-harmony heroes only land in
      // a 320x180 contact sheet, so rendering them at full HD would waste the
      // largest share of the observe_home_harmony budget.
      const [viewWidth, viewHeight] = resolution;
      // The composer's _pixelRatio is inherited from the renderer (1.25), so
      // setSize would render viewWidth*pixelRatio pixels. Resize the two buffer
      // targets directly to get the exact intended evidence dimensions.
      evidenceComposer.renderTarget1.setSize(viewWidth, viewHeight);
      evidenceComposer.renderTarget2.setSize(viewWidth, viewHeight);
      camera.aspect = viewWidth / viewHeight;
      camera.updateProjectionMatrix();

      let hiddenFloors = new Map<THREE.Mesh, boolean>();
      if (scopeToRoom) {
        // Keep only the requested room's floor plane visible so a small room's
        // own tile floor is not swamped by the adjacent hall's wood floor
        // (previously made tile read as wood even on a fresh frame).
        const keptFloorId = getRoomCameraTrack(roomId).surfaceTargets.floor;
        targetIndex.forEach((meshes, surfaceId) => {
          if (!surfaceId.startsWith("surface_real4_floor_") || surfaceId === keptFloorId) return;
          meshes.forEach((mesh) => {
            hiddenFloors.set(mesh, mesh.visible);
            mesh.visible = false;
          });
        });
      }

      try {
        await waitForActivePbr();
        const captures: VisualImage[] = [];
        for (const view of views) {
          camera.position.copy(blenderPoint(view.cameraPose.position));
          controls.target.copy(blenderPoint(view.cameraPose.target));
          camera.fov = view.cameraPose.fov;
          camera.updateProjectionMatrix();
          controls.update();
          const frame = renderEvidenceFrame();
          const visibility = renderTargetVisibility(visibilityTargetIds);
          captures.push({
            viewId: view.id,
            label: view.label,
            purpose: view.purpose,
            focusTargetIds: view.focusTargetIds,
            imageDataUrl: frame.imageDataUrl,
            quality: frame.quality,
            targetVisibility: visibility.targets,
            maskQuality: visibility.maskQuality,
          });
        }
        return captures;
      } finally {
        camera.aspect = previousAspect;
        camera.updateProjectionMatrix();
        activeTrackValue = previousTrack;
        preparedTour = previousPreparedTour;
        tourDurationMsValue = previousDuration;
        detailsVisibleValue = previousDetailsVisible;
        updateLightingForTrack(previousTrack);
        updateCeilingVisibility();
        applyPresentation();
        hiddenFloors.forEach((visible, mesh) => { mesh.visible = visible; });
        setTourProgressValue(previousProgress);
        if (wasPlaying) setTourPlayingValue(true);
      }
    };

    const captureRoomObservation = async (
      roomId: string,
      focusTargetIds: string[] = [],
    ): Promise<RoomObservationResult> => {
      const plan = createRoomObservationPlan(roomId, focusTargetIds);
      // Plan views stay true whole-scene captures (a small room's track
      // intentionally reads e.g. "玄关地面和公共区材料的衔接", which must not be
      // broken by hiding neighbouring floors).
      const views = await captureInspectionViews(
        plan.roomId,
        plan.views,
        false,
        [EVIDENCE_WIDTH, EVIDENCE_HEIGHT],
        plan.expectedTargetIds,
      );
      // A small room's own floor can still be visually swamped by the adjacent
      // hall's wood in those real-scene frames. Append ONE clearly-labelled
      // scoped supplement showing only this room's floor, so the Scheme's floor
      // material is unambiguous. purpose="floor_isolated" marks it as a scoped
      // supplement, NOT a true whole-scene capture.
      const track = getRoomCameraTrack(plan.roomId);
      const floorKeyframe = track.keyframes.find(
        (keyframe) => keyframe.progress === track.focusProgress.floor,
      ) ?? track.keyframes[0];
      const [floorIsolated] = await captureInspectionViews(plan.roomId, [{
        id: `floor_isolated_${Math.round(floorKeyframe.progress * 1000)}`,
        purpose: "floor_isolated",
        sourceProgress: floorKeyframe.progress,
        label: "地面隔离 · 仅本房间地面",
        description: floorKeyframe.description,
        focusTargetIds: [track.surfaceTargets.floor],
        cameraPose: {
          position: [...floorKeyframe.position],
          target: [...floorKeyframe.target],
          fov: floorKeyframe.fov,
        },
      }], true, [EVIDENCE_WIDTH, EVIDENCE_HEIGHT], [track.surfaceTargets.floor]);
      const allViews = [...views, floorIsolated];
      const verifiedCoverage = Object.fromEntries(plan.expectedTargetIds.map((targetId) => [
        targetId,
        allViews
          .filter((view) => view.quality.valid)
          .filter((view) => view.targetVisibility.some((item) => item.targetId === targetId && item.readable))
          .map((view) => view.viewId),
      ]));
      const uncoveredTargetIds = plan.expectedTargetIds.filter(
        (targetId) => verifiedCoverage[targetId].length === 0,
      );
      const invalidViewIds = allViews.filter((view) => !view.quality.valid).map((view) => view.viewId);
      const scheme = currentSchemeRef.current;
      return {
        tool: "observe_room",
        status: uncoveredTargetIds.length === 0 && invalidViewIds.length === 0 ? "ready" : "incomplete_observation",
        evidenceLevel: "pixel_verified_coverage",
        houseId: plan.houseId,
        scheme: { schemeId: scheme?.scheme_id ?? null, title: scheme?.title ?? null },
        room: { id: plan.roomId, label: plan.roomLabel },
        views: allViews,
        plannedCoverage: plan.plannedCoverage,
        verifiedCoverage,
        uncoveredTargetIds,
        invalidViewIds,
        topologyAnomalyTargetIds: plan.topologyAnomalyTargetIds,
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

    const captureTransitionPair = async (transition: HomeHarmonyTransition) => {
      const transitionTargets = [
        getRoomCameraTrack(transition.fromRoomId).surfaceTargets.floor,
        getRoomCameraTrack(transition.toRoomId).surfaceTargets.floor,
      ].filter((targetId): targetId is string => Boolean(targetId));
      const [from] = await captureInspectionViews(transition.fromRoomId, [
        transition.fromView,
      ], false, [960, 540], transitionTargets);
      const [to] = await captureInspectionViews(transition.toRoomId, [
        transition.toView,
      ], false, [960, 540], transitionTargets);
      const seesBothSides = (image: VisualImage) => transitionTargets.every((targetId) => (
        image.targetVisibility.some((item) => item.targetId === targetId && item.readable)
      ));
      const fromReadable = from.quality.valid && seesBothSides(from);
      const toReadable = to.quality.valid && seesBothSides(to);
      return {
        id: transition.id,
        openingId: transition.openingId,
        rationale: transition.rationale,
        openingCenter: transition.openingCenter,
        status: fromReadable && toReadable ? "ready" : "incomplete_observation",
        from,
        to,
      };
    };

    const captureHomeHarmony = async (): Promise<HomeHarmonyObservationResult> => {
      const captureStartedAt = performance.now();
      const plan = createHomeHarmonyPlan();
      const scheme = currentSchemeRef.current;
      const heroImages: Array<{ roomLabel: string; imageDataUrl: string }> = [];
      const incompleteRooms: HomeHarmonyObservationResult["incompleteRooms"] = [];
      const invalidHeroRoomIds: string[] = [];
      const roomHeroDiagnostics: HomeHarmonyObservationResult["roomHeroDiagnostics"] = [];
      let heroCandidateCount = 0;
      for (const hero of plan.roomHeroViews) {
        const track = getRoomCameraTrack(hero.roomId);
        const expected = [track.surfaceTargets.floor, ...track.surfaceTargets.walls]
          .filter((targetId): targetId is string => Boolean(targetId));
        const candidates = await captureInspectionViews(
          hero.roomId,
          hero.candidateViews,
          false,
          [HOME_HERO_WIDTH, HOME_HERO_HEIGHT],
          expected,
        );
        heroCandidateCount += candidates.length;
        const scoreCandidate = (candidate: VisualImage) => {
          const readable = candidate.targetVisibility.filter((item) => item.readable);
          const readableIds = new Set(readable.map((item) => item.targetId));
          const floorId = track.surfaceTargets.floor;
          const floorScore = floorId && readableIds.has(floorId) ? 320 : 0;
          const readableWallCount = track.surfaceTargets.walls
            .filter((targetId) => readableIds.has(targetId)).length;
          const wallScore = track.surfaceTargets.walls.length === 0
            ? 180
            : Math.min(2, readableWallCount) * 180;
          const dominantRatio = Math.max(0, ...readable.map((item) => item.pixelRatio));
          const dominancePenalty = Math.max(0, dominantRatio - 0.58) * 900;
          const occluderPenalty = Math.max(0, candidate.maskQuality.occluderPixelRatio - 0.18) * 700;
          const qualityScore = candidate.quality.valid
            ? 1000 + Math.min(0.25, candidate.quality.luminanceStdDev) * 200
            : -1000;
          return qualityScore + floorScore + wallScore + readable.length * 35
            - dominancePenalty - occluderPenalty;
        };
        const candidatePassesHeroGate = (candidate: VisualImage) => {
          const readableIds = new Set(
            candidate.targetVisibility.filter((item) => item.readable).map((item) => item.targetId),
          );
          const floorId = track.surfaceTargets.floor;
          return candidate.quality.valid
            && Boolean(floorId && readableIds.has(floorId))
            && (track.surfaceTargets.walls.length === 0
              || track.surfaceTargets.walls.some((targetId) => readableIds.has(targetId)))
            // Tiny service rooms legitimately contain more door-frame/wall-core
            // context than bedrooms. Above 72% the actual finish evidence is no
            // longer representative and the hero must fail closed.
            && candidate.maskQuality.occluderPixelRatio <= 0.72;
        };
        const image = [...candidates].sort((first, second) => (
          Number(candidatePassesHeroGate(second)) - Number(candidatePassesHeroGate(first))
          || scoreCandidate(second) - scoreCandidate(first)
        ))[0];
        const selectedScore = scoreCandidate(image);
        heroImages.push({ roomLabel: hero.roomLabel, imageDataUrl: image.imageDataUrl });
        roomHeroDiagnostics.push({
          roomId: hero.roomId,
          selectedViewId: image.viewId,
          score: Number(selectedScore.toFixed(2)),
          quality: image.quality,
          targetVisibility: image.targetVisibility,
          maskQuality: image.maskQuality,
        });
        const readableIds = new Set(image.targetVisibility.filter((item) => item.readable).map((item) => item.targetId));
        const floorId = track.surfaceTargets.floor;
        const hasReadableFloor = Boolean(floorId && readableIds.has(floorId));
        const requiresReadableWall = track.surfaceTargets.walls.length > 0;
        const hasReadableWall = !requiresReadableWall
          || track.surfaceTargets.walls.some((targetId) => readableIds.has(targetId));
        const hasAcceptableOcclusion = image.maskQuality.occluderPixelRatio <= 0.72;
        if (!image.quality.valid || !hasReadableFloor || !hasReadableWall || !hasAcceptableOcclusion) {
          invalidHeroRoomIds.push(hero.roomId);
          incompleteRooms.push({
            roomId: hero.roomId,
            uncoveredTargetIds: [
              ...(!hasReadableFloor && floorId ? [floorId] : []),
              ...(requiresReadableWall && !hasReadableWall ? track.surfaceTargets.walls : []),
            ],
            invalidViewIds: image.quality.valid && hasAcceptableOcclusion ? [] : [image.viewId],
          });
        }
      }

      const transitionPairs = [];
      for (const transition of plan.transitions) {
        transitionPairs.push(await captureTransitionPair(transition));
      }

      return {
        tool: "observe_home_harmony",
        status: incompleteRooms.length === 0 && transitionPairs.every((pair) => pair.status === "ready")
          ? "ready"
          : "incomplete_observation",
        evidenceLevel: "pixel_verified_coverage",
        houseId: plan.houseId,
        scheme: { schemeId: scheme?.scheme_id ?? null, title: scheme?.title ?? null },
        roomContactSheet: await composeRoomContactSheet(heroImages),
        transitionPairs,
        incompleteRooms,
        invalidHeroRoomIds,
        roomHeroDiagnostics,
        captureDiagnostics: {
          durationMs: Math.round(performance.now() - captureStartedAt),
          heroCandidateCount,
          heroCandidateLimitPerRoom: HOME_HERO_MAX_CANDIDATES,
          transitionImageCount: transitionPairs.length * 2,
        },
      };
    };

    const reconcileActiveAssets = () => {
      const activeAssetIds = new Set<string>();
      targetIndex.forEach((meshes) => meshes.forEach((mesh) => {
        const currentAssetId = mesh.userData.currentAssetId;
        if (typeof currentAssetId === "string") activeAssetIds.add(currentAssetId);
      }));
      heroSurfaceRuntime.releaseUnusedWallpaperMaps(activeAssetIds);
      surfaceMaterials.forEach((candidate, candidateId) => {
        if (
          (candidateId.startsWith("floor_") || candidateId.startsWith("tile_"))
          && !activeAssetIds.has(candidateId)
          && candidate.userData.sharedPbr !== true
        ) {
          candidate.userData.releasePbr?.();
        }
      });
    };

    const applyAsset = (
      targetIds: string[],
      assetId: string,
      parameters?: PaintParameters | null,
      reconcile = true,
    ) => {
      const material = surfaceMaterials.get(assetId);
      if (!material) return;
      const pendingPbr = material.userData.ensurePbr?.();
      if (pendingPbr instanceof Promise) {
        // Re-render once the async PBR maps land (the tint renders immediately).
        pendingPbr.then(() => { markDirty(); }).catch(() => { markDirty(); });
      }
      markDirty();
      targetIds.forEach((targetId) => {
        targetIndex.get(targetId)?.forEach((mesh) => {
          const currentParameters = mesh.userData.currentAssetParameters ?? null;
          const nextParameters = parameters ?? null;
          if (
            mesh.userData.currentAssetId === assetId
            && JSON.stringify(currentParameters) === JSON.stringify(nextParameters)
          ) return;
          const paintAsset = PAINT_VARIANT_BY_ID.get(assetId);
          let assignmentMaterial: THREE.Material = material;
          if (paintAsset && !paintAsset.isSpecialty && parameters) {
            const resolved = resolvePaintSelection(paintAsset.id, parameters);
            if (resolved) {
              const instance = material.clone();
              instance.name = `WEB_${assetId}_${targetId}`;
              instance.color.set(resolved.color).multiplyScalar(PAINT_APPEARANCE_CALIBRATION.directLightShare);
              instance.emissive.set(resolved.color).multiplyScalar(PAINT_APPEARANCE_CALIBRATION.colourStandardShare);
              instance.normalScale.set(resolved.normalScale, resolved.normalScale);
              const roughnessMaps = material.userData.paintRoughnessMaps as
                | { matte: THREE.Texture; eggshell: THREE.Texture }
                | undefined;
              if (roughnessMaps) instance.roughnessMap = roughnessMaps[parameters.finish];
              instance.envMapIntensity = resolved.envMapIntensity;
              instance.userData = { ...material.userData, parameterInstance: true, paintParameters: parameters };
              instance.needsUpdate = true;
              assignmentMaterial = instance;
            }
          }
          const previous = Array.isArray(mesh.material) ? null : mesh.material;
          if (previous?.userData.parameterInstance) previous.dispose();
          const wallVariant = material.userData.wallVariant;
          mesh.material = assignmentMaterial !== material
            ? assignmentMaterial
            : typeof mesh.userData.wall_face_id === "string"
            && wallVariant instanceof THREE.Material
            ? wallVariant
            : material;
          mesh.userData.currentAssetId = assetId;
          mesh.userData.currentAssetParameters = parameters ?? null;
        });
      });
      if (reconcile) reconcileActiveAssets();
      setSelected((current) => current && targetIds.includes(current.targetId) ? { ...current, assetId } : current);
    };

    const setCeilingPreset = (roomId: string, presetId: string) => {
      activeCeilingPresets[roomId] = presetId;
      updateCeilingVisibility();
      markDirty();
      const targetId = `surface_real4_ceiling_${roomId}`;
      const meshes = targetIndex.get(targetId) ?? [];
      meshes.forEach((mesh) => { mesh.userData.currentAssetId = presetId; });
      setSelected((current) => current?.targetId.includes("_ceiling_") ? { ...current, assetId: presetId } : current);
    };

    apiRef.current = {
      applyAsset,
      reconcileAssets: reconcileActiveAssets,
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
        markDirty();
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
      "/models/house_spacious_yunkuo_135_v4.glb?revision=hard-finish-realism-pass-v5-wall-coverage",
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
          if (object.userData.surface_role === "ceiling") {
            object.material = flatCeilingMaterial;
            object.userData.currentAssetId = "ceiling_flat_01";
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
            const material = surfaceMaterials.get(assetId)!;
            const wallVariant = material.userData.wallVariant;
            object.material = typeof object.userData.wall_face_id === "string"
              && wallVariant instanceof THREE.Material
              ? wallVariant
              : material;
            object.userData.currentAssetId = assetId;
            material.userData.ensurePbr?.();
          }
        });
        scene.add(modelRoot);
        applyPresentation();
        setTourProgressValue(0);
        setProgress(82);

        const finishInitialSurfaceLoad = async () => {
          try {
            const scheme = await fetchCurrentScheme(designRunIdFromLocation());
            // applyScheme kicks off every referenced asset's PBR load in the
            // background. We only gate "ready" on the shared core maps (paint
            // micro, wood, linen) — scheme wall/floor textures pop in as they
            // arrive instead of delaying the first interactive frame.
            applyScheme(scheme);
            setProgress(90);
            const activePbrLoads = Array.from(new Set(scheme.assignments.map((assignment) => assignment.asset_id)))
              .map((assetId) => surfaceMaterials.get(assetId)?.userData.ensurePbr?.())
              .filter((pending): pending is Promise<unknown> => pending instanceof Promise);
            await Promise.all([heroSurfaceRuntime.ready, ...activePbrLoads]);
            // 预热：纹理就绪后立即强制编译所有材质的 WebGL shader。WebGL 是惰性编译，
            // 若等到第一次 observe_room 才编译，横厅全屋 + 多材质会在取证时卡数十秒。
            if (!disposed) {
              renderer.compile(scene, camera);
            }
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
        // Camera motion stays at RAF cadence; React only needs to refresh the
        // textual timer and slider often enough to feel continuous.
        if (time - lastTourUiUpdate > 100 || nextProgress >= 1) {
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
      const key = frameKey();
      if (needsRender || key !== lastFrameKey) {
        composer.render();
        lastFrameKey = key;
        needsRender = false;
      }
      frame = requestAnimationFrame(animate);
    };
    frame = requestAnimationFrame(animate);

    return () => {
      disposed = true;
      cancelAnimationFrame(frame);
      resizeObserver.disconnect();
      renderer.domElement.removeEventListener("pointerup", onPointerUp);
      renderer.domElement.removeEventListener("webglcontextrestored", markDirty);
      controls.dispose();
      composer.dispose();
      evidenceComposer.dispose();
      visibilityRenderTarget.dispose();
      renderer.dispose();
      environmentTexture?.dispose();
      pmrem.dispose();
      heroSurfaceRuntime.dispose();
      exteriorBackdrop.dispose();
      architecturalRevealMaterial.dispose();
      flatCeilingMaterial.dispose();
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
        const wallVariant = material.userData.wallVariant;
        if (wallVariant instanceof THREE.Material) wallVariant.dispose();
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

  const chooseWallAsset = (assetId: string, parameters?: PaintParameters | null) => {
    if (selected?.targetKind !== "wall_face") return;
    apiRef.current?.applyAsset([selected.targetId], assetId, parameters);
  };

  const choosePaint = (
    nextPaintAssetId: string = paintAssetId,
    nextTone: PaintToneId = paintTone,
    nextFinish: PaintFinishId = paintFinish,
    nextSaturation: number = paintSaturation,
  ) => {
    setPaintAssetId(nextPaintAssetId);
    setPaintTone(nextTone);
    setPaintFinish(nextFinish);
    setPaintSaturation(nextSaturation);
    const selection = findPaintVariant(nextPaintAssetId, nextTone, nextFinish, nextSaturation);
    if (selection) chooseWallAsset(selection.id, selection.parameters);
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
    <main className={`room-experience ${tourPlaying ? "tour-playing" : ""}`}>
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
          <Link href="/chat">对话助手</Link>
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
          <button
            key={`tour-toggle-${activeTrack.roomId}`}
            type="button"
            disabled={loadState !== "ready"}
            aria-label={tourPlaying ? `暂停${activeTrack.roomLabel}导览` : `播放${activeTrack.roomLabel}导览`}
            onClick={toggleTour}
          >
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
                : `5 品类 · ${PAINT_VARIANTS.length + WALLPAPERS.length + FLOORS.length + TILES.length + CEILINGS.length} 个资产 / 预设`}
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
          <div className="drawer-title"><span>01</span><div><h3>墙漆 · {PAINT_VARIANTS.length}</h3><p>{wetWallSelected ? "当前为湿区墙面，仅允许瓷砖" : "先点击墙面，再选择色系、明度、漆面或矿物涂层"}</p></div></div>
          <div className="paint-grid" aria-label="墙漆色彩选择">
            {PAINT_CATALOG.paints.map((paint) => (
              <button
                type="button"
                key={paint.asset_id}
                disabled={!wallTargetSelected || wetWallSelected}
                aria-pressed={paintAssetId === paint.asset_id}
                className={paintAssetId === paint.asset_id ? "selected" : ""}
                title={paint.description}
                onClick={() => choosePaint(paint.asset_id)}
              >
                <i style={{ background: findPaintVariant(paint.asset_id, paintTone, paintFinish, paintSaturation)?.color }} />
                <span>{paint.name_zh.split("与")[0].replace("、", " / ")}</span>
              </button>
            ))}
          </div>
          <div className="paint-parameters">
            <div><small>明度</small><div role="group" aria-label="墙漆明度">
              {PAINT_CATALOG.tones.map((tone) => <button type="button" key={tone.id} disabled={!wallTargetSelected || wetWallSelected} className={paintTone === tone.id ? "selected" : ""} onClick={() => choosePaint(paintAssetId, tone.id)}>{tone.name_zh}</button>)}
            </div></div>
            <div><small>漆面</small><div role="group" aria-label="墙漆漆面">
              {PAINT_CATALOG.finishes.map((finish) => <button type="button" key={finish.id} disabled={!wallTargetSelected || wetWallSelected} className={paintFinish === finish.id ? "selected" : ""} onClick={() => choosePaint(paintAssetId, paintTone, finish.id)}>{finish.name_zh}</button>)}
            </div></div>
            <div><small>饱和度 · {Math.round(paintSaturation * 100)}%</small><div role="group" aria-label="墙漆饱和度">
              <input
                type="range"
                min={PAINT_CATALOG.parameter_schema.saturation.minimum}
                max={PAINT_CATALOG.parameter_schema.saturation.maximum}
                step={PAINT_CATALOG.parameter_schema.saturation.step}
                value={paintSaturation}
                disabled={!wallTargetSelected || wetWallSelected}
                onChange={(event) => choosePaint(paintAssetId, paintTone, paintFinish, Number(event.target.value))}
              />
            </div></div>
          </div>
          <div className="material-options" aria-label="矿物连续涂层">
            {SPECIALTY_PAINTS.map((product) => (
              <button
                type="button"
                key={product.id}
                disabled={!wallTargetSelected || wetWallSelected}
                aria-pressed={wallTargetSelected && selected?.assetId === product.id}
                className={wallTargetSelected && selected?.assetId === product.id ? "selected" : ""}
                title={product.description}
                onClick={() => chooseWallAsset(product.id)}
              >
                <i style={{ background: `${product.color} url('/assets/paints/${product.id}_thumb.webp') center / cover` }} />
                <span>{product.nameZh.replace("涂层", "")}</span>
              </button>
            ))}
          </div>
          <p className="paint-notice">4K 真实尺度微表面 · 屏幕预览不替代实体色卡</p>
        </section>

        <section>
          <div className="drawer-title"><span>02</span><div><h3>墙纸 · {WALLPAPERS.length}</h3><p>真实比例与对花规则，按需加载 PBR</p></div></div>
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
          <div className="drawer-title"><span>03</span><div><h3>地板 · {FLOORS.length}</h3><p>真实板宽与铺法元数据，作用于当前房间地面</p></div></div>
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
          <div className="drawer-title"><span>04</span><div><h3>瓷砖 · {TILES.length}</h3><p>{wetWallSelected ? "作用于当前选中的湿区墙面" : "与木地板互斥，切换当前房间地面"}</p></div></div>
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
          <div className="drawer-title"><span>05</span><div><h3>吊顶 · {CEILINGS.length}</h3><p>真实几何预设；厨卫大板仅适用于湿区</p></div></div>
          <div className="material-options">
            {CEILINGS.map((product) => {
              const suitable = product.preset === "flat"
                || (product.preset === "modular_panel" ? WET_ROOM_IDS.has(activeRoomId) : !WET_ROOM_IDS.has(activeRoomId));
              return (
                <button type="button" key={product.id} disabled={!suitable} aria-pressed={ceilingChoice === product.id} className={ceilingChoice === product.id ? "selected" : ""} title={`下降 ${product.drop_height_mm}mm`} onClick={() => chooseCeiling(product.id)}>
                  <i style={{ background: product.preset === "modular_panel" ? "repeating-linear-gradient(90deg,#c8cbc6 0 32%,#7b7f7a 32% 33%)" : product.preset === "floating_shadow_gap" ? "radial-gradient(circle,#ece7da 45%,#242725 47% 52%,#d8d2c4 54%)" : product.preset === "perimeter_cove" ? "linear-gradient(135deg,#e8e1d2 48%,#f0ad62 50%,#2d302e 54%)" : "linear-gradient(135deg,#ece7da,#c8c0b0)" }} />
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
