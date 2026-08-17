"""Collapse legacy paint-variant IDs into one parameterized Asset per paint."""

from __future__ import annotations

import json
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
CATALOG = ROOT / "viewer" / "app" / "data" / "paintCatalog.json"


def legacy_map() -> dict[str, tuple[str, dict]]:
    catalog = json.loads(CATALOG.read_text(encoding="utf-8"))
    result: dict[str, tuple[str, dict]] = {}
    for paint in catalog["paints"]:
        for tone in catalog["tones"]:
            for finish in catalog["finishes"]:
                legacy_id = f"paint_{paint['id']}_{tone['id']}_{finish['id']}_01"
                result[legacy_id] = (
                    paint["asset_id"],
                    {"lightness": tone["id"], "saturation": 1.0, "finish": finish["id"]},
                )
        for legacy_id in paint.get("legacy_asset_ids", []):
            if legacy_id == "paint_warm_cream_matte_01":
                result[legacy_id] = (paint["asset_id"], {"lightness": "light", "saturation": 1.0, "finish": "matte"})
            elif legacy_id == "paint_light_greige_eggshell_01":
                result[legacy_id] = (paint["asset_id"], {"lightness": "light", "saturation": 1.0, "finish": "eggshell"})
    return result


def migrate(path: Path) -> tuple[int, int]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    mapping = legacy_map()
    migrated = 0
    parameterized = 0
    for assignment in payload.get("assignments", []):
        legacy = mapping.get(assignment.get("asset_id"))
        if legacy:
            assignment["asset_id"], assignment["parameters"] = legacy
            migrated += 1
        if assignment.get("asset_id", "").startswith("paint_") and assignment.get("parameters"):
            parameterized += 1
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return migrated, parameterized


if __name__ == "__main__":
    targets = [Path(arg).resolve() for arg in sys.argv[1:]] or [ROOT / "viewer" / "public" / "current_scheme.json"]
    for target in targets:
        migrated, parameterized = migrate(target)
        print(f"{target}: migrated={migrated}, parameterized_paints={parameterized}")
