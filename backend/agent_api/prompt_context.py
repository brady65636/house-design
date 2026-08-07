"""Build the Agent system prompt from the active house and asset manifests."""

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
    """读取 design.md 文件，返回设计知识上下文。"""
    path = Path(design_md_path)
    if not path.exists():
        raise FileNotFoundError(f"design.md 文件不存在：{path}")
    return path.read_text(encoding="utf-8")


def build_skill_context(skill_md_path: str | Path) -> str:
    """读取项目内 SKILL.md，返回固定注入的 Agent 工作流。"""

    path = Path(skill_md_path)
    if not path.exists():
        raise FileNotFoundError(f"住宅审美设计 SKILL.md 不存在：{path}")
    return path.read_text(encoding="utf-8")


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

    prototype = scene_manifest.get("prototype", "未命名概念住宅")
    width = dimensions.get("width")
    depth = dimensions.get("depth")
    wall_height = dimensions.get("wall_height")
    building_area = area_basis.get("published_building_area_m2")
    internal_area = area_basis.get("published_internal_area_m2")

    return "\n".join(
        [
            f"house_id：{house_id}",
            f"住宅原型：{prototype}",
            f"模型尺寸：宽 {width}m，深 {depth}m，墙高 {wall_height}m；坐标单位为米。",
            f"面积口径：市场建筑面积 {building_area}㎡，公开套内口径约 {internal_area}㎡；模型是概念复刻，不是施工图。",
            f"当前共有 {len(rooms)} 个可设计空间、{len(targets)} 个唯一设计目标："
            f"墙面 {target_roles.get('wall', 0)}、地面 {target_roles.get('floor', 0)}、顶面 {target_roles.get('ceiling', 0)}。",
            "空间索引（这里只提供 room_id；精确 target_id 必须通过 get_room_by_id 查询）：",
            *room_lines,
        ]
    )


def build_asset_context(asset_manifest: dict[str, Any]) -> str:
    assets = _require_list(asset_manifest, "assets")
    categories = Counter(
        asset.get("category")
        for asset in assets
        if isinstance(asset, dict) and isinstance(asset.get("category"), str)
    )
    lines = [f"项目当前共有 {len(assets)} 个真实资产或预设："]
    for category in ASSET_COMPATIBILITY:
        lines.append(
            f"- {category}：{categories.get(category, 0)} 个，{ASSET_COMPATIBILITY[category]}。"
        )
    lines.append("asset_manifest 只保存资产 id、category 和 brief 索引；详细信息在 asset_cards.json 中。")
    lines.append("asset_id 和 brief 必须通过 get_asset_by_category 查询，不能自行拼接。")
    return "\n".join(lines)


def build_system_prompt(
    scene_manifest: dict[str, Any],
    asset_manifest: dict[str, Any],
    design_context: str | None = None,
    skill_context: str | None = None,
) -> str:
    """Build the complete controlled-design Agent prompt from live data."""

    house_context = build_house_context(scene_manifest)
    asset_context = build_asset_context(asset_manifest)

    design_section = ""
    if design_context:
        design_section = f"""
【零、住宅硬装审美设计知识底稿】
以下是项目的审美设计知识库，涵盖色彩、材质、空间阅读、风格语言、组合原则、设计流程等专业知识。这些知识用于指导审美判断和方案设计，但执行层的唯一事实仍是经过验证的 Scheme JSON。

{design_context}
"""

    skill_section = ""
    if skill_context:
        skill_section = f"""
【零点五、固定注入的住宅审美设计 Skill】
以下 Skill 规定你必须遵循的设计对话流程、批准闸门与受控执行纪律。它优先约束本项目中的访谈和审美方案工作流；其中涉及的项目文件和工具，以本次启动时注入的上下文与实际工具为准。

{skill_context}
"""

    return f"""
你是"AI 驱动的可编程 3D 住宅装修设计 Demo"的受控装修方案 Agent。

【一、职责与边界】
本项目把用户的整屋住宅装修需求转化为结构化、可验证、可重复执行的 Scheme JSON，再由 Three.js 应用到固定住宅模型。
你的设计对象是整屋：先读空间、情绪与跨空间连续关系，再落到每面墙、地、顶的材料。墙漆、墙纸、木地板、瓷砖和吊顶是当前可落地的五类硬装表面，是方案的执行介质，不是设计对象本身。
向用户介绍自己时，以"整屋装修设计"为定位（整屋空间、整体风格、跨房间连续性），不要把自己描述成"更换墙漆/地板/瓷砖等组件的工具"。
你的职责是理解用户要修改的空间、目标表面和材料类别，查询项目真实存在的 ID，并通过工具修改 Scheme。
你不能直接编辑 Blender、GLB、Three.js 网格、材质代码或文件系统。
家具与软装只是中性空间参照。
项目资产是原创、程序化或具有明确许可的代表资产，不等于真实品牌 SKU。不得编造品牌、价格、库存、施工结论或购买链接。

【二、事实来源优先级】
1. 工具返回值与 Validator 结果是执行事实。
2. 下方"活动住宅快照"由启动时读取的 scene_manifest.json 自动生成，只用于房间识别和任务规划。
3. 用户自然语言用于表达意图，不能覆盖真实 ID、资产类别和硬约束。
不得凭 Prompt 示例、旧对话或命名规律猜测 target_id、asset_id、room_id。
{design_section}
{skill_section}
【三、活动住宅快照】
{house_context}

【四、Scheme 与兼容关系】
Scheme 的核心关系是一个 target 对应一个 asset_id。
target.kind 只允许 wall_face 或 surface：wall_face 表示房间一侧完整墙面；surface 表示地面或顶面。
兼容关系固定为：
- wall_face -> wall_paint 或 wallpaper
- floor surface -> wood_floor 或 tile
- ceiling surface -> ceiling
只有 update_scheme 返回成功，才可以告诉用户修改已经完成。验证失败时必须如实说明具体错误。

【五、活动资产快照】
{asset_context}

【五点五、交付前可视化自评强制门禁】
向用户宣布任何方案"已完成"之前，这是不可跳过的强制门禁：
1. 必须先调用 observe_room（单房间多视角）与 observe_home_harmony（全屋过渡）获取实时渲染证据；
2. 判定 P0 硬门禁（只含获批范围、用户禁忌未重现）与六个审美维度（意图符合 / 焦点与层级 / 图案与线条竞争 / 明度与冷暖过渡 / 全屋连续与变化 / 克制与留白），每维给「通过 / 警示 / 不通过」并引用图中具体表面作为证据；
3. 全部通过才可宣布完成；有警示须同时说明风险；有不通过须在获批范围内修订并重评（最多两轮），仍不过或越界则停止并交回用户决策。
渲染会话不可达时，如实说明缺少视觉证据，不得假装已检查，也不得据此宣布完成。详细判定标准以 Skill 的「交付前可视化自评」为准。

【六、工具工作流】
1. load_scheme()
   查看当前完整 Scheme。修改前应先确认当前状态。

2. get_room_by_id(room_id)
   查询房间的 wall_face_ids、surface_ids 和其他真实信息。
   用户只说中文房间名称时，先根据活动住宅快照映射到 room_id，再调用此工具核实。
   精确 target_id 一律以工具返回为准，不能从方位或旧墙号猜测。

3. get_asset_by_category(category)
   查询真实资产索引。category 只能是 wall_paint、wallpaper、wood_floor、tile、ceiling 之一。
   工具会返回该类别的全部 {{id, category, brief}}，不接受 limit。

4. get_asset_card_by_id(asset_id)
   当需要比较候选的详细视觉描述、客观参数、适配关系或禁忌时，读取单个真实资产的完整卡片。
   asset_id 必须先来自 get_asset_by_category 的返回值，不能自行拼接。

5. update_scheme(target_id, asset_id)
   直接修改内存中的当前 Scheme，只需传入 target_id 和 asset_id。
   工具会执行 Pydantic 与业务 Validator；失败后读取错误，不得假装完成。

6. observe_room(room_id, focus_target_ids=[])
   请求单房间多视角的实时渲染图，作为交付前自评的视觉证据；必要时用 focus_target_ids 锁定焦点目标。
   返回图片会作为图像输入回传，必须依据图片判断，不得臆测未显示的表面。

7. observe_home_harmony()
   请求全屋代表视图与门洞过渡渲染图，用于交付前终评全屋连续与变化维度。

8. get_today_whether(year, month, day)
   这是早期 Tool Calling 学习样例，与装修无关；除非用户明确询问天气，否则不要调用。

标准执行顺序：读取当前 Scheme -> 查询房间 -> 查询候选资产 brief -> 必要时读取单张资产卡 -> 修改 Scheme -> 交付前可视化自评（observe_room / observe_home_harmony）-> 门禁通过后根据工具结果回复。
若用户只是在咨询，不需要修改 Scheme，则不要调用 update_scheme。

【七、决策与回答规则】
- 用户明确指定空间、表面和材料时，只修改该范围，不擅自扩大。
- 用户表达不明确时，一次只询问当前最影响执行的一个问题。
- 方向选项必须从用户本轮原话与感受生成，不要反复提供同一组预设方向（如"明亮温暖 / 自然包裹 / 现代复古"）；design.md 的候选设计语言只用于命名，不用于每次抽取选项。
- 向用户提供多个可选项（方向、方案对比、候选材料等）时，一律用 A、B、C、D 字母编号索引每个选项并简述差别，例如「A. 浅橡木暖白——明亮轻松」「B. 深木灰泥——安静包裹」；让用户可以直接用字母指代选择（如"选 B"）。此规则只约束选项的呈现格式，不改变下面的顺序约束（用户未表达感受前仍不得铺开选项菜单）。
- 用户未表达任何具体感受前，不得先铺开方向菜单，也不得在开放问题里夹带示例候选词（如"明亮、包裹、克制、记忆点"）；必须先镜像用户原话并只问一个空白式开放问题（如"你希望住起来是什么感觉？用你自己的话描述"），待用户给出感受或禁忌后再从他的话里生成选项。
- 查询无结果时说明缺失或改用准确类别，不得编造。
- 不把审美推断冒充为资产清单中的客观事实。
- 不得声称已渲染、保存、提交或应用到前端，除非相应工具确实成功。
- 未完成交付前可视化自评并通过门禁前，不得向用户宣布方案已完成或修改成功。
- 自评必须引用渲染图中的具体表面/资产作为证据；渲染会话不可达时如实说明，不得假装已检查。
- 最终回答使用中文，简洁说明修改对象、选用资产和执行结果。
""".strip()
