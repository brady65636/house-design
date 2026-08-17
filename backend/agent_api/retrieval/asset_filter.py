"""High-recall Asset filter.

This module is intentionally not an aesthetic ranker.  It applies only
high-confidence vetoes, then keeps a small, diverse comparison set for the
Design Agent to render and inspect visually.

Assets are the single unit: asset_manifest.json exposes a flat `assets[]`
array where every asset is self-describing, and the filter operates on those
assets directly.
"""

from __future__ import annotations

import json
import math
from collections.abc import Mapping
from pathlib import Path
from typing import Any


MIN_REDUCTION_RATE = 0.70
MIN_COMPARISON_COUNT = 2

PROFILE_ENUMS = {
    "temperature": {"warm", "neutral", "cool", "mixed"},
    "chroma_band": {"low", "medium", "high"},
    "value_band": {"light", "medium", "dark", "mixed"},
    "activity": {"low", "medium", "high"},
    "scale": {"none", "micro", "small", "medium", "large", "mural"},
    "direction": {"none", "vertical", "horizontal", "grid", "organic", "mixed"},
    "direction_strength": {"low", "high"},
}


class AssetFilterError(ValueError):
    """The filter query or its source data is invalid."""


def load_filter_profiles(path: str | Path) -> dict[str, Any]:
    """Load and validate the human-calibrated coarse filter profiles."""

    payload = json.loads(Path(path).read_text(encoding="utf-8"))
    defaults = payload.get("defaults_by_category")
    overrides = payload.get("asset_overrides")
    if not isinstance(defaults, dict) or not isinstance(overrides, dict):
        raise AssetFilterError("过滤档案必须包含 defaults_by_category 与 asset_overrides")
    for category, profile in defaults.items():
        _validate_profile(profile, f"defaults_by_category.{category}")
    for asset_id, override in overrides.items():
        if not isinstance(override, dict):
            raise AssetFilterError(f"Asset {asset_id} 的覆盖档案必须是对象")
        unknown = set(override) - (set(PROFILE_ENUMS) | {"material_language", "requires_continuous_target"})
        if unknown:
            raise AssetFilterError(f"Asset {asset_id} 含未知过滤字段：{sorted(unknown)}")
    return payload


def _validate_profile(profile: Mapping[str, Any], label: str) -> None:
    required = set(PROFILE_ENUMS) | {"material_language", "requires_continuous_target"}
    missing = required - set(profile)
    if missing:
        raise AssetFilterError(f"{label} 缺少字段：{sorted(missing)}")
    for field, allowed in PROFILE_ENUMS.items():
        if profile[field] not in allowed:
            raise AssetFilterError(f"{label}.{field}={profile[field]!r} 不在允许值中")
    if not isinstance(profile["material_language"], str) or not profile["material_language"]:
        raise AssetFilterError(f"{label}.material_language 必须是非空字符串")
    if not isinstance(profile["requires_continuous_target"], bool):
        raise AssetFilterError(f"{label}.requires_continuous_target 必须是布尔值")


def _resolved_profile(
    asset: Mapping[str, Any], profile_data: Mapping[str, Any]
) -> dict[str, Any]:
    category = asset.get("category")
    asset_id = asset.get("id")
    default = profile_data["defaults_by_category"].get(category)
    if not isinstance(default, dict):
        raise AssetFilterError(f"资产类别 {category!r} 没有默认过滤档案")
    result = dict(default)
    override = profile_data["asset_overrides"].get(asset_id, {})
    result.update(override)
    _validate_profile(result, f"resolved.{asset_id}")
    return result


def _find_target(scene_manifest: Mapping[str, Any], target_id: str) -> Mapping[str, Any]:
    for target in scene_manifest.get("design_targets", []):
        if isinstance(target, dict) and target.get("id") == target_id:
            return target
    raise AssetFilterError(f"未知 target_id：{target_id}")


def _room_for_target(
    scene_manifest: Mapping[str, Any], target: Mapping[str, Any]
) -> Mapping[str, Any]:
    room_id = target.get("room_id")
    for room in scene_manifest.get("rooms", []):
        if isinstance(room, dict) and room.get("id") == room_id:
            return room
    for room in scene_manifest.get("balconies", []):
        if isinstance(room, dict) and room.get("id") == room_id:
            return room
    raise AssetFilterError(f"目标 {target.get('id')} 引用了未知 room_id：{room_id}")


def _target_is_fragmented(scene_manifest: Mapping[str, Any], target_id: str) -> bool:
    wall_face = next(
        (
            wall
            for wall in scene_manifest.get("wall_faces", [])
            if isinstance(wall, dict) and wall.get("id") == target_id
        ),
        None,
    )
    if not wall_face:
        return False
    start = wall_face.get("start")
    end = wall_face.get("end")
    host_wall_id = wall_face.get("host_wall_id")
    if not isinstance(start, (int, float)) or not isinstance(end, (int, float)):
        return False
    return any(
        isinstance(opening, dict)
        and opening.get("host_wall_id") == host_wall_id
        and isinstance(opening.get("start"), (int, float))
        and isinstance(opening.get("end"), (int, float))
        and max(start, opening["start"]) < min(end, opening["end"])
        for opening in scene_manifest.get("openings", [])
    )


def _ceiling_room_compatible(
    asset_id: str, room_type: str, asset_cards: Mapping[str, Any]
) -> bool:
    suitability: set[str] = set()
    cards = asset_cards.get("cards", asset_cards)
    if not isinstance(cards, dict):
        return True
    card = cards.get(asset_id)
    if isinstance(card, dict):
        facts = card.get("objective_facts", {})
        if isinstance(facts, dict):
            values = facts.get("suitable_rooms", [])
            if isinstance(values, list):
                suitability.update(value for value in values if isinstance(value, str))
    if not suitability:
        return True
    if room_type in suitability:
        return True
    return "all_dry_rooms" in suitability and room_type not in {"bathroom", "kitchen", "balcony"}


def _hard_veto_reasons(
    *,
    asset: Mapping[str, Any],
    profile: Mapping[str, Any],
    room_type: str,
    target_is_fragmented: bool,
    asset_cards: Mapping[str, Any],
    profile_data: Mapping[str, Any],
) -> list[str]:
    reasons: list[str] = []
    category = asset.get("category")
    room_exclusions = profile_data.get("category_room_exclusions", {})
    excluded_room_types = room_exclusions.get(category, []) if isinstance(room_exclusions, dict) else []
    if room_type in excluded_room_types:
        reasons.append("ROOM_MOISTURE_INCOMPATIBLE")
    if category == "ceiling" and not _ceiling_room_compatible(asset["id"], room_type, asset_cards):
        reasons.append("ROOM_TYPE_INCOMPATIBLE")
    if target_is_fragmented and profile["requires_continuous_target"]:
        reasons.append("CONTINUOUS_PATTERN_ON_FRAGMENTED_TARGET")
    return reasons


def _relationship_veto_reasons(
    *,
    role: str,
    color_intent: str,
    profile: Mapping[str, Any],
    anchor_profile: Mapping[str, Any] | None,
) -> list[str]:
    reasons: list[str] = []
    if role == "quiet" and profile["activity"] == "high":
        reasons.append("HIGH_ACTIVITY_FOR_QUIET_ROLE")
    if (
        role == "support"
        and anchor_profile
        and anchor_profile["activity"] == "high"
        and profile["activity"] == "high"
    ):
        reasons.append("DUAL_HIGH_ACTIVITY")
    if (
        color_intent == "harmonious"
        and anchor_profile
        and anchor_profile["chroma_band"] == "high"
        and profile["chroma_band"] == "high"
        and {anchor_profile["temperature"], profile["temperature"]} == {"warm", "cool"}
    ):
        reasons.append("EXTREME_HARMONIOUS_COLOR_CONFLICT")
    return reasons


def _warnings(
    *,
    role: str,
    profile: Mapping[str, Any],
    anchor_profile: Mapping[str, Any] | None,
) -> list[str]:
    warnings: list[str] = []
    if role == "quiet" and profile["activity"] == "medium":
        warnings.append("MEDIUM_ACTIVITY_FOR_QUIET_ROLE")
    if not anchor_profile:
        return warnings
    if (
        anchor_profile["direction_strength"] == "high"
        and profile["direction_strength"] == "high"
        and anchor_profile["direction"] != profile["direction"]
    ):
        warnings.append("STRONG_DIRECTION_COMPETITION")
    if anchor_profile["value_band"] == profile["value_band"] == "dark":
        warnings.append("DUAL_DARK_VALUE")
    return warnings


def _activity_fit(role: str, activity: str) -> int:
    if role == "anchor":
        return {"high": 3, "medium": 2, "low": 1}[activity]
    if role == "quiet":
        return {"low": 3, "medium": 2, "high": 0}[activity]
    return {"medium": 3, "low": 2, "high": 1}[activity]


def _select_diverse(entries: list[dict[str, Any]], role: str, limit: int) -> list[dict[str, Any]]:
    """Greedy stratified sample; the score describes fit/diversity, not beauty."""

    remaining = list(entries)
    selected: list[dict[str, Any]] = []
    seen_temperatures: set[str] = set()
    seen_languages: set[str] = set()
    seen_activities: set[str] = set()
    while remaining and len(selected) < limit:
        best_fit: tuple[int, int, int, int] | None = None
        best: dict[str, Any] | None = None
        for entry in remaining:
            profile = entry["filter_profile"]
            fit = (
                _activity_fit(role, profile["activity"]),
                int(profile["temperature"] not in seen_temperatures),
                int(profile["material_language"] not in seen_languages),
                int(profile["activity"] not in seen_activities),
            )
            if best_fit is None or fit > best_fit or (fit == best_fit and entry["asset_id"] < best["asset_id"]):
                best_fit = fit
                best = entry
        assert best is not None
        selected.append(best)
        remaining.remove(best)
        profile = best["filter_profile"]
        seen_temperatures.add(profile["temperature"])
        seen_languages.add(profile["material_language"])
        seen_activities.add(profile["activity"])
    return selected


def filter_assets(
    *,
    scene_manifest: Mapping[str, Any],
    asset_manifest: Mapping[str, Any],
    asset_cards: Mapping[str, Any],
    profile_data: Mapping[str, Any],
    target_id: str,
    category: str,
    role: str,
    anchor_asset_id: str | None = None,
    color_intent: str = "open",
) -> dict[str, Any]:
    """Return a small visual-comparison set plus explainable exclusions."""

    if role not in {"anchor", "support", "quiet"}:
        raise AssetFilterError("role 只能是 anchor、support 或 quiet")
    if color_intent not in {"open", "harmonious", "contrasting"}:
        raise AssetFilterError("color_intent 只能是 open、harmonious 或 contrasting")

    target = _find_target(scene_manifest, target_id)
    allowed_categories = target.get("allowed_asset_categories", [])
    if category not in allowed_categories:
        raise AssetFilterError(
            f"目标 {target_id} 不允许类别 {category}；允许值为 {allowed_categories}"
        )
    room = _room_for_target(scene_manifest, target)
    room_type = str(room.get("type", room.get("id", "unknown")))

    assets = [
        asset
        for asset in asset_manifest.get("assets", [])
        if isinstance(asset, dict) and asset.get("category") == category
    ]
    if not assets:
        raise AssetFilterError(f"类别 {category} 没有 Asset 候选")

    asset_by_id = {
        asset.get("id"): asset
        for asset in asset_manifest.get("assets", [])
        if isinstance(asset, dict)
    }
    anchor_profile = None
    if anchor_asset_id:
        anchor = asset_by_id.get(anchor_asset_id)
        if not anchor:
            raise AssetFilterError(f"未知 anchor_asset_id：{anchor_asset_id}")
        anchor_profile = _resolved_profile(anchor, profile_data)

    fragmented = _target_is_fragmented(scene_manifest, target_id)
    eligible_before_budget: list[dict[str, Any]] = []
    rejected: list[dict[str, Any]] = []
    for asset in assets:
        profile = _resolved_profile(asset, profile_data)
        reasons = _hard_veto_reasons(
            asset=asset,
            profile=profile,
            room_type=room_type,
            target_is_fragmented=fragmented,
            asset_cards=asset_cards,
            profile_data=profile_data,
        )
        reasons.extend(
            _relationship_veto_reasons(
                role=role,
                color_intent=color_intent,
                profile=profile,
                anchor_profile=anchor_profile,
            )
        )
        compact = {
            "asset_id": asset["id"],
            "category": asset["category"],
            "name_zh": asset.get("name_zh"),
            "filter_profile": profile,  # 仅内部采样用，返回前剥除
        }
        if reasons:
            rejected.append({**compact, "reasons": sorted(set(reasons))})
            continue
        eligible_before_budget.append(
            {
                **compact,
                "brief": asset.get("brief"),
                "warnings": _warnings(
                    role=role,
                    profile=profile,
                    anchor_profile=anchor_profile,
                ),
            }
        )

    total_count = len(assets)
    comparison_limit = max(
        MIN_COMPARISON_COUNT,
        math.floor(total_count * (1.0 - MIN_REDUCTION_RATE) + 1e-9),
    )
    comparison_limit = min(comparison_limit, len(eligible_before_budget))
    eligible = _select_diverse(eligible_before_budget, role, comparison_limit)
    selected_ids = {entry["asset_id"] for entry in eligible}
    deferred = [
        {**entry, "reasons": ["DIVERSITY_BUDGET"]}
        for entry in eligible_before_budget
        if entry["asset_id"] not in selected_ids
    ]

    # 返回体只保留模型决策需要的高信息密度字段，剥除 filter 内部的 filter_profile 枚举；
    # rejected/deferred 再剥掉 brief，只留中文名与否决原因。
    def _public(entry: dict[str, Any], keep_brief: bool = False) -> dict[str, Any]:
        result = {key: value for key, value in entry.items() if key != "filter_profile"}
        if not keep_brief:
            result.pop("brief", None)
        return result

    eligible = [_public(entry, keep_brief=True) for entry in eligible]
    rejected = [_public(entry) for entry in rejected]
    deferred = [_public(entry) for entry in deferred]

    reduction_rate = (total_count - len(eligible)) / total_count
    return {
        "query": {
            "target_id": target_id,
            "room_id": target.get("room_id"),
            "room_type": room_type,
            "category": category,
            "role": role,
            "anchor_asset_id": anchor_asset_id,
            "color_intent": color_intent,
            "target_is_fragmented": fragmented,
        },
        "eligible": eligible,
        "rejected": rejected,
        "deferred": deferred,
        "metrics": {
            "input_count": total_count,
            "output_count": len(eligible),
            "excluded_count": total_count - len(eligible),
            "vetoed_count": len(rejected),
            "budget_deferred_count": len(deferred),
            "reduction_rate": round(reduction_rate, 4),
            "target_reduction_rate": MIN_REDUCTION_RATE,
            "target_met": reduction_rate + 1e-9 >= MIN_REDUCTION_RATE,
        },
    }
