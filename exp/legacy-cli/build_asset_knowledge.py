"""Convert a full asset manifest into a compact index and detailed card library.

Run once while the source manifest still contains the canonical full assets:
    python scripts/build_asset_knowledge.py
"""

from __future__ import annotations

import json
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from asset_knowledge import build_asset_knowledge  # noqa: E402


SOURCE = ROOT / "asset_manifest.json"
INDEX_PATHS = (
    ROOT / "asset_manifest.json",
    ROOT / "output" / "asset_manifest.json",
    ROOT / "viewer" / "public" / "models" / "asset_manifest.json",
)
CARD_PATHS = (
    ROOT / "asset_cards.json",
    ROOT / "output" / "asset_cards.json",
)


def write_json(path: Path, data: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def main() -> None:
    source = json.loads(SOURCE.read_text(encoding="utf-8"))
    assets = source.get("assets")
    if source.get("schema_version") != "1.0.0" or not isinstance(assets, list):
        raise ValueError("源 asset_manifest.json 必须是尚未压缩的 1.0.0 完整资产清单")

    index, cards = build_asset_knowledge(
        assets,
        generated_at=source.get("generated_at"),
        generator="scripts/build_asset_knowledge.py",
    )
    for path in INDEX_PATHS:
        write_json(path, index)
    for path in CARD_PATHS:
        write_json(path, cards)
    print(f"ASSET_INDEX_COUNT={index['asset_count']}")
    print(f"ASSET_CARD_COUNT={cards['card_count']}")


if __name__ == "__main__":
    main()
