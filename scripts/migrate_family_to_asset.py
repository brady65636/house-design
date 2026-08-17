"""取消 family 概念：把双层索引（families[] + assets[]）降级为单一 asset 层。

背景：asset_manifest.json 的 families[] 只是 asset_knowledge.build_asset_knowledge()
按 (category, family_id) 对已含全部富字段的 asset 卡片做的投影层。本脚本：

1. asset_manifest.json：删除 families[]/family_count；assets[] 逐项用同名卡片
   内联富字段（name_zh/name_en/brief/design_roles/relationship_tags/
   visual_description/works_well_with/avoid_when + 墙漆 parameterized/parameter_schema）。
2. asset_cards.json：每张卡删除顶层 family_id、objective_facts 里的
   family/family_id/perceptual_group_id；style_roles 统一改名 design_roles；
   "综合色 Family 为单一 Asset" 文案改 "综合色 Asset"。
3. asset_family_filter_profiles.json -> asset_filter_profiles.json：family_overrides
   按旧 manifest 的 variant_ids 展开为 asset_overrides（按 asset_id 作键，
   多 variant family 的覆盖被各 variant asset 共享）。

幂等：asset_family_filter_profiles.json 不存在时视为已迁移，直接退出。
"""

from __future__ import annotations

import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]

MANIFEST = ROOT / "asset_manifest.json"
CARDS = ROOT / "asset_cards.json"
OLD_PROFILES = ROOT / "asset_family_filter_profiles.json"
NEW_PROFILES = ROOT / "asset_filter_profiles.json"

MANIFEST_COPIES = [
    ROOT / "output" / "asset_manifest.json",
    ROOT / "viewer" / "public" / "models" / "asset_manifest.json",
    ROOT / "viewer" / "dist" / "client" / "models" / "asset_manifest.json",
]
CARDS_COPIES = [
    ROOT / "output" / "asset_cards.json",
]

FAMILY_PROSE = "综合色 Family 为单一 Asset"
ASSET_PROSE = "综合色 Asset"

FAMILY_KEYS_IN_FACTS = ("family", "family_id", "perceptual_group_id")


def load(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def dump(path: Path, payload: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def enrich_manifest(manifest: dict, cards: dict) -> dict:
    cards_by_id = cards["cards"]

    # 多 variant family：旧模型里 family 承载的是组内第一张卡的富字段；降级后这些
    # 知识必须完整保留在每个成员 asset 上，否则成员若卡片是占位描述就会信息损失。
    family_rich: dict[str, dict] = {}
    for family in manifest.get("families", []):
        if not isinstance(family, dict):
            continue
        variants = family.get("variant_ids") or []
        if len(variants) > 1:
            first = cards_by_id.get(variants[0])
            if isinstance(first, dict):
                family_rich[family["id"]] = {
                    "visual_description": first.get("visual_description"),
                    "works_well_with": first.get("works_well_with", []),
                    "avoid_when": first.get("avoid_when"),
                }
    asset_rich: dict[str, dict] = {}
    for family in manifest.get("families", []):
        if not isinstance(family, dict):
            continue
        variants = family.get("variant_ids") or []
        rich = family_rich.get(family["id"])
        if rich and len(variants) > 1:
            for variant in variants:
                asset_rich[variant] = rich

    new_assets: list[dict] = []
    for asset in manifest["assets"]:
        card = cards_by_id.get(asset["id"])
        if not isinstance(card, dict):
            raise SystemExit(f"manifest asset {asset['id']!r} 没有对应卡片")
        rich = asset_rich.get(asset["id"])
        if rich:
            # 多 variant 成员：视觉描述/适配/禁忌继承 family 级知识，名称与 brief 保留自身。
            visual_description = rich["visual_description"]
            works_well_with = rich["works_well_with"]
            avoid_when = rich["avoid_when"]
        else:
            visual_description = card["visual_description"]
            works_well_with = card.get("works_well_with", [])
            avoid_when = card.get("avoid_when", "")
        enriched = {
            "id": card["id"],
            "category": card["category"],
            "name_zh": card["name_zh"],
            "brief": card["brief"],
            "design_roles": card["design_roles"],
            "relationship_tags": card["relationship_tags"],
            "visual_description": visual_description,
            "works_well_with": works_well_with,
            "avoid_when": avoid_when,
        }
        if card.get("name_en"):
            enriched["name_en"] = card["name_en"]
        if asset.get("parameterized") or asset.get("parameter_schema"):
            enriched["parameterized"] = True
            enriched["parameter_schema"] = asset["parameter_schema"]
        new_assets.append(enriched)

    out = {
        key: value
        for key, value in manifest.items()
        if key not in {"families", "family_count", "assets"}
    }
    out["schema_version"] = "2.1.0"
    out["assets"] = new_assets
    return out


def strip_cards(cards: dict) -> dict:
    for card in cards["cards"].values():
        card.pop("family_id", None)
        facts = card.get("objective_facts")
        if isinstance(facts, dict):
            for key in FAMILY_KEYS_IN_FACTS:
                facts.pop(key, None)
        if "style_roles" in card:
            card["design_roles"] = card.pop("style_roles")
        desc = card.get("visual_description", "")
        if isinstance(desc, str) and FAMILY_PROSE in desc:
            card["visual_description"] = desc.replace(FAMILY_PROSE, ASSET_PROSE)
    cards["schema_version"] = "1.2.0"
    return cards


def migrate_profiles(manifest: dict) -> dict:
    if not OLD_PROFILES.exists():
        # 幂等重跑：override 已展开，直接沿用现有 asset_filter_profiles.json。
        return load(NEW_PROFILES)
    family_to_variants = {
        family["id"]: family.get("variant_ids", [family["id"]])
        for family in manifest.get("families", [])
        if isinstance(family, dict)
    }
    old = load(OLD_PROFILES)
    asset_overrides: dict[str, dict] = {}
    for family_id, override in old["family_overrides"].items():
        for variant in family_to_variants.get(family_id, [family_id]):
            asset_overrides[variant] = override
    return {
        "schema_version": "1.1.0",
        "purpose": old["purpose"],
        "field_definitions": old["field_definitions"],
        "defaults_by_category": old["defaults_by_category"],
        "asset_overrides": asset_overrides,
        "category_room_exclusions": old["category_room_exclusions"],
    }


def main() -> None:
    manifest = load(MANIFEST)
    if "families" not in manifest:
        print("已迁移：manifest 无 families，无需操作")
        return

    cards = load(CARDS)

    # strip_cards 先执行：把 style_roles 统一为 design_roles，enrich_manifest 才能读到。
    new_cards = strip_cards(cards)
    new_manifest = enrich_manifest(manifest, cards)
    new_profiles = migrate_profiles(manifest)

    dump(MANIFEST, new_manifest)
    for copy in MANIFEST_COPIES:
        dump(copy, new_manifest)
    dump(CARDS, new_cards)
    for copy in CARDS_COPIES:
        dump(copy, new_cards)
    dump(NEW_PROFILES, new_profiles)
    if OLD_PROFILES.exists():
        OLD_PROFILES.unlink()

    print(
        f"迁移完成：{len(new_manifest['assets'])} assets，"
        f"{len(new_cards['cards'])} cards，"
        f"{len(new_profiles['asset_overrides'])} asset overrides"
    )
    print("写入 asset_manifest.json(+3 副本)、asset_cards.json(+1 副本)、asset_filter_profiles.json；删除 asset_family_filter_profiles.json")


if __name__ == "__main__":
    main()
