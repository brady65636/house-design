import floorCatalog from "./floorCatalog.json";
import tileCatalog from "./tileCatalog.json";
import ceilingCatalog from "./ceilingCatalog.json";

export type SurfaceProduct = {
  order: number;
  id: string;
  name_zh: string;
  name_en: string;
  material_group: string;
  repeat_size_m: [number, number];
  supported_layouts: string[];
  roughness_mean: number;
  normal_scale: number;
  tint: string;
  runtime_color_multiplier?: string;
};

export type CeilingProduct = {
  order: number;
  id: string;
  name_zh: string;
  name_en: string;
  preset: string;
  representation: "geometry_preset";
  drop_height_mm: number;
  perimeter_band_mm?: number;
  cove_width_mm?: number;
  shadow_gap_mm?: number;
  module_size_mm?: [number, number];
  joint_width_mm?: number;
  slat_width_mm?: number;
  slat_gap_mm?: number;
  beam_width_mm?: number;
  grid_module_mm?: number;
  track_width_mm?: number;
  track_offset_mm?: number;
  curve_radius_mm?: number;
  suitable_rooms: string[];
};

export const FLOORS = floorCatalog.products as SurfaceProduct[];
export const TILES = tileCatalog.products as SurfaceProduct[];
export const CEILINGS = ceilingCatalog.products as CeilingProduct[];

export const SURFACE_PRODUCT_BY_ID = new Map(
  [...FLOORS, ...TILES].map((product) => [product.id, product]),
);

export const CEILING_PRODUCT_BY_ID = new Map(
  CEILINGS.map((product) => [product.id, product]),
);

// Glazed or printed tiles still need real specular response, but their selected
// body/print colour must remain recognisable on perpendicular wet-room walls.
// Floor applications keep the regular physically lit material; this split is
// used only by the shared wall variant for tile assets.
export const WALL_TILE_APPEARANCE_CALIBRATION = {
  directionalLightShare: 0.45,
  materialColourShare: 0.55,
} as const;

// Tile floors sit in the same warm-lit rig as tile walls: warm sun, warm HDR
// environment and a warm-grey hemisphere ground all hit horizontal surfaces
// hardest, so a neutral tile (e.g. light microcement) otherwise reads warm
// instead of its catalogue colour — breaking 墙地统一 intents. Anchor a share
// of the floor appearance to the selected tint exactly like the wall variant,
// using the same split so wall and floor tiles read one unified colour family.
export const FLOOR_TILE_APPEARANCE_CALIBRATION = {
  directionalLightShare: 0.45,
  materialColourShare: 0.55,
} as const;
