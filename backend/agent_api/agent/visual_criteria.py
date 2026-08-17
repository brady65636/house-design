"""Shared visual-review criteria for the production Critic and outcome evals."""

from __future__ import annotations

from typing import Final


VISUAL_CRITERIA: Final[tuple[dict[str, str], ...]] = (
    {
        "criterion_id": "intent_matches_image",
        "text": "用户说想要什么感觉，最终画面就应该像什么感觉。例如用户要“明亮、安静”，画面不能又暗又花。",
    },
    {
        "criterion_id": "adjacent_floor_color_harmony",
        "text": "从门口同时看见两个相连房间时，两边地板颜色不能明显打架，例如一边黄橙、一边蓝灰。",
    },
    {
        "criterion_id": "connected_floor_continuity",
        "text": "客厅、餐厅、走廊连在一起时，地面不能像三个互不相关的样板间。",
    },
    {
        "criterion_id": "strong_pattern_competition",
        "text": "同一张画面里，不能同时出现两种以上很抢眼的图案，例如花墙纸再配强石纹或花砖。",
    },
    {
        "criterion_id": "wallpaper_wall_integrity",
        "text": "图案明显的墙纸应该放在比较完整的墙上，不能被门窗切得支离破碎。",
    },
    {
        "criterion_id": "wall_floor_color_relation",
        "text": "墙面和地面的颜色放在一起不能互相显脏，例如墙被衬得发粉，或者木地板被衬得过黄。",
    },
    {
        "criterion_id": "ceiling_visual_priority",
        "text": "除非用户特别要求突出吊顶，否则人进入房间后不应该第一眼只注意到天花板。",
    },
    {
        "criterion_id": "same_room_wall_family",
        "text": "同一个房间的几面墙不能像随手试了好几个色卡，颜色之间要看得出属于同一套搭配。",
    },
    {
        "criterion_id": "small_room_complexity",
        "text": "面积较小的房间不能同时使用深色墙、深色地面和明显图案，否则容易显得拥挤。",
    },
    {
        "criterion_id": "corridor_stripe_direction",
        "text": "狭长走廊不能用很多横向强条纹把空间切成一段一段，显得更短、更碎。",
    },
    {
        "criterion_id": "single_wall_temperature_consistency",
        "text": "同一面墙不能一部分是明显暖色、一部分是明显冷色，却没有清楚的分区理由。",
    },
    {
        "criterion_id": "wood_tile_transition",
        "text": "木地板与石材或瓷砖相接时，最好能找到一种共同颜色，例如灰、米色或棕色，不能完全各说各话。",
    },
)


def numbered_visual_criteria() -> str:
    """Render the shared criteria in the plain-language format used by Critic."""
    return "\n".join(
        f"{index}. {criterion['text']}"
        for index, criterion in enumerate(VISUAL_CRITERIA, start=1)
    )
