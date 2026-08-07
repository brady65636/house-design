import catalogJson from "./paintCatalog.json";

export type PaintToneId = "light" | "mid" | "deep";
export type PaintFinishId = "matte" | "eggshell";

type PaintTone = {
  id: PaintToneId;
  name_zh: string;
  name_en: string;
};

type PaintFinish = {
  id: PaintFinishId;
  name_zh: string;
  name_en: string;
  roughness_mean: number;
  roughness_range: [number, number];
  normal_scale: number;
  env_map_intensity: number;
};

export type PaintFamily = {
  id: string;
  name_zh: string;
  name_en: string;
  description: string;
  colors: Record<PaintToneId, string>;
  id_overrides?: Record<string, string>;
};

export type PaintVariant = {
  id: string;
  familyId: string;
  familyNameZh: string;
  familyNameEn: string;
  tone: PaintToneId;
  toneNameZh: string;
  finish: PaintFinishId;
  finishNameZh: string;
  color: string;
  roughnessMean: number;
  roughnessRange: [number, number];
  normalScale: number;
  envMapIntensity: number;
  nameZh: string;
  nameEn: string;
};

export const PAINT_CATALOG = catalogJson as typeof catalogJson & {
  tones: PaintTone[];
  finishes: PaintFinish[];
  families: PaintFamily[];
};

// A paint picker is a colour-selection tool first.  In the real-time renderer
// the direct sun is therefore only a small part of a paint's final appearance:
// the remaining calibrated albedo term keeps the catalogue's colour standard
// stable when the same paint is applied to walls with different orientations.
export const PAINT_APPEARANCE_CALIBRATION = {
  directLightShare: 0.14,
  colourStandardShare: 0.86,
} as const;

function variantId(family: PaintFamily, tone: PaintToneId, finish: PaintFinishId) {
  const override = family.id_overrides?.[`${tone}_${finish}`];
  return override ?? `paint_${family.id}_${tone}_${finish}_01`;
}

export const PAINT_VARIANTS: PaintVariant[] = PAINT_CATALOG.families.flatMap((family) =>
  PAINT_CATALOG.tones.flatMap((tone) =>
    PAINT_CATALOG.finishes.map((finish) => ({
      id: variantId(family, tone.id, finish.id),
      familyId: family.id,
      familyNameZh: family.name_zh,
      familyNameEn: family.name_en,
      tone: tone.id,
      toneNameZh: tone.name_zh,
      finish: finish.id,
      finishNameZh: finish.name_zh,
      color: family.colors[tone.id],
      roughnessMean: finish.roughness_mean,
      roughnessRange: finish.roughness_range,
      normalScale: finish.normal_scale,
      envMapIntensity: finish.env_map_intensity,
      nameZh: `${family.name_zh} · ${tone.name_zh} · ${finish.name_zh}墙漆`,
      nameEn: `${family.name_en} · ${tone.name_en} · ${finish.name_en} wall paint`,
    })),
  ),
);

export const PAINT_VARIANT_BY_ID = new Map(PAINT_VARIANTS.map((variant) => [variant.id, variant]));

export function findPaintVariant(familyId: string, tone: PaintToneId, finish: PaintFinishId) {
  return PAINT_VARIANTS.find(
    (variant) => variant.familyId === familyId && variant.tone === tone && variant.finish === finish,
  );
}
