import floorCatalog from "./floorCatalog.json";
import tileCatalog from "./tileCatalog.json";
import ceilingCatalog from "./ceilingCatalog.json";

export type SurfaceProduct = {
  order: number;
  id: string;
  name_zh: string;
  name_en: string;
  family: string;
  repeat_size_m: [number, number];
  supported_layouts: string[];
  roughness_mean: number;
  normal_scale: number;
  tint: string;
};

export type CeilingProduct = {
  order: number;
  id: string;
  name_zh: string;
  name_en: string;
  family: string;
  representation: "geometry_preset";
  drop_height_mm: number;
  perimeter_band_mm?: number;
  cove_width_mm?: number;
  shadow_gap_mm?: number;
  module_size_mm?: [number, number];
  joint_width_mm?: number;
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
