"""Pure fail-closed compaction for browser-rendered visual evidence."""

from __future__ import annotations


def _is_pixel_verified_ready(payload: dict) -> bool:
    """Only a complete pixel-verified observation may become model vision input."""

    return (
        payload.get("status") == "ready"
        and payload.get("evidenceLevel") == "pixel_verified_coverage"
    )


def _view_quality_valid(view: object) -> bool:
    if not isinstance(view, dict):
        return False
    quality = view.get("quality")
    return isinstance(quality, dict) and quality.get("valid") is True


def _room_contract_ready(payload: dict) -> bool:
    views = payload.get("views")
    planned = payload.get("plannedCoverage")
    verified = payload.get("verifiedCoverage")
    if not _is_pixel_verified_ready(payload):
        return False
    if not isinstance(views, list) or not views or not all(_view_quality_valid(view) for view in views):
        return False
    if payload.get("uncoveredTargetIds") or payload.get("invalidViewIds"):
        return False
    if not isinstance(planned, dict) or not isinstance(verified, dict) or not planned:
        return False
    return all(
        isinstance(verified.get(target_id), list) and bool(verified[target_id])
        for target_id in planned
    )


def _home_contract_ready(payload: dict) -> bool:
    pairs = payload.get("transitionPairs")
    hero_diagnostics = payload.get("roomHeroDiagnostics")
    if not _is_pixel_verified_ready(payload):
        return False
    if payload.get("incompleteRooms") or payload.get("invalidHeroRoomIds"):
        return False
    if not isinstance(payload.get("roomContactSheet"), str):
        return False
    if not isinstance(pairs, list) or not pairs:
        return False
    if not all(
        isinstance(pair, dict)
        and pair.get("status") == "ready"
        and _view_quality_valid(pair.get("from"))
        and _view_quality_valid(pair.get("to"))
        for pair in pairs
    ):
        return False
    if not isinstance(hero_diagnostics, list) or not hero_diagnostics:
        return False
    return all(
        _view_quality_valid({"quality": hero.get("quality")})
        and isinstance(hero.get("maskQuality"), dict)
        and isinstance(hero["maskQuality"].get("occluderPixelRatio"), (int, float))
        and hero["maskQuality"]["occluderPixelRatio"] <= 0.72
        for hero in hero_diagnostics
        if isinstance(hero, dict)
    ) and all(isinstance(hero, dict) for hero in hero_diagnostics)


def compact_render_evidence(
    tool: str,
    payload: dict,
) -> tuple[dict, list[tuple[str, str]]]:
    """Strip data URLs from metadata and fail closed when evidence is incomplete."""

    images: list[tuple[str, str]] = []
    summary = dict(payload)
    observation_ready = (
        _room_contract_ready(payload)
        if tool == "observe_room"
        else _home_contract_ready(payload)
        if tool == "observe_home_harmony"
        else False
    )

    if tool == "observe_room":
        views = []
        for raw_view in payload.get("views", []):
            if not isinstance(raw_view, dict):
                continue
            view = dict(raw_view)
            image_url = view.pop("imageDataUrl", None)
            views.append(view)
            if observation_ready and _view_quality_valid(view) and isinstance(image_url, str):
                images.append(
                    (
                        f"{payload.get('room', {}).get('label', '房间')} · "
                        f"{view.get('label', '观察视图')}",
                        image_url,
                    )
                )
        summary["views"] = views
    elif tool == "observe_home_harmony":
        contact_sheet = summary.pop("roomContactSheet", None)
        if observation_ready and isinstance(contact_sheet, str):
            images.append(("全屋代表视图总览", contact_sheet))

        pairs = []
        for raw_pair in payload.get("transitionPairs", []):
            if not isinstance(raw_pair, dict):
                continue
            pair = dict(raw_pair)
            pair_ready = pair.get("status") == "ready"
            for side in ("from", "to"):
                raw_view = pair.get(side, {})
                view = dict(raw_view) if isinstance(raw_view, dict) else {}
                image_url = view.pop("imageDataUrl", None)
                pair[side] = view
                if (
                    observation_ready
                    and pair_ready
                    and _view_quality_valid(view)
                    and isinstance(image_url, str)
                ):
                    images.append((f"过渡 {pair.get('id', '')} · {side}", image_url))
            pairs.append(pair)
        summary["transitionPairs"] = pairs
    else:
        raise ValueError(f"Unsupported render evidence tool: {tool}")

    summary["modelEvidenceReady"] = observation_ready and bool(images)
    summary["modelEvidenceImageCount"] = len(images)
    if not observation_ready:
        summary["modelEvidenceBlockReason"] = (
            "观察未满足完整的 ready、pixel_verified_coverage、覆盖、单图质量或遮挡合同；"
            "图片仅用于诊断，未作为模型视觉证据回注。"
        )
    elif not images:
        summary["modelEvidenceBlockReason"] = (
            "观察虽标记 ready，但没有通过单图质量门禁的图片；未回注视觉证据。"
        )
    return summary, images
