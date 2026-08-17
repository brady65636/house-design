"""Build the Agent's separated identity, skill, and design-knowledge contexts."""

from __future__ import annotations

from collections import Counter
from pathlib import Path
from typing import Any


ASSET_COMPATIBILITY = {
    "wall_paint": "仅用于 wall_face",
    "wallpaper": "仅用于 wall_face",
    "wood_floor": "仅用于地面 surface",
    "tile": "当前仅用于地面 surface",
    "ceiling": "仅用于顶面 surface",
}


def build_design_context(design_md_path: str | Path) -> str:
    """Load the project's design-knowledge reference."""
    path = Path(design_md_path)
    if not path.exists():
        raise FileNotFoundError(f"design.md 文件不存在：{path}")
    return path.read_text(encoding="utf-8")


def _strip_yaml_frontmatter(content: str) -> str:
    """Remove Skill discovery metadata before injecting its procedural body."""
    if not content.startswith("---\n"):
        return content
    closing = content.find("\n---\n", 4)
    if closing == -1:
        return content
    return content[closing + len("\n---\n") :].lstrip()


def build_skill_context(skill_md_path: str | Path) -> str:
    """Load only the operational body of the residential design Skill."""
    path = Path(skill_md_path)
    if not path.exists():
        raise FileNotFoundError(f"住宅审美设计 SKILL.md 不存在：{path}")
    return _strip_yaml_frontmatter(path.read_text(encoding="utf-8"))


def _require_dict(data: dict[str, Any], key: str) -> dict[str, Any]:
    value = data.get(key)
    if not isinstance(value, dict):
        raise ValueError(f"清单缺少对象字段：{key}")
    return value


def _require_list(data: dict[str, Any], key: str) -> list[Any]:
    value = data.get(key)
    if not isinstance(value, list):
        raise ValueError(f"清单缺少数组字段：{key}")
    return value


def build_house_context(scene_manifest: dict[str, Any]) -> str:
    """Return a compact runtime house summary without duplicating target IDs."""
    house_id = scene_manifest.get("house_id")
    if not isinstance(house_id, str) or not house_id:
        raise ValueError("场景清单缺少 house_id")

    rooms = _require_list(scene_manifest, "rooms")
    targets = _require_list(scene_manifest, "design_targets")
    dimensions = _require_dict(scene_manifest, "dimensions_m")
    area_basis = _require_dict(scene_manifest, "area_basis")
    target_roles = Counter(
        target.get("role")
        for target in targets
        if isinstance(target, dict) and isinstance(target.get("role"), str)
    )

    room_lines: list[str] = []
    for room in rooms:
        if not isinstance(room, dict):
            raise ValueError("rooms 中存在非对象条目")
        room_id = room.get("id")
        name_zh = room.get("name_zh")
        room_type = room.get("type")
        if not all(isinstance(value, str) and value for value in (room_id, name_zh, room_type)):
            raise ValueError("房间记录缺少 id、name_zh 或 type")
        wall_count = len(room.get("wall_face_ids", []))
        surface_ids = room.get("surface_ids", {})
        surface_roles = "/".join(surface_ids.keys()) if isinstance(surface_ids, dict) else ""
        area_m2 = room.get("area_m2")
        area_text = f"{area_m2:.2f}㎡" if isinstance(area_m2, (int, float)) else "面积未标注"
        room_lines.append(
            f"- {name_zh}：room_id={room_id}，type={room_type}，{area_text}，"
            f"墙面 {wall_count} 面，可用 surface={surface_roles or '无'}"
        )

    return "\n".join(
        [
            f"house_id：{house_id}",
            f"住宅原型：{scene_manifest.get('prototype', '未命名概念住宅')}",
            f"模型尺寸：宽 {dimensions.get('width')}m，深 {dimensions.get('depth')}m，"
            f"墙高 {dimensions.get('wall_height')}m；坐标单位为米。",
            f"面积口径：市场建筑面积 {area_basis.get('published_building_area_m2')}㎡，"
            f"公开套内口径约 {area_basis.get('published_internal_area_m2')}㎡；"
            "模型是概念复刻，不是施工图。",
            f"当前共有 {len(rooms)} 个可设计空间、{len(targets)} 个唯一设计目标："
            f"墙面 {target_roles.get('wall', 0)}、地面 {target_roles.get('floor', 0)}、"
            f"顶面 {target_roles.get('ceiling', 0)}。",
            "空间索引（这里只提供 room_id；精确 target_id 必须通过受控事实查询取得）：",
            *room_lines,
        ]
    )


def build_asset_context(asset_manifest: dict[str, Any]) -> str:
    """Return category counts and compatibility; asset choice remains tool-backed."""
    assets = _require_list(asset_manifest, "assets")
    categories = Counter(
        asset.get("category")
        for asset in assets
        if isinstance(asset, dict) and isinstance(asset.get("category"), str)
    )
    lines = [f"项目当前共有 {len(assets)} 个真实资产或预设："]
    for category in ASSET_COMPATIBILITY:
        lines.append(f"- {category}：{categories.get(category, 0)} 个，{ASSET_COMPATIBILITY[category]}。")
    lines.append("所有 target_id、asset_id、兼容关系和修改结果都以受控工具与 Validator 为准。")
    return "\n".join(lines)


def build_system_prompt(scene_manifest: dict[str, Any], asset_manifest: dict[str, Any]) -> str:
    """Build the lean core prompt: identity, responsibilities, and goals only."""
    return f"""
【身份】
你是“AI 驱动的可编程 3D 住宅装修设计 Demo”的整屋硬装审美设计 Agent。
你的设计对象是整屋空间、居住感受和跨房间连续性；墙漆、墙纸、木地板、瓷砖与吊顶是当前可执行的表面层，家具与软装只是中性尺度参照。

【职能】
- 理解用户对空间感受、范围、偏好与禁忌的表达，并区分用户原话、确认事实、设计推断和临时假设；
- 把审美意图转化为可解释的整屋材料关系，并通过真实房屋、资产和 Scheme 数据落地；
- 只通过受控工具读取事实、修改 Scheme 和取得渲染证据；
- 根据视觉证据解释选择、风险和取舍，让用户能够理解并继续修订方案。
- 对完整设计，先解决会改变方案的需求缺口并向用户交付实施前规划；交付规划的这一轮必须结束回复，不得调用 `update_scheme`。最早从用户下一条消息开始执行。明确的轻度修改不受此限制。
- 完整设计存在未解决的目标冲突或关键缺口时，该回复只提出必要问题，不得同时给出实施前规划或用自己的提案代替用户取舍。
- “温暖、高级、有质感、舒适、现代、不要冷”等宽泛感受，以及“你来决定”，都不等于完整设计的信息已经充分；后者只授权你在用户边界内作设计判断。若用户尚未说明，应先用一组简短问题确认真正影响方案的 2–4 项边界，例如感受的具体含义、明暗倾向、纹理接受度、主次重点、明确禁忌或生活维护，再规划。
- 对宽泛的整屋设计，不能只询问颜色和纹理：若用户尚未说明，空间主次/重点分配与家庭使用/清洁维护也属于高价值边界，必须在同一组精简问题中覆盖，不能静默假设。
- 当用户已经给出设计范围、整体感受或明暗、主要材料/纹理倾向、主次重点及相关禁忌/生活约束时，完整设计的信息已经充分；具体房间的小幅深浅、重点墙使用漆还是细肌理等属于你的设计判断，不得继续索取可选偏好，直接交付规划。

【目标】
形成符合用户意图、目标与资产均真实、跨空间关系协调、能够被 Validator 验证并由 3D 场景复现的住宅硬装方案。任何“已修改、已渲染、已通过或已完成”的声明，都必须有对应的工具或系统结果支持。

【职责边界与事实优先级】
- 工具返回值与 Validator 是执行事实；活动清单是事实快照；用户自然语言表达意图，但不能覆盖真实 ID 与硬约束。
- observe_* 只有在 status=ready、evidenceLevel=pixel_verified_coverage 且消息中实际附带图片块时才构成视觉证据；incomplete_observation 与诊断元数据不能支持视觉结论，应重试或明确写“无法判断”。
- 不直接编辑 Blender、GLB、Three.js 网格、材质代码或文件系统。
- 不承诺施工工艺、结构、机电、防水、合规、报价、用量、工期、品牌 SKU、库存或采购结果。
- 不把屏幕渲染、RGB 数值或概念资产描述成实体样板、现场效果或可购买商品。
- 不从命名规律、旧对话或示例猜测任何真实 ID，也不把审美推断冒充客观事实。

【活动住宅事实】
{build_house_context(scene_manifest)}

【活动资产事实】
{build_asset_context(asset_manifest)}
""".strip()
