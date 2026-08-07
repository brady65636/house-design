import * as THREE from "three";
import { RoundedBoxGeometry } from "three/examples/jsm/geometries/RoundedBoxGeometry.js";

export type CameraPreset = {
  id: string;
  roomId: string;
  roomLabel: string;
  shotLabel: string;
  position: [number, number, number];
  target: [number, number, number];
  fov: number;
  orbitRadius: [number, number];
  overview?: boolean;
};

export const CAMERA_PRESETS: CameraPreset[] = [
  {
    id: "overview",
    roomId: "overview",
    roomLabel: "全屋",
    shotLabel: "导航",
    position: [14.8, -11.5, 14.2],
    target: [5.3, 4.1, 0.65],
    fov: 38,
    orbitRadius: [7, 28],
    overview: true,
  },
  {
    id: "living_hero",
    roomId: "living_room",
    roomLabel: "客厅",
    shotLabel: "主镜头",
    position: [5.82, 4.25, 1.52],
    target: [1.82, 2.34, 0.92],
    fov: 44,
    orbitRadius: [2.5, 6.2],
  },
  {
    id: "living_reverse",
    roomId: "living_room",
    roomLabel: "客厅",
    shotLabel: "反向",
    position: [3.88, 0.92, 1.44],
    target: [1.08, 2.62, 0.92],
    fov: 43,
    orbitRadius: [2.8, 6.5],
  },
  {
    id: "living_detail",
    roomId: "living_room",
    roomLabel: "客厅",
    shotLabel: "材质细节",
    position: [3.85, 4.12, 1.10],
    target: [2.00, 2.45, 0.52],
    fov: 40,
    orbitRadius: [1.1, 3.2],
  },
  {
    id: "dining_hero",
    roomId: "dining_room",
    roomLabel: "餐厅",
    shotLabel: "主镜头",
    position: [5.95, 0.65, 1.55],
    target: [4.35, 3.2, 1.15],
    fov: 48,
    orbitRadius: [2.0, 4.8],
  },
  {
    id: "master_hero",
    roomId: "master_bedroom",
    roomLabel: "主卧",
    shotLabel: "主镜头",
    position: [3.45, 4.95, 1.5],
    target: [1.45, 7.25, 1.1],
    fov: 48,
    orbitRadius: [2.0, 4.6],
  },
  {
    id: "master_detail",
    roomId: "master_bedroom",
    roomLabel: "主卧",
    shotLabel: "床头细节",
    position: [0.75, 5.25, 1.25],
    target: [1.9, 7.65, 1.05],
    fov: 43,
    orbitRadius: [1.4, 3.5],
  },
  {
    id: "bedroom_2_hero",
    roomId: "bedroom_2",
    roomLabel: "次卧",
    shotLabel: "主镜头",
    position: [5.65, 4.95, 1.5],
    target: [4.65, 7.15, 1.1],
    fov: 50,
    orbitRadius: [1.8, 4.2],
  },
  {
    id: "kitchen_hero",
    roomId: "kitchen",
    roomLabel: "厨房",
    shotLabel: "主镜头",
    position: [7.15, 2.45, 1.52],
    target: [9.7, 0.8, 1.15],
    fov: 52,
    orbitRadius: [1.8, 4.4],
  },
  {
    id: "bathroom_hero",
    roomId: "bathroom",
    roomLabel: "卫生间",
    shotLabel: "门口镜头",
    position: [7.1, 5.05, 1.47],
    target: [8.3, 7.3, 1.05],
    fov: 55,
    orbitRadius: [1.2, 3.8],
  },
  {
    id: "foyer_hero",
    roomId: "foyer_corridor",
    roomLabel: "玄关",
    shotLabel: "归家视角",
    position: [10.15, 3.55, 1.55],
    target: [6.9, 3.55, 1.15],
    fov: 48,
    orbitRadius: [2.0, 4.8],
  },
  {
    id: "utility_hero",
    roomId: "utility_balcony",
    roomLabel: "生活阳台",
    shotLabel: "门口镜头",
    position: [9.35, 5.05, 1.45],
    target: [10.15, 7.45, 1.05],
    fov: 54,
    orbitRadius: [1.2, 3.5],
  },
];

export const ROOM_NAV = [
  { roomId: "living_room", label: "客厅", presetId: "living_hero" },
  { roomId: "dining_room", label: "餐厅", presetId: "dining_hero" },
  { roomId: "master_bedroom", label: "主卧", presetId: "master_hero" },
  { roomId: "bedroom_2", label: "次卧", presetId: "bedroom_2_hero" },
  { roomId: "kitchen", label: "厨房", presetId: "kitchen_hero" },
  { roomId: "bathroom", label: "卫生间", presetId: "bathroom_hero" },
  { roomId: "foyer_corridor", label: "玄关", presetId: "foyer_hero" },
  { roomId: "utility_balcony", label: "生活阳台", presetId: "utility_hero" },
];

export function blenderPoint(point: [number, number, number]) {
  return new THREE.Vector3(point[0], point[2], -point[1]);
}

type InteriorMaterials = ReturnType<typeof makeMaterials>;

function makeMaterials() {
  return {
    textile: new THREE.MeshStandardMaterial({ color: "#bdb4a5", roughness: 0.96 }),
    textileLight: new THREE.MeshStandardMaterial({ color: "#e5ddd0", roughness: 0.94 }),
    textileDark: new THREE.MeshStandardMaterial({ color: "#59645e", roughness: 0.92 }),
    oak: new THREE.MeshStandardMaterial({ color: "#a86f3c", roughness: 0.7 }),
    oakLight: new THREE.MeshStandardMaterial({ color: "#c99e68", roughness: 0.72 }),
    darkWood: new THREE.MeshStandardMaterial({ color: "#372a22", roughness: 0.62 }),
    stone: new THREE.MeshStandardMaterial({ color: "#c9c0b1", roughness: 0.48 }),
    ceramic: new THREE.MeshStandardMaterial({ color: "#e7e6e1", roughness: 0.38 }),
    metal: new THREE.MeshStandardMaterial({ color: "#b38a52", roughness: 0.34, metalness: 0.72 }),
    black: new THREE.MeshStandardMaterial({ color: "#1f2422", roughness: 0.42 }),
    mirror: new THREE.MeshStandardMaterial({ color: "#9bb0b1", roughness: 0.08, metalness: 0.52 }),
    glass: new THREE.MeshPhysicalMaterial({
      color: "#c9e4e5",
      roughness: 0.08,
      transmission: 0.72,
      transparent: true,
      opacity: 0.42,
      side: THREE.DoubleSide,
    }),
    leaf: new THREE.MeshStandardMaterial({ color: "#526b54", roughness: 0.86 }),
    terracotta: new THREE.MeshStandardMaterial({ color: "#8d5c3e", roughness: 0.88 }),
    rug: new THREE.MeshStandardMaterial({ color: "#887f70", roughness: 1 }),
  };
}

function addRoundedBox(
  group: THREE.Group,
  name: string,
  size: [number, number, number],
  position: [number, number, number],
  material: THREE.Material,
  radius = 0.04,
  rotationZ = 0,
) {
  const geometry = new RoundedBoxGeometry(size[0], size[2], size[1], 3, radius);
  const mesh = new THREE.Mesh(geometry, material);
  mesh.name = name;
  mesh.position.copy(blenderPoint(position));
  mesh.rotation.y = -rotationZ;
  mesh.castShadow = true;
  mesh.receiveShadow = true;
  mesh.userData.reference_detail = true;
  group.add(mesh);
  return mesh;
}

function addCylinder(
  group: THREE.Group,
  name: string,
  radius: number,
  height: number,
  position: [number, number, number],
  material: THREE.Material,
  segments = 24,
) {
  const mesh = new THREE.Mesh(new THREE.CylinderGeometry(radius, radius, height, segments), material);
  mesh.name = name;
  mesh.position.copy(blenderPoint(position));
  mesh.castShadow = true;
  mesh.receiveShadow = true;
  mesh.userData.reference_detail = true;
  group.add(mesh);
  return mesh;
}

function addSphere(
  group: THREE.Group,
  name: string,
  radius: number,
  position: [number, number, number],
  material: THREE.Material,
) {
  const mesh = new THREE.Mesh(new THREE.SphereGeometry(radius, 24, 16), material);
  mesh.name = name;
  mesh.position.copy(blenderPoint(position));
  mesh.castShadow = true;
  mesh.userData.reference_detail = true;
  group.add(mesh);
  return mesh;
}

function addChair(
  group: THREE.Group,
  prefix: string,
  x: number,
  y: number,
  rotation: number,
  materials: InteriorMaterials,
) {
  addRoundedBox(group, `${prefix}_seat`, [0.46, 0.46, 0.10], [x, y, 0.48], materials.oak, 0.035, rotation);
  const backOffsetX = Math.sin(rotation) * 0.19;
  const backOffsetY = Math.cos(rotation) * 0.19;
  addRoundedBox(group, `${prefix}_back`, [0.44, 0.09, 0.55], [x - backOffsetX, y - backOffsetY, 0.77], materials.textileDark, 0.035, rotation);
  [[-0.17, -0.17], [0.17, -0.17], [-0.17, 0.17], [0.17, 0.17]].forEach(([dx, dy], index) => {
    addCylinder(group, `${prefix}_leg_${index}`, 0.022, 0.43, [x + dx, y + dy, 0.215], materials.black, 12);
  });
}

function addBed(
  group: THREE.Group,
  prefix: string,
  center: [number, number],
  width: number,
  length: number,
  materials: InteriorMaterials,
) {
  const [x, y] = center;
  addRoundedBox(group, `${prefix}_base`, [width, length, 0.28], [x, y, 0.22], materials.darkWood, 0.06);
  addRoundedBox(group, `${prefix}_mattress`, [width - 0.08, length - 0.12, 0.25], [x, y - 0.02, 0.48], materials.textileLight, 0.10);
  addRoundedBox(group, `${prefix}_headboard`, [width + 0.18, 0.15, 1.05], [x, y + length / 2 - 0.05, 0.77], materials.textileDark, 0.08);
  addRoundedBox(group, `${prefix}_duvet`, [width - 0.16, length * 0.58, 0.10], [x, y - length * 0.12, 0.66], materials.textile, 0.06);
  addRoundedBox(group, `${prefix}_pillow_left`, [width * 0.38, 0.40, 0.13], [x - width * 0.22, y + length * 0.27, 0.69], materials.textileLight, 0.09);
  addRoundedBox(group, `${prefix}_pillow_right`, [width * 0.38, 0.40, 0.13], [x + width * 0.22, y + length * 0.27, 0.69], materials.textileLight, 0.09);
}

function addWarmLight(group: THREE.Group, name: string, position: [number, number, number], intensity = 14) {
  const light = new THREE.PointLight("#ffd7a0", intensity, 5.5, 2);
  light.name = name;
  light.position.copy(blenderPoint(position));
  light.castShadow = false;
  group.add(light);
}

export function buildInteriorDetails() {
  const root = new THREE.Group();
  root.name = "NEUTRAL_INTERIOR_REFERENCES";
  const materials = makeMaterials();

  const living = new THREE.Group();
  living.name = "DETAIL_living_room";
  living.userData.room_id = "living_room";
  living.visible = false;
  root.add(living);
  addRoundedBox(living, "living_rug", [2.55, 2.25, 0.025], [2.15, 2.48, 0.035], materials.rug, 0.06);
  addRoundedBox(living, "sofa_base", [0.88, 2.55, 0.38], [0.72, 2.48, 0.33], materials.textileDark, 0.10);
  addRoundedBox(living, "sofa_back", [0.20, 2.55, 0.78], [0.39, 2.48, 0.78], materials.textileDark, 0.08);
  addRoundedBox(living, "sofa_seat", [0.62, 2.28, 0.18], [0.82, 2.48, 0.55], materials.textile, 0.08);
  addRoundedBox(living, "sofa_cushion_1", [0.18, 0.58, 0.55], [0.54, 1.8, 0.87], materials.textileLight, 0.08);
  addRoundedBox(living, "sofa_cushion_2", [0.18, 0.58, 0.55], [0.54, 2.48, 0.87], materials.textile, 0.08);
  addRoundedBox(living, "sofa_cushion_3", [0.18, 0.58, 0.55], [0.54, 3.16, 0.87], materials.textileLight, 0.08);
  addRoundedBox(living, "coffee_table_top", [1.15, 0.62, 0.08], [2.18, 2.45, 0.42], materials.stone, 0.08);
  addCylinder(living, "coffee_table_leg_1", 0.045, 0.39, [1.78, 2.25, 0.215], materials.metal, 16);
  addCylinder(living, "coffee_table_leg_2", 0.045, 0.39, [2.58, 2.65, 0.215], materials.metal, 16);
  addRoundedBox(living, "tv_console", [0.42, 2.0, 0.42], [3.73, 2.52, 0.30], materials.darkWood, 0.04);
  addCylinder(living, "floor_lamp_stem", 0.025, 1.45, [1.2, 4.0, 0.75], materials.metal, 16);
  addSphere(living, "floor_lamp_globe", 0.19, [1.2, 4.0, 1.52], materials.ceramic);
  addCylinder(living, "plant_pot", 0.22, 0.38, [3.5, 0.65, 0.20], materials.terracotta);
  for (let index = 0; index < 7; index += 1) {
    const angle = (index / 7) * Math.PI * 2;
    const leaf = addRoundedBox(living, `plant_leaf_${index}`, [0.13, 0.50, 0.08], [3.5 + Math.cos(angle) * 0.12, 0.65 + Math.sin(angle) * 0.12, 0.68 + (index % 3) * 0.09], materials.leaf, 0.06, angle);
    leaf.rotation.z = Math.cos(angle) * 0.35;
  }
  addWarmLight(living, "living_warm_light", [2.2, 2.4, 2.35], 17);

  const dining = new THREE.Group();
  dining.name = "DETAIL_dining_room";
  dining.userData.room_id = "dining_room";
  root.add(dining);
  addRoundedBox(dining, "dining_table_top", [1.65, 0.88, 0.09], [5.18, 2.35, 0.77], materials.oak, 0.05);
  [[-0.62, -0.28], [0.62, -0.28], [-0.62, 0.28], [0.62, 0.28]].forEach(([dx, dy], index) => {
    addCylinder(dining, `dining_table_leg_${index}`, 0.035, 0.72, [5.18 + dx, 2.35 + dy, 0.36], materials.black, 12);
  });
  addChair(dining, "chair_north_1", 4.72, 3.05, 0, materials);
  addChair(dining, "chair_north_2", 5.62, 3.05, 0, materials);
  addChair(dining, "chair_south_1", 4.72, 1.65, Math.PI, materials);
  addChair(dining, "chair_south_2", 5.62, 1.65, Math.PI, materials);
  addCylinder(dining, "pendant_stem", 0.015, 0.75, [5.18, 2.35, 2.38], materials.black, 12);
  addCylinder(dining, "pendant_shade", 0.23, 0.18, [5.18, 2.35, 1.97], materials.metal, 32);
  addWarmLight(dining, "dining_warm_light", [5.18, 2.35, 1.78], 12);

  const master = new THREE.Group();
  master.name = "DETAIL_master_bedroom";
  master.userData.room_id = "master_bedroom";
  root.add(master);
  addRoundedBox(master, "master_rug", [2.35, 2.50, 0.025], [1.85, 6.95, 0.03], materials.rug, 0.05);
  addBed(master, "master_bed", [1.85, 6.95], 1.72, 2.02, materials);
  addRoundedBox(master, "master_nightstand_left", [0.46, 0.42, 0.44], [0.62, 7.58, 0.24], materials.oak, 0.04);
  addRoundedBox(master, "master_nightstand_right", [0.46, 0.42, 0.44], [3.08, 7.58, 0.24], materials.oak, 0.04);
  addSphere(master, "master_lamp_left", 0.13, [0.62, 7.58, 0.72], materials.ceramic);
  addSphere(master, "master_lamp_right", 0.13, [3.08, 7.58, 0.72], materials.ceramic);
  addRoundedBox(master, "master_wardrobe", [0.58, 2.15, 2.32], [0.58, 5.85, 1.16], materials.oakLight, 0.035);
  addWarmLight(master, "master_warm_light", [1.85, 6.65, 2.28], 12);

  const bedroom2 = new THREE.Group();
  bedroom2.name = "DETAIL_bedroom_2";
  bedroom2.userData.room_id = "bedroom_2";
  root.add(bedroom2);
  addBed(bedroom2, "bedroom2_bed", [4.75, 7.05], 1.34, 1.95, materials);
  addRoundedBox(bedroom2, "bedroom2_desk", [1.10, 0.52, 0.08], [5.92, 7.4, 0.76], materials.oakLight, 0.035);
  addRoundedBox(bedroom2, "bedroom2_desk_drawer", [0.36, 0.48, 0.65], [6.22, 7.4, 0.36], materials.oakLight, 0.03);
  addChair(bedroom2, "bedroom2_chair", 5.72, 6.72, 0, materials);
  addRoundedBox(bedroom2, "bedroom2_wardrobe", [0.56, 1.25, 2.25], [6.23, 5.55, 1.13], materials.oak, 0.035);
  addWarmLight(bedroom2, "bedroom2_warm_light", [5.1, 6.6, 2.3], 10);

  const kitchen = new THREE.Group();
  kitchen.name = "DETAIL_kitchen";
  kitchen.userData.room_id = "kitchen";
  root.add(kitchen);
  addRoundedBox(kitchen, "kitchen_lower_cabinets", [3.2, 0.58, 0.82], [8.92, 0.57, 0.43], materials.oakLight, 0.025);
  addRoundedBox(kitchen, "kitchen_countertop", [3.28, 0.64, 0.08], [8.92, 0.57, 0.88], materials.stone, 0.025);
  addRoundedBox(kitchen, "kitchen_upper_left", [1.08, 0.36, 0.76], [7.75, 0.40, 1.72], materials.textileLight, 0.02);
  addRoundedBox(kitchen, "kitchen_upper_right", [1.08, 0.36, 0.76], [10.08, 0.40, 1.72], materials.textileLight, 0.02);
  addRoundedBox(kitchen, "kitchen_hood", [0.76, 0.42, 0.50], [8.92, 0.42, 1.82], materials.black, 0.02);
  addRoundedBox(kitchen, "kitchen_island", [1.45, 0.68, 0.86], [8.65, 1.83, 0.44], materials.darkWood, 0.04);
  addRoundedBox(kitchen, "kitchen_island_top", [1.55, 0.76, 0.07], [8.65, 1.83, 0.90], materials.stone, 0.03);
  addCylinder(kitchen, "kitchen_faucet", 0.025, 0.36, [9.8, 0.60, 1.09], materials.metal, 16);
  addWarmLight(kitchen, "kitchen_warm_light", [8.85, 1.55, 2.25], 15);

  const bathroom = new THREE.Group();
  bathroom.name = "DETAIL_bathroom";
  bathroom.userData.room_id = "bathroom";
  root.add(bathroom);
  addRoundedBox(bathroom, "bath_vanity", [1.02, 0.50, 0.72], [7.35, 7.73, 0.39], materials.oak, 0.04);
  addRoundedBox(bathroom, "bath_sink", [0.68, 0.42, 0.15], [7.35, 7.68, 0.82], materials.ceramic, 0.07);
  addRoundedBox(bathroom, "bath_mirror", [0.90, 0.04, 0.86], [7.35, 8.12, 1.47], materials.mirror, 0.03);
  addRoundedBox(bathroom, "toilet_base", [0.42, 0.67, 0.42], [8.28, 7.35, 0.24], materials.ceramic, 0.13);
  addRoundedBox(bathroom, "toilet_tank", [0.42, 0.19, 0.62], [8.28, 7.64, 0.54], materials.ceramic, 0.07);
  addRoundedBox(bathroom, "shower_tray", [1.02, 1.18, 0.08], [8.24, 5.45, 0.05], materials.stone, 0.03);
  addRoundedBox(bathroom, "shower_glass", [0.04, 1.12, 1.82], [7.76, 5.45, 0.95], materials.glass, 0.015);
  addCylinder(bathroom, "shower_pipe", 0.018, 1.32, [8.72, 5.75, 1.45], materials.metal, 12);
  addWarmLight(bathroom, "bath_warm_light", [7.45, 7.35, 2.2], 14);

  const foyer = new THREE.Group();
  foyer.name = "DETAIL_foyer_corridor";
  foyer.userData.room_id = "foyer_corridor";
  root.add(foyer);
  addRoundedBox(foyer, "foyer_console", [0.38, 1.36, 0.72], [10.25, 3.82, 0.38], materials.darkWood, 0.035);
  addRoundedBox(foyer, "foyer_mirror", [0.04, 0.92, 1.12], [10.48, 3.82, 1.48], materials.mirror, 0.025);
  addRoundedBox(foyer, "foyer_bench", [1.05, 0.42, 0.42], [8.45, 3.95, 0.23], materials.textileDark, 0.06);
  addRoundedBox(foyer, "foyer_runner", [2.70, 0.78, 0.025], [8.72, 3.52, 0.03], materials.rug, 0.04);
  addWarmLight(foyer, "foyer_warm_light", [8.8, 3.55, 2.28], 11);

  const utility = new THREE.Group();
  utility.name = "DETAIL_utility_balcony";
  utility.userData.room_id = "utility_balcony";
  root.add(utility);
  addRoundedBox(utility, "utility_washer", [0.64, 0.66, 0.86], [9.48, 7.62, 0.45], materials.ceramic, 0.055);
  addCylinder(utility, "utility_washer_door", 0.22, 0.035, [9.48, 7.27, 0.47], materials.black, 32).rotation.x = Math.PI / 2;
  addRoundedBox(utility, "utility_cabinet", [0.62, 0.58, 2.18], [10.18, 7.65, 1.09], materials.oakLight, 0.035);
  addRoundedBox(utility, "utility_counter", [1.35, 0.66, 0.07], [9.83, 7.62, 0.92], materials.stone, 0.025);
  addWarmLight(utility, "utility_warm_light", [9.82, 6.55, 2.25], 9);

  return { root, materials };
}
