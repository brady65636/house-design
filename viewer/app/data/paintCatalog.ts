import catalogJson from "./paintCatalog.json";

export type PaintToneId = "light" | "mid" | "deep";
export type PaintFinishId = "matte" | "eggshell";

export type PaintParameters = {
  lightness: PaintToneId;
  saturation: number;
  finish: PaintFinishId;
};

type PaintTone = { id: PaintToneId; name_zh: string; name_en: string };
type PaintFinish = {
  id: PaintFinishId;
  name_zh: string;
  name_en: string;
  roughness_mean: number;
  roughness_range: [number, number];
  normal_scale: number;
  env_map_intensity: number;
};

export type PaintProduct = {
  id: string;
  asset_id: string;
  name_zh: string;
  name_en: string;
  description: string;
  colors: Record<PaintToneId, string>;
  legacy_asset_ids?: string[];
};

export type SpecialtyPaintProduct = {
  order: number;
  id: string;
  slug: string;
  coating_system: "limewash" | "clay_plaster" | "marmorino";
  name_zh: string;
  name_en: string;
  description: string;
  color_srgb: string;
  finish: string;
  physical_size_m: [number, number];
  roughness_mean: number;
  roughness_range: [number, number];
  normal_scale: number;
  env_map_intensity: number;
  texture_set_id: string;
  source_type: string;
  supported_rooms: string[];
};

export type PaintAsset = {
  id: string;
  color: string;
  roughnessMean: number;
  roughnessRange: [number, number];
  normalScale: number;
  envMapIntensity: number;
  nameZh: string;
  nameEn: string;
  coatingSystem: "solid_paint" | SpecialtyPaintProduct["coating_system"];
  isSpecialty: boolean;
  physicalSizeM: [number, number];
  texturePrefix?: string;
  description?: string;
  parameters?: PaintParameters;
};

export const PAINT_CATALOG = catalogJson as typeof catalogJson & {
  tones: PaintTone[];
  finishes: PaintFinish[];
  paints: PaintProduct[];
  specialty_products: SpecialtyPaintProduct[];
};

export const DEFAULT_PAINT_PARAMETERS: PaintParameters = {
  lightness: "light",
  saturation: 1,
  finish: "matte",
};

export const PAINT_APPEARANCE_CALIBRATION = {
  directLightShare: 0.14,
  colourStandardShare: 0.86,
} as const;

function finishById(id: PaintFinishId) {
  return PAINT_CATALOG.finishes.find((finish) => finish.id === id)!;
}

export function applySaturation(hex: string, factor: number) {
  const channels = [1, 3, 5].map((offset) => Number.parseInt(hex.slice(offset, offset + 2), 16));
  const luminance = channels[0] * 0.2126 + channels[1] * 0.7152 + channels[2] * 0.0722;
  const adjusted = channels.map((channel) => Math.max(0, Math.min(255, Math.round(luminance + (channel - luminance) * factor))));
  return `#${adjusted.map((channel) => channel.toString(16).padStart(2, "0")).join("").toUpperCase()}`;
}

const STANDARD_PAINTS: PaintAsset[] = PAINT_CATALOG.paints.map((paint) => {
  const finish = finishById(DEFAULT_PAINT_PARAMETERS.finish);
  return {
    id: paint.asset_id,
    color: paint.colors[DEFAULT_PAINT_PARAMETERS.lightness],
    roughnessMean: finish.roughness_mean,
    roughnessRange: finish.roughness_range,
    normalScale: finish.normal_scale,
    envMapIntensity: finish.env_map_intensity,
    nameZh: `${paint.name_zh}墙漆`,
    nameEn: `${paint.name_en} wall paint`,
    coatingSystem: "solid_paint" as const,
    isSpecialty: false,
    physicalSizeM: PAINT_CATALOG.texture_set.physical_size_m as [number, number],
    description: paint.description,
    parameters: { ...DEFAULT_PAINT_PARAMETERS },
  };
});

export const SPECIALTY_PAINTS: PaintAsset[] = PAINT_CATALOG.specialty_products.map((product) => ({
  id: product.id,
  color: product.color_srgb,
  roughnessMean: product.roughness_mean,
  roughnessRange: product.roughness_range,
  normalScale: product.normal_scale,
  envMapIntensity: product.env_map_intensity,
  nameZh: product.name_zh,
  nameEn: product.name_en,
  coatingSystem: product.coating_system,
  isSpecialty: true,
  physicalSizeM: product.physical_size_m,
  texturePrefix: product.id,
  description: product.description,
}));

export const PAINT_ASSETS: PaintAsset[] = [...STANDARD_PAINTS, ...SPECIALTY_PAINTS];
// Compatibility name for renderer modules; this is now 13 Assets, not 63 variants.
export const PAINT_VARIANTS = PAINT_ASSETS;
export const PAINT_ASSET_BY_ID = new Map(PAINT_ASSETS.map((asset) => [asset.id, asset]));
export const PAINT_VARIANT_BY_ID = PAINT_ASSET_BY_ID;

export function resolvePaintSelection(paintAssetId: string, parameters: PaintParameters) {
  const paint = PAINT_CATALOG.paints.find((item) => item.asset_id === paintAssetId);
  if (!paint) return undefined;
  const finish = finishById(parameters.finish);
  const asset = PAINT_ASSET_BY_ID.get(paint.asset_id)!;
  return {
    ...asset,
    color: applySaturation(paint.colors[parameters.lightness], parameters.saturation),
    roughnessMean: finish.roughness_mean,
    roughnessRange: finish.roughness_range,
    normalScale: finish.normal_scale,
    envMapIntensity: finish.env_map_intensity,
    parameters,
  };
}

export function findPaintVariant(paintAssetId: string, lightness: PaintToneId, finish: PaintFinishId, saturation = 1) {
  return resolvePaintSelection(paintAssetId, { lightness, saturation, finish });
}
