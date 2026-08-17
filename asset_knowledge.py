"""Build the compact asset index and detailed aesthetic asset cards.

The index is deliberately small because it is returned by the Agent's category
lookup tool.  The cards keep the complete objective data plus visual design
knowledge and are fetched one asset at a time after a candidate is chosen.
"""

from __future__ import annotations

from collections.abc import Iterable
from copy import deepcopy
from datetime import datetime, timezone
from typing import Any


PAINT_GUIDANCE: dict[str, dict[str, str | list[str]]] = {
    "warm_white": {
        "description": "柔和偏暖、低彩度的近白色；用于减轻纯白墙面的生硬，并放大自然光的温度。",
        "spatial_effect": "作为大面积墙面会形成明亮、柔和的基底；深色档可提供轻度包裹感。",
        "works_well_with": ["浅色自然木", "暖灰与米色矿物砖", "低对比织纹墙纸"],
        "avoid_when": "空间已同时使用高饱和黄木和暖黄砖时，容易令整体偏黄。",
    },
    "cool_white": {
        "description": "带灰度的冷中性近白色；在偏暖木色和强日照空间中保持清爽。",
        "spatial_effect": "让背景显得干净、后退，适合以木地板或图案墙纸承担温度与焦点。",
        "works_well_with": ["浅色自然木", "低对比白色石纹砖", "细线性或矿物感墙纸"],
        "avoid_when": "与高饱和蜂蜜木和偏蓝灰瓷砖同时大面积并置时，冷暖反差可能生硬。",
    },
    "greige": {
        "description": "介于暖灰和米色之间的低饱和中性色，是木、亚麻和石材之间的安静过渡。",
        "spatial_effect": "能降低多种材料之间的色温冲突，适合作为公共区连续墙面背景。",
        "works_well_with": ["自然橡木", "洞石感瓷砖", "亚麻与暖灰织纹墙纸"],
        "avoid_when": "若地面、顶面和墙面都采用几乎相同的明度与哑光表面，空间会显得单薄。",
    },
    "taupe": {
        "description": "带泥土感的棕灰中性色，提供温和包裹感而不过度泛黄。",
        "spatial_effect": "中色和深色档能为卧室或完整焦点墙增加安静的视觉重量。",
        "works_well_with": ["胡桃木感地板", "暖米石材感瓷砖", "低对比植物或矿物墙纸"],
        "avoid_when": "采光偏弱空间若多面连续使用深色档，整体可能过于沉重。",
    },
    "charcoal": {
        "description": "从柔和中灰到低反射炭灰的中性灰色，用于现代背景或局部强调。",
        "spatial_effect": "深色档能建立明确重心并压低反射；浅色档仍保持理性、清晰的背景。",
        "works_well_with": ["浅自然木", "低对比白色石纹", "克制的线性吊顶"],
        "avoid_when": "不宜同时叠加深木地板、高对比 Damask 或多处深色墙面。",
    },
    "sage_olive": {
        "description": "低彩度植物绿，带灰度而非鲜绿；与自然材料相处时稳定、安静。",
        "spatial_effect": "适合做低强度的情绪墙面或卧室背景，提供自然感而不成为强装饰。",
        "works_well_with": ["浅木与灰洗木", "暖白矿物砖", "草本或亚麻墙纸"],
        "avoid_when": "与多种高饱和陶土、芥末黄和植物图案同时出现，容易变成主题堆砌。",
    },
    "slate_blue": {
        "description": "降低纯蓝饱和度后的灰蓝与深蓝，适合沉静而不冷峻的空间。",
        "spatial_effect": "中色和深色档可制造收拢、安静的背景，浅色档则保留清透感。",
        "works_well_with": ["浅色或烟熏木", "低对比白灰石材", "抽象矿物墙纸"],
        "avoid_when": "与偏黄木色、暖黄砖直接大面积对撞时，需先加入灰米过渡。",
    },
    "terracotta": {
        "description": "带矿物感的低饱和暖红棕，适合提供小面积温度和记忆点。",
        "spatial_effect": "中色和深色档具有明显视觉重量，应作为局部强调而非处处重复。",
        "works_well_with": ["暖白墙面", "自然橡木", "暖灰或洞石感砖"],
        "avoid_when": "避免再与高对比花砖、红棕木地板和强植物墙纸同时竞争。",
    },
    "dusty_rose": {
        "description": "混入灰度的粉紫与藕色，柔和但不甜腻。",
        "spatial_effect": "可让私人空间更温和、亲密；深色档适合作为克制的情绪焦点。",
        "works_well_with": ["暖白与 Greige", "浅色细纹木", "低对比亚麻或植物墙纸"],
        "avoid_when": "不宜与高饱和粉色、金色古典图案和强亮面材料一起大面积使用。",
    },
    "ochre": {
        "description": "从浅麦秆到深黄赭的低饱和矿物黄，带有成熟的温暖感。",
        "spatial_effect": "更适合局部色彩重心；浅色档可作温和背景，中深档会明显提高空间温度。",
        "works_well_with": ["灰米墙面", "烟熏或自然木", "白色与暖灰矿物砖"],
        "avoid_when": "若与蜂蜜木、暖白和暖洞石全部大面积叠加，整体容易失去中性呼吸。",
    },
}

SPECIALTY_PAINT_GUIDANCE: dict[str, dict[str, str | list[str]]] = {
    "limewash_cool_neutral": {
        "description": "冷灰米底色的石灰洗涂层，以低对比云雾和薄层叠刷提供连续的矿物变化。",
        "spatial_effect": "远景保持安静，侧光下才显出柔和手工层次，适合把深木或强石材托成焦点。",
        "works_well_with": ["深色木地板", "深色草编墙纸", "暖白或冷灰细模数砖"],
        "avoid_when": "不要与另一种大面积云纹、强石纹和高色差做旧木同时竞争。",
    },
    "clay_plaster_earth": {
        "description": "低彩度暖土黏土灰泥，细砂颗粒与干燥吸光感形成自然但克制的连续背景。",
        "spatial_effect": "在不依赖木纹的情况下增加温度，适合作为卧室或公共区的包裹底色。",
        "works_well_with": ["冷白细砖", "自然软木", "浅灰洗木或深炭哑光砖"],
        "avoid_when": "与蜂蜜木、赭黄和暖洞石同时大面积使用时，综合色会过暖。",
    },
    "marmorino_deep": {
        "description": "深炭褐抛光灰泥，以低对比镘刀运动和克制柔光建立连续深色表面。",
        "spatial_effect": "可作为完整主墙或小空间包裹面，提供重量但不依赖显眼图案。",
        "works_well_with": ["浅软木或漂白木", "冷白细模数砖", "平顶或阴影缝"],
        "avoid_when": "采光弱空间避免再叠加深地面、深顶和强图案墙纸。",
    },
}

FLOOR_GUIDANCE: dict[str, dict[str, str | list[str]]] = {
    "light_fine_grain": {
        "description": "浅色、细密、低色差的中性木纹；综合色已压低黄橙倾向，作为地面背景安静而明亮。",
        "spatial_effect": "增强公共区的连续性和轻盈感，不会与低对比墙面争夺注意力。",
        "works_well_with": ["暖白、冷白或 Greige 墙面", "细织纹墙纸", "平顶或阴影缝"],
        "avoid_when": "若期待深沉包裹或强复古重心，它的视觉重量可能不足。",
    },
    "light_natural_oak": {
        "description": "中性浅橡木色，保留温和木纹并压低黄橙倾向，是平衡明亮与自然温度的主地面。",
        "spatial_effect": "适合客餐厅、走廊连续使用，提供稳定的人体尺度和自然温度。",
        "works_well_with": ["Greige、暖白、低饱和植物绿", "洞石或微水泥感瓷砖", "低对比墙纸"],
        "avoid_when": "与多处高对比木纹、复古花砖同时出现，会削弱它作为稳定基底的作用。",
    },
    "honey_warm_wood": {
        "description": "蜂蜜色暖木，比自然浅橡木更有金棕温度和存在感。",
        "spatial_effect": "让空间更亲和、暖润，但大面积使用会明显提高整体色温。",
        "works_well_with": ["冷白或中性灰墙面", "白色低对比石纹砖", "克制的现代顶面"],
        "avoid_when": "与奶油黄墙、暖洞石和黄赭色同时大面积叠加时容易偏黄。",
    },
    "warm_red_brown": {
        "description": "暖红棕胡桃木感地板，综合色深且有成熟的复古重量。",
        "spatial_effect": "可快速建立安静、沉稳或中古感，需要较轻的墙顶退后。",
        "works_well_with": ["暖灰、Taupe、浅灰米墙面", "低对比白色或灰色石材砖", "少量深蓝或陶土强调"],
        "avoid_when": "不宜再搭配深炭灰墙、大尺度 Damask 或多种强图案。",
    },
    "smoked_dark_wood": {
        "description": "烟熏深橡木，低明度且带刷纹，视觉重量最强。",
        "spatial_effect": "为大空间或明确的深沉方向提供重心和包裹感。",
        "works_well_with": ["暖白或灰米墙面", "低反射矿物砖", "安静平顶或细阴影缝"],
        "avoid_when": "采光弱的小空间不宜再叠加深墙和复杂吊顶。",
    },
    "greywashed_reclaimed": {
        "description": "灰洗、高色差、带做旧感的木地板，纹理变化明显。",
        "spatial_effect": "带来松弛、时间感和较强节奏，更适合把它视为主材料。",
        "works_well_with": ["暖白或柔和灰墙面", "素色矿物砖", "无强图案的顶面与墙纸"],
        "avoid_when": "不宜与强石纹、花砖、密集墙纸同时并置。",
    },
    "natural_cork": {
        "description": "暖浅棕的细颗粒天然软木，材料细胞清晰但不形成木纹方向。",
        "spatial_effect": "以柔软、吸音联想和低视觉重量形成亲和地面，填补木板与矿物砖之间的自然材料语言。",
        "works_well_with": ["冷中性石灰洗", "暖土黏土灰泥", "冷灰蓝细模数砖"],
        "avoid_when": "避免与大颗粒水磨石、高色差做旧木同时出现，三种颗粒节奏会互相干扰。",
    },
}

TILE_GUIDANCE: dict[str, dict[str, str | list[str]]] = {
    "plain_mineral": {
        "description": "暖白、低对比的矿物感素砖，以细微表面变化代替显眼石纹。",
        "spatial_effect": "形成干净、安静且可连续延展的底面或湿区背景。",
        "works_well_with": ["暖白与 Greige 墙面", "浅色自然木", "平顶或模块化顶面"],
        "avoid_when": "若全屋已过于接近白色，需要通过地面、墙面或顶面增加可读层次。",
    },
    "white_marble": {
        "description": "低对比白色石纹，图形信息受控，偏向清晰而非奢华。",
        "spatial_effect": "让湿区或入口显得明亮、规整，可作为较轻的石材语言。",
        "works_well_with": ["冷白或暖白墙面", "浅色木地板", "简洁线性吊顶"],
        "avoid_when": "不宜再与高反射、复杂金色古典纹样或多处强石纹叠加。",
    },
    "warm_travertine": {
        "description": "暖米色洞石感，纹理温和、带有矿物层次和自然孔洞联想。",
        "spatial_effect": "为空间增加温润的石材重量，适合连接暖木与中性墙面。",
        "works_well_with": ["Greige、Taupe、暖白", "自然橡木", "亚麻或矿物感墙纸"],
        "avoid_when": "不宜与蜂蜜木、黄赭墙和暖奶油色全部大面积叠加。",
    },
    "dark_slate": {
        "description": "深灰板岩感，粗哑、低反射，具有明确的冷静重量。",
        "spatial_effect": "适合用作小面积或明确分区的深色基底，能压住明亮墙面。",
        "works_well_with": ["暖白与自然木", "低对比墙纸", "现代细阴影缝"],
        "avoid_when": "小且采光弱的空间不宜再配深墙、深顶或密集纹样。",
    },
    "microcement": {
        "description": "浅灰微水泥感，表面连续、低对比、低装饰性。",
        "spatial_effect": "带来当代、安静的矿物背景，可让木材或墙纸成为重点。",
        "works_well_with": ["浅木与烟熏木", "冷白、Greige、灰蓝墙面", "平顶或悬浮阴影缝"],
        "avoid_when": "若墙、顶、地都同样灰且同样哑光，需要加入温度或材质层次。",
    },
    "terrazzo": {
        "description": "暖灰细颗粒水磨石，颗粒细小、综合色温和，具有适度图形信息。",
        "spatial_effect": "为地面或局部空间提供轻快却不喧闹的节奏。",
        "works_well_with": ["暖白或灰米墙面", "浅自然木", "细织纹或纯色墙纸"],
        "avoid_when": "不宜同时使用高对比花砖、强植物墙纸或高色差木地板。",
    },
    "woodlook": {
        "description": "暖橡木色的木纹砖，以砖的模数呈现木材的线性温度。",
        "spatial_effect": "适合需要延续木色但希望保留瓷砖秩序感的区域。",
        "works_well_with": ["暖白与 Greige", "低对比矿物墙砖", "安静的现代顶面"],
        "avoid_when": "与真正高对比木地板在同一连续视域并置时，容易形成重复且不统一的木纹语言。",
    },
    "decorative_pattern": {
        "description": "弧环几何装饰花砖，重复图案清晰，是明确的视觉焦点。",
        "spatial_effect": "适合小面积或局部分区建立记忆点，其他大面需退后。",
        "works_well_with": ["纯色或低对比墙面", "安静的浅木", "平顶或低线性复杂度的顶面"],
        "avoid_when": "不要与强墙纸、强石纹和复杂拼花地板同时使用。",
    },
    "cool_finger_mosaic": {
        "description": "冷灰蓝细长马赛克，以高频竖向模数和轻微釉色差建立精细秩序。",
        "spatial_effect": "适合湿区局部墙面或壁龛成为精致焦点，面积过大时会产生强线性噪声。",
        "works_well_with": ["冷中性石灰洗", "天然软木", "深炭哑光素砖"],
        "avoid_when": "避免再与竖槽砖、密集线性墙纸或条栅吊顶并置。",
    },
    "smoke_penny_mosaic": {
        "description": "烟灰圆点马赛克，以小尺度圆形重复形成克制但明确的复古几何节奏。",
        "spatial_effect": "适合小面积湿区、壁龛或入口节点；远景读为灰色基面，近景才显圆形模数。",
        "works_well_with": ["暖土灰泥", "浅色安静木地板", "平顶或软弧灯槽"],
        "avoid_when": "不宜与棋盘砖、弧环花砖或大尺度圆弧墙纸同时使用。",
    },
    "deep_matte_monochrome": {
        "description": "深炭灰大规格哑光素砖，接缝弱、反射低，以明度而非图案建立重量。",
        "spatial_effect": "可为湿区或入口提供深色 Quiet 基底，让细模数砖或浅墙成为唯一焦点。",
        "works_well_with": ["暖土黏土灰泥", "天然软木", "冷灰蓝指形砖"],
        "avoid_when": "采光弱空间避免再叠加深色地板、深墙纸和深顶。",
    },
}

CEILING_GUIDANCE: dict[str, dict[str, str | list[str]]] = {
    "flat": {
        "description": "原顶或平顶，视觉上最轻、最安静，依靠空间比例和材料本身建立秩序。",
        "spatial_effect": "保留完整顶面与高度感，让墙面和地面承担主要材料表达。",
        "works_well_with": ["几乎所有克制的材料关系", "强焦点墙纸", "连续地面"],
        "avoid_when": "若期待顶面成为明确的光影或边界重点，它会显得过于平静。",
    },
    "perimeter_step": {
        "description": "周边跌级双眼皮，以细薄的周边层次提供精致、规整的顶面边界。",
        "spatial_effect": "让客餐厅或卧室的顶面更有收口感，但不应成为强装饰。",
        "works_well_with": ["现代极简", "温暖克制的低对比材料", "细线性墙纸"],
        "avoid_when": "不宜与多方向条纹、复杂花砖和多层装饰线同时叠加。",
    },
    "perimeter_cove": {
        "description": "周边下吊灯槽，使用柔和明暗建立顶面层次与夜间包裹感。",
        "spatial_effect": "比平顶更有氛围和边界感，适合希望公共区或卧室更柔和的方向。",
        "works_well_with": ["暖灰、Taupe、自然木", "低对比矿物砖", "安静焦点墙"],
        "avoid_when": "顶面已有复杂造型或墙地材料都很强时，会让画面过满。",
    },
    "floating_shadow_gap": {
        "description": "悬浮顶与阴影缝，用明确的暗缝表达轻薄、当代的顶面边界。",
        "spatial_effect": "强化现代秩序和留白，适合低反射、低对比的材料组合。",
        "works_well_with": ["微水泥或矿物砖", "冷白、Greige、灰蓝墙面", "浅木或烟熏木"],
        "avoid_when": "与浓重古典图案、密集装饰线和多种高反差材质混用时，语言会冲突。",
    },
    "modular_panel": {
        "description": "厨卫模块化大板顶面，以整齐模数和细缝表达清洁、理性的湿区秩序。",
        "spatial_effect": "为厨卫提供与瓷砖相容的顶面节奏，应让墙地材料决定主要情绪。",
        "works_well_with": ["素色矿物砖", "低对比石纹砖", "微水泥感砖"],
        "avoid_when": "不应把其模块感误用为干区的通用装饰语言。",
    },
}


def _tone_text(tone: str) -> str:
    return {"light": "浅色档", "mid": "中色档", "deep": "深色档"}.get(tone, tone)


def _finish_text(finish: str) -> str:
    return {"matte": "哑光，远景更安静、反射更弱", "eggshell": "蛋壳光，保留克制的细微反射"}.get(finish, finish)


def _card_for_paint(asset: dict[str, Any]) -> dict[str, Any]:
    guidance = (
        SPECIALTY_PAINT_GUIDANCE.get(asset.get("slug", ""), {})
        if asset.get("coating_system", "solid_paint") != "solid_paint"
        else PAINT_GUIDANCE.get(asset.get("slug", ""), {})
    )
    tone = _tone_text(str(asset.get("tone", "")))
    finish = _finish_text(str(asset.get("finish", "")))
    specialty = asset.get("coating_system", "solid_paint") != "solid_paint"
    visual_description = str(guidance.get("description", asset.get("name_zh", "墙漆")))
    if not specialty:
        visual_description = (
            f"{visual_description}综合色 Asset；明度、饱和度和漆面由 Scheme 参数控制。"
            if asset.get("parameter_schema")
            else f"{visual_description}{tone}，{finish}。"
        )
    return {
        "visual_description": visual_description,
        "spatial_effect": str(guidance.get("spatial_effect", "作为连续墙面背景使用，需与地面和自然光一起判断综合色。")),
        "works_well_with": guidance.get("works_well_with", []),
        "avoid_when": str(guidance.get("avoid_when", "避免把多个高对比材料同时作为焦点。")),
        "design_roles": asset.get("design_roles", ["quiet", "support"]),
    }


def _card_for_wallpaper(asset: dict[str, Any]) -> dict[str, Any]:
    use = asset.get("recommended_use", [])
    effect = (
        "可作为低强度的连续墙面层次，仍应控制相邻地面与顶面的图形信息。"
        if "full_wall" in use
        else "更适合在完整墙面承担单一焦点，相邻墙、地、顶应退后。"
    )
    if asset.get("texture_mode") == "panel_mural":
        effect = "作为完整主墙的叙事焦点，需要足够观看距离和安静的相邻表面。"
    is_mineral_wash = asset.get("id") == "wallpaper_mineral_wash_01"
    return {
        "visual_description": asset.get("description_zh", asset.get("name_zh", "墙纸")),
        "spatial_effect": (
            "在完整主墙形成明确的多综合色块焦点；远景仍有可见活动度，其他大面必须保持安静。"
            if is_mineral_wash else effect
        ),
        "works_well_with": ["低对比墙漆", "纹理对比受控的木地板或瓷砖", "线条克制的吊顶"],
        "avoid_when": (
            "避免用于用户明确要求的低对比、纯净或安静背景；也避免放在被门窗切碎的墙面，或与另一种强图案并置。"
            if is_mineral_wash
            else "避免放在被门窗切碎的墙面；避免与强石纹、高色差木纹或另一种强图案并置。"
        ),
        "design_roles": asset.get("design_roles", ["anchor", "support"]),
    }


def _card_for_guided_surface(asset: dict[str, Any], guidance_map: dict[str, dict[str, str | list[str]]]) -> dict[str, Any]:
    key_field = "preset" if asset.get("category") == "ceiling" else "material_group"
    guidance = guidance_map.get(asset.get(key_field, ""), {})
    return {
        "visual_description": str(guidance.get("description", asset.get("name_zh", "表面资产"))),
        "spatial_effect": str(guidance.get("spatial_effect", "应与相邻墙面、顶面和光线一起判断整体效果。")),
        "works_well_with": guidance.get("works_well_with", []),
        "avoid_when": str(guidance.get("avoid_when", "避免与多个同等级强图案同时使用。")),
        "design_roles": asset.get("design_roles", ["support"]),
    }


def build_asset_card(asset: dict[str, Any]) -> dict[str, Any]:
    """Return one detailed card without mutating the supplied source asset."""

    category = asset.get("category")
    if category == "wall_paint":
        aesthetic = _card_for_paint(asset)
    elif category == "wallpaper":
        aesthetic = _card_for_wallpaper(asset)
    elif category == "wood_floor":
        aesthetic = _card_for_guided_surface(asset, FLOOR_GUIDANCE)
    elif category == "tile":
        aesthetic = _card_for_guided_surface(asset, TILE_GUIDANCE)
    elif category == "ceiling":
        aesthetic = _card_for_guided_surface(asset, CEILING_GUIDANCE)
    else:
        raise ValueError(f"不支持的资产类别：{category}")

    objective_facts = deepcopy(asset)
    if objective_facts.get("parameter_schema"):
        objective_facts["default_color_srgb"] = objective_facts.pop("color_srgb", None)
        for resolved_default_field in ("tone", "finish", "roughness_mean", "roughness_range", "normal_scale"):
            objective_facts.pop(resolved_default_field, None)
    for group_field in ("family", "family_id", "perceptual_group_id"):
        objective_facts.pop(group_field, None)
    return {
        "id": asset["id"],
        "category": category,
        "name_zh": asset.get("name_zh", asset.get("name", asset["id"])),
        "name_en": asset.get("name_en", asset.get("name")),
        "brief": _brief_for(asset, aesthetic),
        "relationship_tags": asset.get("relationship_tags", []),
        "objective_facts": objective_facts,
        "preview_image": _preview_image_for(asset),
        **aesthetic,
    }


def _preview_image_for(asset: dict[str, Any]) -> dict[str, str]:
    """Return the stable project-relative visual reference for one asset card."""

    category = str(asset["category"])
    if category == "ceiling":
        depiction = "geometry_preview"
        alt = f"{asset.get('name_zh', asset['id'])}的目录几何预览；用于理解构造，不是施工节点图。"
    elif category == "wall_paint" and asset.get("parameter_schema"):
        depiction = "parameter_swatch"
        alt = f"{asset.get('name_zh', asset['id'])}的浅、中、深参数色阶预览；屏幕色不替代实体色卡。"
    else:
        depiction = "material_thumbnail"
        alt = f"{asset.get('name_zh', asset['id'])}的材质目录预览；最终选择仍需在房间实时渲染中验证。"
    return {
        "path": f"viewer/public/assets/asset-cards/{asset['id']}_preview.webp",
        "media_type": "image/webp",
        "depiction": depiction,
        "alt": alt,
    }


def _brief_for(asset: dict[str, Any], aesthetic: dict[str, Any]) -> str:
    name = asset.get("name_zh", asset.get("name", asset["id"]))
    category = asset.get("category")
    if category == "wall_paint":
        if asset.get("coating_system", "solid_paint") != "solid_paint":
            return f"{name}；{asset.get('coating_system')} 连续矿物涂层，固定综合色与表面系统。"
        if asset.get("parameter_schema"):
            return f"{name}；单一综合色 Asset，明度、饱和度与漆面是参数，不是独立资产。"
        return f"{name}；{_tone_text(str(asset.get('tone', '')))}{_finish_text(str(asset.get('finish', '')))}。"
    if category == "wallpaper":
        return f"{name}；{asset.get('description_zh', '墙面图案与微纹理资产')}"
    return f"{name}；{aesthetic['visual_description']}"


def build_asset_knowledge(
    assets: Iterable[dict[str, Any]],
    *,
    generated_at: str | None = None,
    generator: str = "asset_knowledge.py",
) -> tuple[dict[str, Any], dict[str, Any]]:
    """Build compact index and detailed cards from canonical full asset data."""

    source_assets = list(assets)
    cards = [build_asset_card(asset) for asset in source_assets]
    ids = [card["id"] for card in cards]
    if len(ids) != len(set(ids)):
        raise ValueError("资产 ID 不能重复")

    timestamp = generated_at or datetime.now(timezone.utc).isoformat()
    index = {
        "schema_version": "2.1.0",
        "generated_at": timestamp,
        "generator": generator,
        "asset_cards_file": "asset_cards.json",
        "asset_count": len(cards),
        "assets": [
            {
                "id": card["id"],
                "category": card["category"],
                "name_zh": card["name_zh"],
                "brief": card["brief"],
                "design_roles": card["design_roles"],
                "relationship_tags": card["relationship_tags"],
                "visual_description": card["visual_description"],
                "works_well_with": card["works_well_with"],
                "avoid_when": card["avoid_when"],
                **({"name_en": card["name_en"]} if card.get("name_en") else {}),
                **(
                    {"parameterized": True, "parameter_schema": card["objective_facts"]["parameter_schema"]}
                    if card["objective_facts"].get("parameter_schema")
                    else {}
                ),
            }
            for card in cards
        ],
    }
    card_library = {
        "schema_version": "1.2.0",
        "generated_at": timestamp,
        "generator": generator,
        "card_count": len(cards),
        "cards": {card["id"]: card for card in cards},
    }
    return index, card_library
