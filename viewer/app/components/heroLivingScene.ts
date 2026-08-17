import * as THREE from "three";
import { RoundedBoxGeometry } from "three/examples/jsm/geometries/RoundedBoxGeometry.js";
import type { GLTFLoader } from "three/examples/jsm/loaders/GLTFLoader.js";
import { PAINT_APPEARANCE_CALIBRATION, PAINT_CATALOG, PAINT_VARIANTS } from "../data/paintCatalog";
import { WALLPAPER_APPEARANCE_CALIBRATION, WALLPAPERS } from "../data/wallpaperCatalog";

const HERO_ROOT = "/assets/hero-living";

function texture(
  loader: THREE.TextureLoader,
  path: string,
  anisotropy: number,
  options: { color?: boolean; repeat?: [number, number]; clamp?: boolean } = {},
) {
  const map = loader.load(path.startsWith("/") ? path : `${HERO_ROOT}/${path}`);
  if (options.color) map.colorSpace = THREE.SRGBColorSpace;
  map.wrapS = map.wrapT = options.clamp ? THREE.ClampToEdgeWrapping : THREE.RepeatWrapping;
  if (options.repeat) map.repeat.set(...options.repeat);
  map.anisotropy = anisotropy;
  return map;
}

// Async variant of `texture`: same configuration, but resolves with the map so
// callers can await a full PBR set (used to signal render-on-demand when the
// maps land after an idle frame was skipped).
async function textureAsync(
  loader: THREE.TextureLoader,
  path: string,
  anisotropy: number,
  options: { color?: boolean; repeat?: [number, number]; clamp?: boolean } = {},
) {
  const map = await loader.loadAsync(path.startsWith("/") ? path : `${HERO_ROOT}/${path}`);
  if (options.color) map.colorSpace = THREE.SRGBColorSpace;
  map.wrapS = map.wrapT = options.clamp ? THREE.ClampToEdgeWrapping : THREE.RepeatWrapping;
  if (options.repeat) map.repeat.set(...options.repeat);
  map.anisotropy = anisotropy;
  return map;
}

function rounded(
  group: THREE.Group,
  name: string,
  size: [number, number, number],
  position: [number, number, number],
  material: THREE.Material,
  radius = 0.06,
  rotation: [number, number, number] = [0, 0, 0],
) {
  const mesh = new THREE.Mesh(new RoundedBoxGeometry(size[0], size[1], size[2], 6, radius), material);
  mesh.name = name;
  mesh.position.set(...position);
  mesh.rotation.set(...rotation);
  mesh.castShadow = true;
  mesh.receiveShadow = true;
  group.add(mesh);
  return mesh;
}

function cylinder(
  group: THREE.Group,
  name: string,
  radius: number,
  height: number,
  position: [number, number, number],
  material: THREE.Material,
  segments = 32,
) {
  const mesh = new THREE.Mesh(new THREE.CylinderGeometry(radius, radius, height, segments), material);
  mesh.name = name;
  mesh.position.set(...position);
  mesh.castShadow = true;
  mesh.receiveShadow = true;
  group.add(mesh);
  return mesh;
}

function makeCurtain(material: THREE.Material, width: number, height: number) {
  const geometry = new THREE.PlaneGeometry(width, height, 48, 12);
  const position = geometry.attributes.position;
  for (let index = 0; index < position.count; index += 1) {
    const x = position.getX(index);
    const y = position.getY(index);
    const edgeFade = Math.min(1, (height / 2 - Math.abs(y)) * 5 + 0.12);
    position.setZ(index, Math.sin((x / width + 0.5) * Math.PI * 13) * 0.045 * edgeFade);
  }
  geometry.computeVertexNormals();
  const curtain = new THREE.Mesh(geometry, material);
  curtain.castShadow = true;
  curtain.receiveShadow = true;
  return curtain;
}

function makeRugTexture(anisotropy: number) {
  const canvas = document.createElement("canvas");
  canvas.width = 1024;
  canvas.height = 1024;
  const context = canvas.getContext("2d")!;
  const gradient = context.createLinearGradient(0, 0, 1024, 1024);
  gradient.addColorStop(0, "#9a8e7d");
  gradient.addColorStop(0.5, "#b6aa98");
  gradient.addColorStop(1, "#7f7568");
  context.fillStyle = gradient;
  context.fillRect(0, 0, 1024, 1024);
  for (let index = 0; index < 15000; index += 1) {
    const shade = 85 + Math.floor(Math.random() * 95);
    context.fillStyle = `rgba(${shade},${shade - 7},${shade - 15},${0.04 + Math.random() * 0.09})`;
    const x = Math.random() * 1024;
    const y = Math.random() * 1024;
    context.fillRect(x, y, 0.5 + Math.random() * 2, 3 + Math.random() * 8);
  }
  context.strokeStyle = "rgba(231,221,203,.25)";
  context.lineWidth = 6;
  context.strokeRect(24, 24, 976, 976);
  const map = new THREE.CanvasTexture(canvas);
  map.colorSpace = THREE.SRGBColorSpace;
  map.anisotropy = anisotropy;
  return map;
}

function placeNormalizedModel(
  loader: GLTFLoader,
  root: THREE.Group,
  url: string,
  targetWidth: number,
  position: [number, number, number],
  rotationY: number,
  hidePrefix?: string,
  materialOverrides?: Record<string, THREE.Material>,
) {
  return new Promise<void>((resolve) => {
    loader.load(
      url,
      (gltf) => {
        const model = gltf.scene;
        model.traverse((object) => {
          if (!(object instanceof THREE.Mesh)) return;
          if (url.includes("hero_modern_sofa") && object.name.startsWith("back_piping")) {
            object.visible = false;
          }
          object.castShadow = true;
          object.receiveShadow = true;
          if (materialOverrides) {
            if (Array.isArray(object.material)) {
              object.material = object.material.map((material) => materialOverrides[material.name] ?? material);
            } else {
              object.material = materialOverrides[object.material.name] ?? object.material;
            }
          }
          const materials = Array.isArray(object.material) ? object.material : [object.material];
          materials.forEach((material) => {
            if (material instanceof THREE.MeshStandardMaterial) {
              material.envMapIntensity = 0.85;
              material.needsUpdate = true;
            }
          });
        });
        const initial = new THREE.Box3().setFromObject(model);
        const size = initial.getSize(new THREE.Vector3());
        const horizontal = Math.max(size.x, size.z);
        model.scale.setScalar(targetWidth / horizontal);
        model.updateMatrixWorld(true);
        const scaled = new THREE.Box3().setFromObject(model);
        const center = scaled.getCenter(new THREE.Vector3());
        model.position.set(-center.x, -scaled.min.y, -center.z);
        model.rotation.y = rotationY;
        const wrapper = new THREE.Group();
        wrapper.position.set(...position);
        wrapper.add(model);
        if (hidePrefix) {
          root.traverse((object) => {
            if (object.name.startsWith(hidePrefix)) object.visible = false;
          });
        }
        root.add(wrapper);
        resolve();
      },
      undefined,
      (error) => {
        console.warn(`Hero model failed to load: ${url}`, error);
        resolve();
      },
    );
  });
}

export function buildHeroLiving(renderer: THREE.WebGLRenderer, loader: GLTFLoader) {
  const root = new THREE.Group();
  root.name = "HERO_LIVING_ROOM";
  root.userData.room_id = "living_room";
  const anisotropy = Math.min(renderer.capabilities.getMaxAnisotropy(), 16);
  const textureLoader = new THREE.TextureLoader();

  const fabricNormal = texture(textureLoader, "textures/fabric_pattern_05_nor_gl_1k.jpg", anisotropy, { repeat: [3, 3] });
  const fabricRough = texture(textureLoader, "textures/fabric_pattern_05_rough_1k.jpg", anisotropy, { repeat: [3, 3] });
  const sofaMaterial = new THREE.MeshPhysicalMaterial({
    color: "#70786c",
    normalMap: fabricNormal,
    normalScale: new THREE.Vector2(0.34, 0.34),
    roughnessMap: fabricRough,
    roughness: 0.82,
    sheen: 0.7,
    sheenColor: new THREE.Color("#ddd8c8"),
    sheenRoughness: 0.76,
  });
  const pipingMaterial = new THREE.MeshStandardMaterial({ color: "#777c70", roughness: 0.88 });
  const accentFabric = new THREE.MeshPhysicalMaterial({ color: "#a85435", roughness: 0.82, sheen: 0.55, sheenColor: new THREE.Color("#e6a37f") });
  const walnut = new THREE.MeshPhysicalMaterial({ color: "#3c261a", roughness: 0.38, clearcoat: 0.18, clearcoatRoughness: 0.58 });
  const brass = new THREE.MeshStandardMaterial({ color: "#b08a52", metalness: 0.82, roughness: 0.25 });
  const ceramic = new THREE.MeshPhysicalMaterial({ color: "#d9d4c7", roughness: 0.22, clearcoat: 0.4 });
  const darkCeramic = new THREE.MeshPhysicalMaterial({ color: "#242825", roughness: 0.28, clearcoat: 0.25 });
  const leafMaterial = new THREE.MeshPhysicalMaterial({ color: "#445943", roughness: 0.72, sheen: 0.2, side: THREE.DoubleSide });
  const curtainMaterial = new THREE.MeshPhysicalMaterial({
    color: "#d8d1c2",
    normalMap: fabricNormal,
    normalScale: new THREE.Vector2(0.18, 0.18),
    roughness: 0.92,
    transparent: true,
    opacity: 0.88,
    transmission: 0.04,
    sheen: 0.9,
    sheenColor: new THREE.Color("#fff8e9"),
    side: THREE.DoubleSide,
  });

  // Linen sofa: separate, slightly irregular cushions and seam strips break the toy-like silhouette.
  rounded(root, "sofa_plinth", [0.78, 0.18, 2.72], [0.70, 0.25, -2.48], walnut, 0.035);
  rounded(root, "sofa_body", [0.86, 0.30, 2.76], [0.67, 0.48, -2.48], sofaMaterial, 0.105);
  rounded(root, "sofa_back", [0.23, 0.72, 2.72], [0.34, 0.84, -2.48], sofaMaterial, 0.095, [0, 0, -0.035]);
  rounded(root, "sofa_arm_left", [0.76, 0.54, 0.20], [0.71, 0.66, -1.18], sofaMaterial, 0.09);
  rounded(root, "sofa_arm_right", [0.76, 0.54, 0.20], [0.71, 0.66, -3.78], sofaMaterial, 0.09);
  [-3.30, -2.48, -1.66].forEach((z, index) => {
    rounded(root, `sofa_seat_${index}`, [0.68, 0.20, 0.74], [0.86, 0.66 + (index === 1 ? -0.012 : 0), z], sofaMaterial, 0.10, [0, (index - 1) * 0.012, 0]);
    rounded(root, `sofa_back_cushion_${index}`, [0.22, 0.68, 0.72], [0.49, 1.02 + (index === 1 ? 0.018 : 0), z], sofaMaterial, 0.105, [(index - 1) * 0.018, (index - 1) * 0.018, -0.08]);
    rounded(root, `sofa_seam_${index}`, [0.012, 0.026, 0.64], [1.205, 0.69, z], pipingMaterial, 0.005);
  });
  cylinder(root, "sofa_leg_1", 0.025, 0.18, [0.52, 0.11, -1.26], brass, 16);
  cylinder(root, "sofa_leg_2", 0.025, 0.18, [0.52, 0.11, -3.70], brass, 16);
  cylinder(root, "sofa_leg_3", 0.025, 0.18, [1.00, 0.11, -1.26], brass, 16);
  cylinder(root, "sofa_leg_4", 0.025, 0.18, [1.00, 0.11, -3.70], brass, 16);

  const rugMap = makeRugTexture(anisotropy);
  const rugMaterial = new THREE.MeshPhysicalMaterial({ map: rugMap, roughness: 1, sheen: 0.35, sheenColor: new THREE.Color("#d7c8ae") });
  rounded(root, "handwoven_rug", [2.72, 0.025, 2.42], [2.25, 0.035, -2.48], rugMaterial, 0.055);

  // Window dressing, skirting and art create believable architectural scale.
  const leftCurtain = makeCurtain(curtainMaterial, 1.08, 2.48);
  leftCurtain.name = "curtain_left";
  leftCurtain.position.set(0.78, 1.50, -0.27);
  root.add(leftCurtain);
  const rightCurtain = makeCurtain(curtainMaterial, 1.08, 2.48);
  rightCurtain.name = "curtain_right";
  rightCurtain.position.set(3.48, 1.50, -0.27);
  root.add(rightCurtain);
  cylinder(root, "curtain_rail", 0.022, 3.62, [2.13, 2.73, -0.23], brass, 24).rotation.z = Math.PI / 2;
  rounded(root, "skirting_south", [3.72, 0.09, 0.035], [2.15, 0.07, -0.23], ceramic, 0.012);
  rounded(root, "skirting_west", [0.035, 0.09, 4.10], [0.23, 0.07, -2.40], ceramic, 0.012);
  const shadowGap = new THREE.MeshStandardMaterial({ color: "#4b443a", roughness: 1 });
  rounded(root, "ceiling_shadow_gap_south", [3.70, 0.012, 0.012], [2.15, 2.765, -0.235], shadowGap, 0.003);
  rounded(root, "ceiling_shadow_gap_west", [0.012, 0.012, 4.08], [0.235, 2.765, -2.40], shadowGap, 0.003);

  rounded(root, "console_body", [0.42, 0.48, 1.82], [3.73, 0.34, -2.55], walnut, 0.035);
  rounded(root, "console_door_left", [0.025, 0.36, 0.80], [3.515, 0.38, -2.99], walnut, 0.01);
  rounded(root, "console_door_right", [0.025, 0.36, 0.80], [3.515, 0.38, -2.11], walnut, 0.01);
  cylinder(root, "console_handle_left", 0.009, 0.18, [3.49, 0.42, -2.63], brass, 12);
  cylinder(root, "console_handle_right", 0.009, 0.18, [3.49, 0.42, -2.47], brass, 12);
  rounded(root, "art_frame", [0.055, 1.02, 1.46], [0.245, 1.58, -2.55], walnut, 0.018);
  rounded(root, "art_canvas", [0.028, 0.90, 1.34], [0.280, 1.58, -2.55], new THREE.MeshStandardMaterial({ color: "#8f8370", roughness: 0.96 }), 0.01);
  const artAccent = rounded(root, "art_accent", [0.018, 0.35, 0.70], [0.300, 1.52, -2.40], new THREE.MeshStandardMaterial({ color: "#b96743", roughness: 0.9 }), 0.008);
  artAccent.rotation.x = -0.18;

  cylinder(root, "vase", 0.10, 0.34, [3.48, 0.18, -0.66], darkCeramic, 32);
  for (let index = 0; index < 8; index += 1) {
    const leaf = new THREE.Mesh(new THREE.SphereGeometry(0.16, 18, 12), leafMaterial);
    const angle = (index / 8) * Math.PI * 2;
    leaf.scale.set(0.40, 1.55, 0.18);
    leaf.position.set(3.48 + Math.cos(angle) * 0.18, 0.52 + (index % 3) * 0.11, -0.66 + Math.sin(angle) * 0.18);
    leaf.rotation.set(Math.sin(angle) * 0.55, angle, Math.cos(angle) * 0.65);
    leaf.castShadow = true;
    root.add(leaf);
  }
  [
    [3.72, 0.69, -2.30, 0.27, "#b7a47f"],
    [3.72, 0.72, -2.30, 0.19, "#d5c8ad"],
    [3.72, 0.75, -2.30, 0.12, "#7c5e46"],
  ].forEach(([x, y, z, width, color], index) => {
    rounded(root, `book_${index}`, [0.16, 0.035, width as number], [x as number, y as number, z as number], new THREE.MeshStandardMaterial({ color: color as string, roughness: 0.8 }), 0.006);
  });

  cylinder(root, "floor_lamp_stem", 0.018, 1.38, [1.34, 0.73, -4.00], brass, 20);
  cylinder(root, "floor_lamp_base", 0.18, 0.025, [1.34, 0.025, -4.00], brass, 32);
  const lampShade = new THREE.Mesh(new THREE.CylinderGeometry(0.17, 0.29, 0.38, 40, 1, true), curtainMaterial);
  lampShade.name = "floor_lamp_shade";
  lampShade.position.set(1.34, 1.48, -4.00);
  lampShade.castShadow = true;
  root.add(lampShade);
  const lampGlow = new THREE.PointLight("#ffd6a0", 21, 4.2, 2);
  lampGlow.position.set(1.34, 1.44, -4.00);
  lampGlow.castShadow = true;
  lampGlow.shadow.mapSize.set(512, 512);
  root.add(lampGlow);

  const windowLight = new THREE.RectAreaLight("#cfe3f1", 5.5, 2.7, 2.25);
  windowLight.position.set(2.15, 1.55, -0.34);
  windowLight.lookAt(2.15, 1.1, -2.4);
  root.add(windowLight);

  const wallWash = new THREE.RectAreaLight("#f5d7b0", 1.25, 1.1, 1.8);
  wallWash.position.set(1.38, 1.78, -3.58);
  wallWash.lookAt(0.20, 1.54, -3.05);
  root.add(wallWash);

  const ready = Promise.all([
    placeNormalizedModel(loader, root, `${HERO_ROOT}/modern_coffee_table_01/modern_coffee_table_01_1k.gltf`, 1.28, [2.22, 0.035, -2.48], Math.PI / 2),
    placeNormalizedModel(loader, root, `${HERO_ROOT}/modern_arm_chair_01/modern_arm_chair_01_1k.gltf`, 0.92, [2.82, 0.035, -0.95], -Math.PI * 0.70),
    placeNormalizedModel(
      loader,
      root,
      `${HERO_ROOT}/hero_modern_sofa.glb`,
      2.68,
      [0.68, 0.035, -2.48],
      Math.PI / 2,
      "sofa_",
      {
        HERO_SOFA_FABRIC: sofaMaterial,
        HERO_SOFA_PIPING: pipingMaterial,
        HERO_SOFA_WOOD: walnut,
        HERO_SOFA_BRASS: brass,
        HERO_SOFA_ACCENT: accentFabric,
      },
    ),
  ]).then(() => undefined);

  const dispose = () => {
    root.traverse((object) => {
      if (!(object instanceof THREE.Mesh)) return;
      object.geometry.dispose();
      const materials = Array.isArray(object.material) ? object.material : [object.material];
      materials.forEach((material) => material.dispose());
    });
    [fabricNormal, fabricRough, rugMap].forEach((map) => map.dispose());
  };

  return { root, ready, dispose };
}

export function enhanceHeroSurfaces(materials: Map<string, THREE.MeshStandardMaterial>, renderer: THREE.WebGLRenderer) {
  const anisotropy = Math.min(renderer.capabilities.getMaxAnisotropy(), 16);
  let resolveReady: () => void = () => undefined;
  const ready = new Promise<void>((resolve) => { resolveReady = resolve; });
  const loadingManager = new THREE.LoadingManager(() => resolveReady());
  const loader = new THREE.TextureLoader(loadingManager);
  // Floor UVs are authored in metres. One source tile spans about 2 m, so
  // half a repeat per metre keeps plank scale consistent in every room.
  const woodRepeat: [number, number] = [0.5, 0.5];
  const woodColor = texture(loader, "textures/wood_floor_diff_1k.jpg", anisotropy, { color: true, repeat: woodRepeat });
  const woodNormal = texture(loader, "textures/wood_floor_nor_gl_1k.jpg", anisotropy, { repeat: woodRepeat });
  const woodRough = texture(loader, "textures/wood_floor_rough_1k.jpg", anisotropy, { repeat: woodRepeat });
  // Numbered wall-face UVs are authored in metres. Deriving the repeat from
  // catalog metadata keeps the renderer and procedural generator in lockstep.
  const [paintWidthM, paintHeightM] = PAINT_CATALOG.texture_set.physical_size_m;
  const paintRepeat: [number, number] = [1 / paintWidthM, 1 / paintHeightM];
  // Web-sized variants: the 4K masters are upscaled from a 2048 source, so the
  // 2048 web set costs ~4x less decode time and VRAM with no visible difference.
  const paintBase = texture(loader, "/assets/paints/paint_micro_basecolor_web.jpg", anisotropy, { color: true, repeat: paintRepeat });
  const paintNormal = texture(loader, "/assets/paints/paint_micro_normal_gl_web.jpg", anisotropy, { repeat: paintRepeat });
  const paintRoughMatte = texture(loader, "/assets/paints/paint_micro_roughness_matte_web.jpg", anisotropy, { repeat: paintRepeat });
  const paintRoughEggshell = texture(loader, "/assets/paints/paint_micro_roughness_eggshell_web.jpg", anisotropy, { repeat: paintRepeat });
  const loadedSpecialtyPaintMaps = new Map<string, THREE.Texture[]>();
  const loadedWallpaperMaps = new Map<string, THREE.Texture[]>();

  ["floor_light_oak_matte_01", "floor_honey_oak_matte_01"].forEach((assetId) => {
    const material = materials.get(assetId);
    if (!material) return;
    material.map?.dispose();
    material.map = woodColor;
    material.normalMap = woodNormal;
    material.normalScale.set(0.30, 0.30);
    material.roughnessMap = woodRough;
    // `woodRough` is authored in absolute linear roughness values. Do not apply
    // a second scalar here, or the material becomes glossier than its catalogued
    // matte finish (roughness maps and the scalar are multiplied by Three.js).
    material.roughness = 1;
    material.color.set(assetId.includes("honey") ? "#a86f46" : "#d2b38b");
    material.envMapIntensity = 0.14;
    // These three textures are intentionally shared by both catalogue entries.
    // The generic inactive-material cleanup must not dispose them through one
    // material while the other one is still visible.
    material.userData.sharedPbr = true;
    material.needsUpdate = true;
  });

  PAINT_VARIANTS.forEach((variant) => {
    const material = materials.get(variant.id);
    if (!material) return;
    if (variant.isSpecialty && variant.texturePrefix) {
      material.userData.ensurePbr = () => {
        if (loadedSpecialtyPaintMaps.has(variant.id)) return;
        const repeat: [number, number] = [1 / variant.physicalSizeM[0], 1 / variant.physicalSizeM[1]];
        const basePath = `/assets/paints/${variant.texturePrefix}`;
        const load = Promise.all([
          textureAsync(loader, `${basePath}_basecolor_web.jpg`, anisotropy, { color: true, repeat }),
          textureAsync(loader, `${basePath}_normal_gl_web.jpg`, anisotropy, { repeat }),
          textureAsync(loader, `${basePath}_roughness_web.jpg`, anisotropy, { repeat }),
        ]).then(([color, normal, roughness]) => {
          loadedSpecialtyPaintMaps.set(variant.id, [color, normal, roughness]);
          material.map = color;
          material.normalMap = normal;
          material.normalScale.set(variant.normalScale, variant.normalScale);
          material.roughnessMap = roughness;
          material.roughness = 1;
          material.color.set("#ffffff").multiplyScalar(PAINT_APPEARANCE_CALIBRATION.directLightShare);
          material.emissive.set("#ffffff").multiplyScalar(PAINT_APPEARANCE_CALIBRATION.colourStandardShare);
          material.emissiveMap = color;
          material.emissiveIntensity = 1;
          material.envMapIntensity = variant.envMapIntensity;
          material.needsUpdate = true;
        }).catch((error) => {
          console.warn(`Failed to load specialty paint maps for ${variant.id}`, error);
        });
        return load;
      };
      return;
    }
    material.map?.dispose();
    material.map = paintBase;
    material.normalMap = paintNormal;
    material.normalScale.set(variant.normalScale, variant.normalScale);
    material.roughnessMap = variant.parameters?.finish === "eggshell" ? paintRoughEggshell : paintRoughMatte;
    material.userData.paintRoughnessMaps = { matte: paintRoughMatte, eggshell: paintRoughEggshell };
    material.roughness = 1;
    material.color.set(variant.color).multiplyScalar(PAINT_APPEARANCE_CALIBRATION.directLightShare);
    material.emissive.set(variant.color).multiplyScalar(PAINT_APPEARANCE_CALIBRATION.colourStandardShare);
    material.emissiveIntensity = 1;
    material.emissiveMap = paintBase;
    material.envMapIntensity = variant.envMapIntensity;
    material.needsUpdate = true;
  });

  WALLPAPERS.forEach((product) => {
    const material = materials.get(product.id);
    if (!material) return;
    material.userData.ensurePbr = () => {
      if (loadedWallpaperMaps.has(product.id)) return;
      const repeat: [number, number] = product.texture_mode === "panel_mural"
        // The living-room feature wall is 4.51 m wide. Add a tiny real-time fit
        // allowance so no edge texel or wrapped sliver is magnified at grazing
        // angles; the production master and installation metadata stay 4.40 m.
        ? [1 / (product.repeat_size_m[0] + 0.12), 1 / (product.repeat_size_m[1] + 0.02)]
        : [1 / product.repeat_size_m[0], 1 / product.repeat_size_m[1]];
      // Repeat wrapping avoids ClampToEdge smearing on oblique mip samples. The
      // mural allowance above keeps the authored image entirely inside 0..1.
      const clamp = false;
      const load = Promise.all([
        textureAsync(loader, `/assets/wallpapers/${product.id}_basecolor_web.jpg`, anisotropy, { color: true, repeat, clamp }),
        textureAsync(loader, `/assets/wallpapers/${product.id}_normal_gl_web.webp`, anisotropy, { repeat, clamp }),
        textureAsync(loader, `/assets/wallpapers/${product.id}_roughness_web.webp`, anisotropy, { repeat, clamp }),
      ]).then(([color, normal, roughness]) => {
        loadedWallpaperMaps.set(product.id, [color, normal, roughness]);
        material.map = color;
        material.normalMap = normal;
        material.normalScale.set(product.normal_scale, product.normal_scale);
        material.roughnessMap = roughness;
        material.roughness = 1;
        material.color.set("#ffffff").multiplyScalar(
          WALLPAPER_APPEARANCE_CALIBRATION.directionalLightShare,
        );
        material.emissive.set("#ffffff").multiplyScalar(
          WALLPAPER_APPEARANCE_CALIBRATION.printedColourShare,
        );
        material.emissiveMap = color;
        material.emissiveIntensity = 1;
        material.envMapIntensity = product.env_map_intensity;
        material.needsUpdate = true;
      }).catch((error) => {
        // A failed wallpaper must not break applyAsset / observation flows.
        console.warn(`Failed to load wallpaper maps for ${product.id}`, error);
      });
      return load;
    };
    // The default west wall starts with linen; all other products remain lazy.
    if (product.id === "wallpaper_linen_natural_01") material.userData.ensurePbr();
  });

  const releaseUnusedWallpaperMaps = (activeAssetIds: Set<string>) => {
    for (const [assetId, maps] of loadedWallpaperMaps) {
      if (activeAssetIds.has(assetId) || assetId === "wallpaper_linen_natural_01") continue;
      maps.forEach((map) => map.dispose());
      loadedWallpaperMaps.delete(assetId);
      const material = materials.get(assetId);
      if (material) {
        material.map = null;
        material.normalMap = null;
        material.roughnessMap = null;
        material.emissiveMap = null;
        material.needsUpdate = true;
      }
    }
  };

  const dispose = () => [
    woodColor,
    woodNormal,
    woodRough,
    paintBase,
    paintNormal,
    paintRoughMatte,
    paintRoughEggshell,
    ...Array.from(loadedSpecialtyPaintMaps.values()).flat(),
    ...Array.from(loadedWallpaperMaps.values()).flat(),
  ].forEach((map) => map.dispose());

  return { ready, dispose, releaseUnusedWallpaperMaps };
}
