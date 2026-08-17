/** 与 Python schema.py 对齐的 Scheme 前端类型 */

export type TargetKind = "wall_face" | "surface";

export type Target = {
  kind: TargetKind;
  id: string;
};

export type Assignment = {
  target: Target;
  asset_id: string;
  parameters?: {
    lightness: "light" | "mid" | "deep";
    saturation: number;
    finish: "matte" | "eggshell";
  } | null;
};

export type Scheme = {
  schema_version: "1.0.0";
  scheme_id: string;
  title: string;
  assignments: Assignment[];
};
