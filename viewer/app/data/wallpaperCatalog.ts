import catalogJson from "./wallpaperCatalog.json";

export type WallpaperMatchType = "random_match" | "straight_match" | "half_drop_match" | "panel_mural";
export type WallpaperTextureMode = "repeat" | "panel_mural";

export type WallpaperProduct = {
  id: string;
  order: number;
  slug: string;
  name_zh: string;
  name_en: string;
  description_zh: string;
  recommended_use: string[];
  texture_mode: WallpaperTextureMode;
  roll_width_m?: number;
  panel_width_m?: number;
  panel_count?: number;
  repeat_size_m: [number, number];
  match_type: WallpaperMatchType;
  source_file: string;
  output_resolution: [number, number];
  master_resolution?: [number, number];
  surface_profile: string;
  roughness_mean: number;
  normal_scale: number;
  height_strength: number;
  env_map_intensity: number;
  sheen: number;
  tint: string;
};

export const WALLPAPER_CATALOG = catalogJson as typeof catalogJson & {
  reference_wall_size_m: [number, number];
  products: WallpaperProduct[];
};

export const WALLPAPERS = WALLPAPER_CATALOG.products;
export const WALLPAPER_BY_ID = new Map(WALLPAPERS.map((product) => [product.id, product]));

// Wallpaper is a printed colour-selection surface, so its artwork must not
// turn into a different colourway merely because the wall normal faces toward
// or away from the room's directional sun. Keep enough physically-lit response
// to read corners and surface relief, while anchoring most of the base-colour
// map to the same display standard on every wall orientation.
export const WALLPAPER_APPEARANCE_CALIBRATION = {
  directionalLightShare: 0.22,
  printedColourShare: 0.78,
} as const;
