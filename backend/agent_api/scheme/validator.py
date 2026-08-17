from typing import Any

from .schema import Scheme


ALLOWED_ASSET_CATEGORIES: dict[str, set[str]] = {
    "wall": {"wall_paint", "wallpaper"},
    "floor": {"wood_floor", "tile"},
    "ceiling": {"ceiling"},
}


def validate_scheme(
    scheme: Scheme,
    scene_manifest: dict[str, Any],
    asset_manifest: dict[str, Any],
) -> list[str]:
    """Validate Scheme references and target/asset compatibility.

    An empty list means the Scheme passed validation. The function does not
    mutate the Scheme or either manifest, and it collects all independent
    errors so the caller can fix them in one pass.
    """

    errors: list[str] = []

    manifest_targets = {
        (target.get("kind"), target.get("id")): target
        for target in scene_manifest.get("design_targets", [])
        if isinstance(target.get("kind"), str)
        and isinstance(target.get("id"), str)
    }

    surface_roles: dict[str, str] = {}
    for room in scene_manifest.get("rooms", []):
        surface_ids = room.get("surface_ids", {})
        floor_id = surface_ids.get("floor")
        ceiling_id = surface_ids.get("ceiling")

        if isinstance(floor_id, str):
            surface_roles[floor_id] = "floor"
        if isinstance(ceiling_id, str):
            surface_roles[ceiling_id] = "ceiling"

    assets_by_id = {
        asset["id"]: asset
        for asset in asset_manifest.get("assets", [])
        if isinstance(asset.get("id"), str)
    }

    for index, assignment in enumerate(scheme.assignments):
        target = assignment.target
        manifest_target = manifest_targets.get((target.kind, target.id))
        target_role: str | None = (
            manifest_target.get("role") if manifest_target else None
        )
        if target_role is None and target.kind == "surface":
            target_role = surface_roles.get(target.id)
        if target_role is None:
            errors.append(
                f"assignment[{index}] 目标不存在：{target.kind}:{target.id}"
            )

        asset = assets_by_id.get(assignment.asset_id)
        if asset is None:
            errors.append(
                f"assignment[{index}] 资产不存在：{assignment.asset_id}"
            )
            continue

        if target_role is None:
            continue

        asset_category = asset.get("category")
        declared_categories = (
            manifest_target.get("allowed_asset_categories", [])
            if manifest_target
            else []
        )
        allowed_categories = (
            set(declared_categories)
            if declared_categories
            else ALLOWED_ASSET_CATEGORIES[target_role]
        )
        if asset_category not in allowed_categories:
            errors.append(
                f"assignment[{index}] 资产类别不兼容：目标 {target.id} "
                f"是 {target_role}，不能使用 {asset_category} 类型资产 "
                f"{assignment.asset_id}"
            )

        is_parameterized_paint = (
            asset_category == "wall_paint"
            and asset.get("parameterized") is True
        )
        if assignment.parameters is not None and not is_parameterized_paint:
            errors.append(
                f"assignment[{index}] 只有参数化综合色墙漆允许 parameters：{assignment.asset_id}"
            )

    return errors
