"""Activate the generated v4 house manifest for the Agent and viewer.

This is a deterministic data migration.  It does not change the Scheme schema
or backend logic; it synchronizes the current house JSON and rebuilds the
default Scheme so every designable target in the new house can be updated.
"""

from __future__ import annotations

import json
import hashlib
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SOURCE_MANIFEST = ROOT / "output" / "scene_manifest_spacious_v4.json"
SOURCE_GLB = ROOT / "output" / "house_spacious_yunkuo_135_v4.glb"
VIEWER_GLB = ROOT / "viewer" / "public" / "models" / "house_spacious_yunkuo_135_v4.glb"
ACTIVE_MANIFEST_PATHS = (
    ROOT / "scene_manifest.json",
    ROOT / "output" / "scene_manifest.json",
    ROOT / "viewer" / "public" / "models" / "scene_manifest.json",
    ROOT / "viewer" / "public" / "models" / "scene_manifest_spacious_v4.json",
)
CURRENT_SCHEME = ROOT / "viewer" / "public" / "current_scheme.json"
LEGACY_SCHEME = ROOT / "viewer" / "public" / "current_scheme_legacy_90_v1.json"
OUTPUT_DEFAULT_SCHEME = ROOT / "output" / "current_scheme_spacious_v4.json"
EXPECTED_HOUSE_ID = "house_spacious_yunkuo_135_v4"


def write_json(path: Path, data: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(data, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )


def main() -> None:
    manifest_text = SOURCE_MANIFEST.read_text(encoding="utf-8")
    manifest = json.loads(manifest_text)
    if manifest.get("house_id") != EXPECTED_HOUSE_ID:
        raise ValueError(f"意外的 house_id：{manifest.get('house_id')}")

    targets = manifest.get("design_targets", [])
    target_keys = [(target.get("kind"), target.get("id")) for target in targets]
    if len(targets) != 55 or len(target_keys) != len(set(target_keys)):
        raise ValueError(
            f"v4 设计目标应为 55 个且不能重复，实际为 {len(targets)} 个"
        )

    if CURRENT_SCHEME.exists() and not LEGACY_SCHEME.exists():
        LEGACY_SCHEME.write_text(
            CURRENT_SCHEME.read_text(encoding="utf-8"),
            encoding="utf-8",
        )

    scheme = {
        "schema_version": "1.0.0",
        "scheme_id": "scheme_yunkuo_135_v4_default_01",
        "title": "云阔 135㎡ · 基础方案",
        "assignments": [
            {
                "target": {"kind": target["kind"], "id": target["id"]},
                "asset_id": target["default_asset_id"],
            }
            for target in targets
        ],
    }

    for path in ACTIVE_MANIFEST_PATHS:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(manifest_text, encoding="utf-8")
    VIEWER_GLB.parent.mkdir(parents=True, exist_ok=True)
    model_bytes = SOURCE_GLB.read_bytes()
    VIEWER_GLB.write_bytes(model_bytes)
    write_json(CURRENT_SCHEME, scheme)
    write_json(OUTPUT_DEFAULT_SCHEME, scheme)

    print("ACTIVE_HOUSE_JSON_SYNC_COMPLETE")
    print(f"HOUSE_ID={manifest['house_id']}")
    print(f"ROOMS={len(manifest['rooms'])}")
    print(f"WALL_FACES={len(manifest['wall_faces'])}")
    print(f"DESIGN_TARGETS={len(targets)}")
    print(f"SCHEME_ASSIGNMENTS={len(scheme['assignments'])}")
    print(f"GLB_SHA256={hashlib.sha256(model_bytes).hexdigest()}")


if __name__ == "__main__":
    main()
