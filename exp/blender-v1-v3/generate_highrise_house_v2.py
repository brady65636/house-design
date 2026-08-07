"""Generate a Chinese slab small-highrise reference floor and one editable east unit.

Run with:
    blender --background --factory-startup --python blender/generate_highrise_house_v2.py

The existing 90 sqm v1 model is intentionally left untouched.  This file builds
the research-backed replacement as a separate artifact so the two assumptions
can be compared directly.
"""

from __future__ import annotations

import importlib.util
import json
import math
from datetime import datetime, timezone
from pathlib import Path

import bpy
from mathutils import Vector


ROOT_DIR = Path(__file__).resolve().parents[1]
OUTPUT_DIR = ROOT_DIR / "output"
PREVIEW_DIR = OUTPUT_DIR / "previews"
BLEND_PATH = OUTPUT_DIR / "house_3b2l_127_v2.blend"
GLB_PATH = OUTPUT_DIR / "house_3b2l_127_v2.glb"
SCENE_MANIFEST_PATH = OUTPUT_DIR / "scene_manifest_highrise_v2.json"
HOUSE_ID = "house_3b2l_127_v2"

HOUSE_WIDTH = 10.40
HOUSE_DEPTH = 10.60
WALL_HEIGHT = 3.00
OUTER_WALL = 0.20
INNER_WALL = 0.12
FINISH = 0.001

spec = importlib.util.spec_from_file_location(
    "house_v1_base", Path(__file__).with_name("generate_house_assets.py")
)
base = importlib.util.module_from_spec(spec)
assert spec.loader
spec.loader.exec_module(base)
base.WALL_HEIGHT = WALL_HEIGHT
base.WALL_FINISH_THICKNESS = FINISH

OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
PREVIEW_DIR.mkdir(parents=True, exist_ok=True)


ROOMS = [
    {"id": "bedroom_2", "name_zh": "次卧（南）", "type": "bedroom", "rect": [0.20, 0.20, 3.00, 4.20], "area_m2": 11.20, "orientation": "south"},
    {"id": "living_room", "name_zh": "客厅", "type": "living_room", "rect": [3.12, 0.20, 7.20, 5.50], "area_m2": 21.62, "orientation": "south"},
    {"id": "master_bedroom", "name_zh": "主卧", "type": "bedroom", "rect": [7.32, 0.20, 10.20, 5.05], "area_m2": 13.97, "orientation": "south_east"},
    {"id": "foyer", "name_zh": "玄关", "type": "foyer", "rect": [0.20, 4.32, 3.00, 6.50], "area_m2": 6.10, "orientation": "internal"},
    {"id": "pantry_laundry", "name_zh": "家政储物", "type": "service", "rect": [0.20, 6.62, 3.00, 7.48], "area_m2": 2.40, "orientation": "internal"},
    {"id": "kitchen", "name_zh": "厨房", "type": "kitchen", "rect": [0.20, 7.60, 3.00, 10.40], "area_m2": 7.84, "orientation": "north"},
    {"id": "dining_room", "name_zh": "餐厅", "type": "dining_room", "rect": [3.12, 5.62, 5.80, 8.28], "area_m2": 7.13, "orientation": "internal"},
    {"id": "guest_bath", "name_zh": "公卫", "type": "bathroom", "rect": [3.12, 8.40, 5.80, 10.40], "area_m2": 5.36, "orientation": "north"},
    {"id": "hall_storage", "name_zh": "卧室走廊", "type": "hall", "rect": [5.92, 5.62, 7.02, 10.40], "area_m2": 5.26, "orientation": "internal"},
    {"id": "master_closet", "name_zh": "主卧衣帽", "type": "closet", "rect": [7.32, 5.17, 7.98, 7.38], "area_m2": 1.46, "orientation": "internal"},
    {"id": "master_bath", "name_zh": "主卫", "type": "bathroom", "rect": [8.10, 5.17, 10.20, 7.38], "area_m2": 4.64, "orientation": "east"},
    {"id": "bedroom_3", "name_zh": "书房 / 次卧（北）", "type": "bedroom", "rect": [7.32, 7.50, 10.20, 10.40], "area_m2": 8.35, "orientation": "north_east"},
]

BALCONIES = [
    {"id": "south_balcony", "name_zh": "南向景观阳台", "rect": [3.12, -1.50, 7.20, 0.00], "area_m2": 6.12, "orientation": "south"},
    {"id": "north_utility_balcony", "name_zh": "北向生活阳台", "rect": [0.20, 10.60, 3.00, 11.80], "area_m2": 3.36, "orientation": "north"},
]

# Absolute opening coordinates along the wall axis.  They are converted to the
# relative coordinates expected by the reusable v1 wall constructor.
OPENINGS = {
    "wall_ext_south": [
        {"id": "opening_bed2_south_window", "start": 0.65, "end": 2.55, "bottom": 0.80, "top": 2.35, "kind": "window"},
        {"id": "opening_living_balcony_slider", "start": 3.35, "end": 6.97, "bottom": 0.00, "top": 2.40, "kind": "window"},
    ],
    "wall_ext_north": [
        {"id": "opening_kitchen_utility_door", "start": 0.55, "end": 2.65, "bottom": 0.00, "top": 2.40, "kind": "window"},
        {"id": "opening_guest_bath_window", "start": 3.65, "end": 4.75, "bottom": 1.35, "top": 2.35, "kind": "window"},
        {"id": "opening_bed3_north_window", "start": 7.55, "end": 9.75, "bottom": 0.80, "top": 2.35, "kind": "window"},
    ],
    "wall_ext_east": [
        {"id": "opening_master_east_window", "start": 1.10, "end": 3.70, "bottom": 0.65, "top": 2.35, "kind": "window"},
        {"id": "opening_master_bath_window", "start": 5.65, "end": 6.65, "bottom": 1.35, "top": 2.35, "kind": "window"},
        {"id": "opening_bed3_east_window", "start": 8.00, "end": 9.70, "bottom": 0.85, "top": 2.35, "kind": "window"},
    ],
    "wall_ext_west": [
        {"id": "opening_entry_door", "start": 5.05, "end": 6.10, "bottom": 0.00, "top": 2.30, "kind": "door"},
    ],
    "wall_bed2_east": [{"id": "opening_bed2_door", "start": 3.15, "end": 4.05, "bottom": 0.00, "top": 2.20, "kind": "door"}],
    "wall_foyer_east": [{"id": "opening_foyer_living", "start": 4.65, "end": 6.35, "bottom": 0.00, "top": 2.45, "kind": "passage"}],
    "wall_kitchen_east": [{"id": "opening_kitchen_door", "start": 7.45, "end": 8.45, "bottom": 0.00, "top": 2.25, "kind": "door"}],
    "wall_pantry_north": [{"id": "opening_pantry_kitchen", "start": 1.00, "end": 2.20, "bottom": 0.00, "top": 2.25, "kind": "passage"}],
    "wall_living_master": [{"id": "opening_master_door", "start": 4.00, "end": 4.90, "bottom": 0.00, "top": 2.20, "kind": "door"}],
    "wall_master_north": [{"id": "opening_master_suite", "start": 8.45, "end": 9.35, "bottom": 0.00, "top": 2.20, "kind": "door"}],
    "wall_dining_hall": [{"id": "opening_dining_hall", "start": 6.00, "end": 8.15, "bottom": 0.00, "top": 2.45, "kind": "passage"}],
    "wall_guest_hall": [{"id": "opening_guest_bath_door", "start": 8.85, "end": 9.65, "bottom": 0.00, "top": 2.20, "kind": "door"}],
    "wall_hall_bed3": [{"id": "opening_bed3_door", "start": 7.95, "end": 8.85, "bottom": 0.00, "top": 2.20, "kind": "door"}],
    "wall_hall_master": [{"id": "opening_master_hall", "start": 5.55, "end": 6.45, "bottom": 0.00, "top": 2.20, "kind": "passage"}],
    "wall_closet_bath": [{"id": "opening_master_bath_door", "start": 6.00, "end": 6.80, "bottom": 0.00, "top": 2.20, "kind": "door"}],
}

WALLS = [
    ("wall_ext_south", (0.00, 0.00), (10.40, 0.00), OUTER_WALL, ["bedroom_2", "living_room", "master_bedroom"], True),
    ("wall_ext_north", (0.00, 10.60), (10.40, 10.60), OUTER_WALL, ["kitchen", "guest_bath", "bedroom_3"], False),
    ("wall_ext_west", (0.00, 0.00), (0.00, 10.60), OUTER_WALL, ["bedroom_2", "foyer", "pantry_laundry", "kitchen"], False),
    ("wall_ext_east", (10.40, 0.00), (10.40, 10.60), OUTER_WALL, ["master_bedroom", "master_bath", "bedroom_3"], True),
    ("wall_bed2_east", (3.06, 0.20), (3.06, 4.26), INNER_WALL, ["bedroom_2", "living_room"], False),
    ("wall_bed2_north", (0.20, 4.26), (3.06, 4.26), INNER_WALL, ["bedroom_2", "foyer"], False),
    ("wall_foyer_east", (3.06, 4.26), (3.06, 6.56), INNER_WALL, ["foyer", "living_room", "dining_room"], False),
    ("wall_kitchen_east", (3.06, 6.56), (3.06, 10.40), INNER_WALL, ["pantry_laundry", "kitchen", "dining_room", "guest_bath"], False),
    ("wall_pantry_north", (0.20, 7.54), (3.06, 7.54), INNER_WALL, ["pantry_laundry", "kitchen"], False),
    ("wall_living_master", (7.26, 0.20), (7.26, 5.11), INNER_WALL, ["living_room", "master_bedroom"], True),
    ("wall_master_north", (7.26, 5.11), (10.20, 5.11), INNER_WALL, ["master_bedroom", "master_closet", "master_bath"], False),
    ("wall_dining_guest", (3.06, 8.34), (5.86, 8.34), INNER_WALL, ["dining_room", "guest_bath"], False),
    ("wall_dining_hall", (5.86, 5.56), (5.86, 8.34), INNER_WALL, ["dining_room", "hall_storage"], False),
    ("wall_guest_hall", (5.86, 8.34), (5.86, 10.40), INNER_WALL, ["guest_bath", "hall_storage"], False),
    ("wall_hall_bed3", (7.08, 7.44), (7.08, 10.40), INNER_WALL, ["hall_storage", "bedroom_3"], False),
    ("wall_bed3_south", (7.08, 7.44), (10.20, 7.44), INNER_WALL, ["bedroom_3", "master_closet", "master_bath"], False),
    ("wall_hall_master", (7.26, 5.11), (7.26, 7.44), INNER_WALL, ["hall_storage", "master_closet"], False),
    ("wall_closet_bath", (8.04, 5.11), (8.04, 7.44), INNER_WALL, ["master_closet", "master_bath"], False),
]


def build_materials() -> dict[str, bpy.types.Material]:
    paint_cream = next(asset for asset in base.PAINT_ASSETS if asset["id"] == "paint_warm_cream_matte_01")
    paint_greige = next(asset for asset in base.PAINT_ASSETS if asset["id"] == "paint_light_greige_eggshell_01")
    linen = next(asset for asset in base.WALLPAPER_ASSETS if asset["id"] == "wallpaper_linen_natural_01")
    materials = {
        paint_cream["id"]: base.make_paint_material(paint_cream),
        paint_greige["id"]: base.make_paint_material(paint_greige),
        linen["id"]: base.make_wallpaper_material(linen),
        "floor_light_oak_matte_01": base.make_wood_material("floor_light_oak_matte_01", ((0.38, 0.25, 0.12), (0.82, 0.62, 0.35))),
        "floor_honey_oak_matte_01": base.make_wood_material("floor_honey_oak_matte_01", ((0.30, 0.13, 0.045), (0.72, 0.39, 0.12))),
        "tile_warm_travertine_01": base.make_noise_material("tile_warm_travertine_01", ((0.39, 0.29, 0.18), (0.77, 0.62, 0.42)), 5.5, 0.56, 0.16),
        "tile_light_microcement_01": base.make_noise_material("tile_light_microcement_01", ((0.34, 0.36, 0.36), (0.67, 0.69, 0.67)), 8.0, 0.72, 0.10),
    }
    colors = {
        "wall_core": ((0.72, 0.72, 0.70), 0.82), "ceiling_white": ((0.86, 0.85, 0.80), 0.82),
        "glass": ((0.18, 0.36, 0.44), 0.18), "frame": ((0.08, 0.07, 0.06), 0.34),
        "door": ((0.22, 0.12, 0.055), 0.46), "label": ((0.025, 0.025, 0.025), 0.55),
        "context": ((0.31, 0.34, 0.34), 0.84), "context_floor": ((0.18, 0.20, 0.20), 0.88),
        "furniture_light": ((0.62, 0.52, 0.40), 0.60), "furniture_dark": ((0.13, 0.15, 0.14), 0.55),
        "fabric": ((0.40, 0.43, 0.40), 0.82), "sanitary": ((0.88, 0.88, 0.84), 0.34),
        "balcony_rail": ((0.12, 0.14, 0.14), 0.32),
    }
    for key, (color, roughness) in colors.items():
        materials[key] = base.make_plain_material(key, color, roughness)
    glass_shader = materials["glass"].node_tree.nodes.get("Principled BSDF")
    if glass_shader and "Transmission Weight" in glass_shader.inputs:
        glass_shader.inputs["Transmission Weight"].default_value = 0.55
    return materials


def floor_material(room: dict, materials: dict) -> bpy.types.Material:
    if room["type"] in {"kitchen", "bathroom", "service"}:
        return materials["tile_light_microcement_01"]
    if room["id"] == "master_bedroom":
        return materials["floor_honey_oak_matte_01"]
    return materials["floor_light_oak_matte_01"]


def add_surface_box(name: str, rect: list[float], z: float, thickness: float, collection, material, props: dict):
    x1, y1, x2, y2 = rect
    return base.add_box(name, (x2 - x1, y2 - y1, thickness), ((x1 + x2) / 2, (y1 + y2) / 2, z), collection, material, props)


def relative_openings(wall_id: str, start: tuple[float, float]) -> list[dict]:
    axis_offset = start[0] if abs(start[1] - next(w[2][1] for w in WALLS if w[0] == wall_id)) < 1e-6 else start[1]
    return [{**o, "start": o["start"] - axis_offset, "end": o["end"] - axis_offset} for o in OPENINGS.get(wall_id, [])]


def build_unit(collections: dict, materials: dict) -> None:
    surfaces = collections["surfaces"]
    for room in ROOMS:
        asset = floor_material(room, materials)
        add_surface_box(
            f"Floor_{room['id']}", room["rect"], 0.015, 0.03, surfaces, asset,
            {"surface_id": f"surface_hr2_floor_{room['id']}", "surface_role": "floor", "room_id": room["id"], "asset_id": asset["asset_id"], "area_m2": room["area_m2"]},
        )
        add_surface_box(
            f"Ceiling_{room['id']}", room["rect"], WALL_HEIGHT - 0.015, 0.03, surfaces, materials["ceiling_white"],
            {"surface_id": f"surface_hr2_ceiling_{room['id']}", "surface_role": "ceiling", "room_id": room["id"], "asset_id": "ceiling_white", "preview_hide": True},
        )

    for balcony in BALCONIES:
        add_surface_box(
            f"Floor_{balcony['id']}", balcony["rect"], 0.00, 0.08, surfaces, materials["tile_warm_travertine_01"],
            {"surface_id": f"surface_hr2_floor_{balcony['id']}", "surface_role": "balcony_floor", "room_id": balcony["id"], "asset_id": "tile_warm_travertine_01", "area_m2": balcony["area_m2"]},
        )

    base.WALL_FACE_OPENINGS = OPENINGS
    for wall_id, start, end, thickness, room_ids, preview_hide in WALLS:
        base.add_wall(wall_id, start, end, thickness, materials["wall_core"], collections["walls"], room_ids, relative_openings(wall_id, start), preview_hide)

    # Opening fixtures make the facade hierarchy legible in Blender and GLB.
    for wall_id, items in OPENINGS.items():
        wall = next(w for w in WALLS if w[0] == wall_id)
        start, end = wall[1], wall[2]
        horizontal = abs(start[1] - end[1]) < 1e-6
        for opening in items:
            if opening["kind"] == "passage":
                continue
            base.add_opening_fixture(
                opening["id"], "X" if horizontal else "Y", start[1] if horizontal else start[0],
                opening["start"], opening["end"], opening["bottom"], opening["top"],
                "window" if opening["kind"] == "window" else "door", collections["openings"], materials,
            )

    # Thin room-side finish planes.  One stable ID is assigned per room/wall
    # relationship; these are the future Agent's material assignment targets.
    face_index = 1
    wall_faces = []
    for wall_id, start, end, thickness, room_ids, preview_hide in WALLS:
        horizontal = abs(start[1] - end[1]) < 1e-6
        for side_index, room_id in enumerate(room_ids[:2]):
            orientation = ("north" if side_index == 0 else "south") if horizontal else ("east" if side_index == 0 else "west")
            coordinate = (start[1] + (thickness / 2 - FINISH / 2) * (1 if orientation == "north" else -1)) if horizontal else (start[0] + (thickness / 2 - FINISH / 2) * (1 if orientation == "east" else -1))
            asset_id = "wallpaper_linen_natural_01" if wall_id == "wall_living_master" and room_id == "living_room" else ("paint_light_greige_eggshell_01" if room_id in {"master_bedroom", "bedroom_3"} else "paint_warm_cream_matte_01")
            face = {
                "id": f"wall_face_hr2_{face_index:03d}", "code": f"HR2-{face_index:03d}",
                "name_zh": f"{next((r['name_zh'] for r in ROOMS if r['id'] == room_id), room_id)}墙面",
                "room_id": room_id, "host_wall_id": wall_id, "orientation": orientation,
                "axis": "X" if horizontal else "Y", "coordinate": coordinate,
                "start": min(start[0], end[0]) if horizontal else min(start[1], end[1]),
                "end": max(start[0], end[0]) if horizontal else max(start[1], end[1]),
                "asset_id": asset_id, "preview_hide": preview_hide,
            }
            base.add_wall_face(face, materials[asset_id], collections["finishes"])
            wall_faces.append(face)
            face_index += 1
    bpy.context.scene["wall_faces_json"] = json.dumps(wall_faces, ensure_ascii=False)

    # Balcony guardrails.
    for name, size, location in [
        ("SouthBalconyRail", (4.08, 0.05, 1.10), (5.16, -1.47, 0.55)),
        ("SouthBalconyRailWest", (0.05, 1.50, 1.10), (3.14, -0.75, 0.55)),
        ("SouthBalconyRailEast", (0.05, 1.50, 1.10), (7.18, -0.75, 0.55)),
        ("UtilityBalconyRail", (2.80, 0.05, 1.10), (1.60, 11.77, 0.55)),
    ]:
        base.add_box(name, size, location, collections["openings"], materials["balcony_rail"], {"asset_role": "guardrail"})


def furnishing_box(name, size, location, material, collection, room_id, role, bevel=0.04):
    return base.add_box(name, size, location, collection, material, {"room_id": room_id, "asset_role": role, "reference_only": True}, bevel=bevel)


def build_layout_references(collection, materials) -> None:
    light, dark, fabric, sanitary = materials["furniture_light"], materials["furniture_dark"], materials["fabric"], materials["sanitary"]
    # Living and dining: sofa faces an east media wall; six-seat dining table.
    furnishing_box("Ref_Sofa", (2.80, 0.95, 0.72), (4.75, 1.15, 0.38), fabric, collection, "living_room", "sofa_reference", 0.10)
    furnishing_box("Ref_CoffeeTable", (1.15, 0.58, 0.34), (4.95, 2.65, 0.19), light, collection, "living_room", "coffee_table_reference", 0.06)
    furnishing_box("Ref_TVConsole", (1.75, 0.40, 0.46), (6.92, 2.35, 0.25), dark, collection, "living_room", "media_console_reference", 0.03)
    furnishing_box("Ref_DiningTable", (1.55, 0.82, 0.74), (4.45, 6.95, 0.39), light, collection, "dining_room", "dining_table_reference", 0.05)
    for i, (x, y) in enumerate([(3.65, 6.55), (3.65, 7.35), (5.25, 6.55), (5.25, 7.35), (4.05, 6.25), (4.85, 7.65)]):
        furnishing_box(f"Ref_DiningChair_{i+1}", (0.42, 0.42, 0.82), (x, y, 0.42), fabric, collection, "dining_room", "dining_chair_reference", 0.04)

    # Beds and storage make the three-bedroom capacity immediately readable.
    for name, center, size, room in [
        ("Ref_Bed_Master", (8.72, 2.45), (1.80, 2.05), "master_bedroom"),
        ("Ref_Bed_South", (1.45, 1.90), (1.50, 2.00), "bedroom_2"),
        ("Ref_Bed_North", (8.75, 8.85), (1.35, 1.95), "bedroom_3"),
    ]:
        furnishing_box(name, (size[0], size[1], 0.48), (center[0], center[1], 0.26), fabric, collection, room, "bed_reference", 0.08)
        furnishing_box(name + "_Head", (size[0], 0.10, 0.90), (center[0], center[1] + size[1] / 2, 0.48), dark, collection, room, "headboard_reference", 0.04)
    furnishing_box("Ref_Wardrobe_Master", (0.56, 2.00, 2.35), (9.82, 4.00, 1.20), light, collection, "master_bedroom", "wardrobe_reference", 0.02)
    furnishing_box("Ref_Wardrobe_South", (1.55, 0.56, 2.35), (1.45, 3.88, 1.20), light, collection, "bedroom_2", "wardrobe_reference", 0.02)
    furnishing_box("Ref_Desk_North", (1.20, 0.55, 0.74), (8.00, 10.00, 0.39), light, collection, "bedroom_3", "desk_reference", 0.03)

    # L-shaped kitchen and two recognisable wet rooms.
    furnishing_box("Ref_KitchenCounter_W", (0.60, 2.40, 0.88), (0.52, 9.15, 0.46), light, collection, "kitchen", "kitchen_counter_reference", 0.02)
    furnishing_box("Ref_KitchenCounter_N", (2.20, 0.60, 0.88), (1.65, 10.08, 0.46), light, collection, "kitchen", "kitchen_counter_reference", 0.02)
    for prefix, room, toilet, vanity in [
        ("Guest", "guest_bath", (3.62, 9.00), (4.95, 9.95)),
        ("Master", "master_bath", (8.52, 6.65), (9.55, 5.55)),
    ]:
        furnishing_box(f"Ref_{prefix}_Toilet", (0.40, 0.68, 0.44), (toilet[0], toilet[1], 0.24), sanitary, collection, room, "toilet_reference", 0.10)
        furnishing_box(f"Ref_{prefix}_Vanity", (0.82, 0.48, 0.78), (vanity[0], vanity[1], 0.41), sanitary, collection, room, "vanity_reference", 0.04)


def build_core_context(collection, materials) -> None:
    # Public lobby between two mirrored homes.  Context is deliberately subdued:
    # it explains Chinese standard-floor circulation without becoming editable.
    base.add_box("Core_LobbyFloor", (4.40, 3.00, 0.08), (-2.20, 5.90, 0.00), collection, materials["context_floor"], {"context_only": True, "zone": "public_lobby"})
    for name, size, location in [
        ("Core_WestBoundary", (0.20, 3.00, 3.00), (-4.30, 5.90, 1.50)),
        ("Core_LobbySouth", (4.40, 0.20, 3.00), (-2.20, 4.40, 1.50)),
        ("Core_LobbyNorth", (4.40, 0.20, 3.00), (-2.20, 7.40, 1.50)),
        ("ElevatorBank", (1.80, 2.75, 3.00), (-3.35, 5.90, 1.50)),
        ("StairEnclosure", (4.20, 0.20, 3.00), (-2.20, 10.50, 1.50)),
    ]:
        base.add_box(name, size, location, collection, materials["context"], {"context_only": True, "zone": "public_core"})
    # Two elevator doors face the lobby.
    for y in (5.20, 6.60):
        base.add_box(f"ElevatorDoor_{y:.1f}", (0.05, 1.05, 2.25), (-2.43, y, 1.13), collection, materials["frame"], {"context_only": True, "asset_role": "elevator_door"})
    # Simple switchback stair north of the lobby.
    for i in range(9):
        base.add_box(f"StairStep_A_{i:02d}", (1.70, 0.28, 0.10 + i * 0.16), (-3.30, 7.68 + i * 0.29, 0.05 + i * 0.08), collection, materials["context"], {"context_only": True, "asset_role": "stair"})
        base.add_box(f"StairStep_B_{i:02d}", (1.70, 0.28, 1.54 - i * 0.16), (-1.15, 7.68 + i * 0.29, 0.77 - i * 0.08), collection, materials["context"], {"context_only": True, "asset_role": "stair"})

    # Mirrored west household is a massing reference, not a second editable unit.
    base.add_box("WestUnit_ContextFloor", (10.40, 10.60, 0.08), (-9.60, 5.30, 0.00), collection, materials["context_floor"], {"context_only": True, "zone": "mirrored_west_unit"})
    for name, size, location in [
        ("WestUnit_SouthWall", (10.40, 0.20, 3.00), (-9.60, 0.00, 1.50)),
        ("WestUnit_NorthWall", (10.40, 0.20, 3.00), (-9.60, 10.60, 1.50)),
        ("WestUnit_WestWall", (0.20, 10.60, 3.00), (-14.80, 5.30, 1.50)),
        ("WestUnit_EastWall", (0.20, 10.60, 3.00), (-4.40, 5.30, 1.50)),
        ("WestUnit_SpineA", (0.12, 7.50, 3.00), (-11.66, 3.95, 1.50)),
        ("WestUnit_SpineB", (0.12, 7.50, 3.00), (-7.54, 3.95, 1.50)),
        ("WestUnit_Cross", (10.00, 0.12, 3.00), (-9.60, 5.15, 1.50)),
    ]:
        base.add_box(name, size, location, collection, materials["context"], {"context_only": True, "zone": "mirrored_west_unit", "preview_hide": name == "WestUnit_SouthWall"})
    base.add_box("WestUnit_SouthBalcony", (4.08, 1.50, 0.08), (-9.60, -0.75, 0.00), collection, materials["tile_warm_travertine_01"], {"context_only": True, "zone": "mirrored_west_unit"})


def build_labels(collection, materials) -> None:
    for room in ROOMS:
        x1, y1, x2, y2 = room["rect"]
        label = base.add_floor_text(room["name_zh"], ((x1 + x2) / 2, (y1 + y2) / 2, 0.075), 0.23, collection, materials["label"])
        label["room_id"] = room["id"]
        label["preview_only"] = True
    for label, loc in [("公共电梯厅", (-2.10, 5.90, 0.075)), ("楼梯间", (-2.15, 9.35, 0.075)), ("镜像邻户（低模）", (-9.60, 5.30, 0.075))]:
        base.add_floor_text(label, loc, 0.28, collection, materials["label"])["preview_only"] = True


def export_glb(export_collection) -> None:
    bpy.ops.object.select_all(action="DESELECT")
    for obj in export_collection.all_objects:
        if obj.type in {"MESH", "CURVE"} and not obj.get("preview_only", False):
            obj.hide_set(False)
            obj.select_set(True)
    bpy.ops.export_scene.gltf(
        filepath=str(GLB_PATH), export_format="GLB", use_selection=True,
        export_apply=True, export_extras=True, export_yup=True,
        export_materials="PLACEHOLDER",
    )
    bpy.ops.object.select_all(action="DESELECT")


def write_manifest(wall_faces: list[dict]) -> None:
    net_area = round(sum(room["area_m2"] for room in ROOMS), 2)
    manifest = {
        "schema_version": "2.0.0", "generated_at": datetime.now(timezone.utc).isoformat(),
        "generator": "blender/generate_highrise_house_v2.py", "blender_version": bpy.app.version_string,
        "house_id": HOUSE_ID, "prototype": "中国板式小高层标准层东边户",
        "units": "meters", "up_axis": "Z", "origin": "east_unit_southwest_exterior_corner_at_floor_level",
        "area_basis": {
            "marketed_gross_area_m2": 127.0, "estimated_in_suite_building_area_m2": 104.5,
            "modeled_net_usable_area_m2": net_area, "south_balcony_area_m2": 6.12,
            "north_utility_balcony_area_m2": 3.36,
            "note_zh": "127㎡为市场常用建筑面积口径；模型净使用面积按房间矩形统计，公摊通过标准层公共核心关系表达。",
        },
        "dimensions_m": {"east_unit_width": HOUSE_WIDTH, "east_unit_depth": HOUSE_DEPTH, "wall_height": WALL_HEIGHT, "standard_floor_width": 25.20, "outer_wall": OUTER_WALL, "inner_wall": INNER_WALL},
        "planning_rules": {
            "layout": "一梯两户板式小高层（东、西两户镜像）", "active_unit": "east_edge_unit",
            "bedrooms": 3, "living_dining": 2, "bathrooms": 2,
            "south_facing_bays": ["bedroom_2", "living_room", "master_bedroom"],
            "north_service_rooms": ["kitchen", "guest_bath"], "north_secondary_bedroom": "bedroom_3",
            "public_entry_relation": "entry_door_opens_to_shared_elevator_lobby",
        },
        "rooms": [{**room, "surface_ids": {"floor": f"surface_hr2_floor_{room['id']}", "ceiling": f"surface_hr2_ceiling_{room['id']}"}, "wall_face_ids": [face["id"] for face in wall_faces if face["room_id"] == room["id"]]} for room in ROOMS],
        "balconies": BALCONIES,
        "openings": [{**opening, "host_wall_id": host} for host, openings in OPENINGS.items() for opening in openings],
        "wall_faces": wall_faces,
        "context_zones": ["public_lobby", "elevator_bank", "stair_enclosure", "mirrored_west_unit"],
        "agent_wall_assignment": {"target_field": "wall_face_id", "asset_field": "asset_id", "operation": "assign_wall_asset", "cardinality": "one_asset_per_wall_face"},
        "asset_catalog": "asset_manifest.json",
        "files": {"blend": BLEND_PATH.name, "glb": GLB_PATH.name, "standard_floor_preview": "previews/highrise_standard_floor_overview.png", "east_unit_preview": "previews/highrise_east_unit_overview.png", "validation": "validation_report_highrise_v2.json"},
        "disclaimer": "求职 Demo 概念模型；面积和结构用于产品/空间数据验证，不作为施工图或规范审图文件。",
    }
    SCENE_MANIFEST_PATH.write_text(json.dumps(manifest, ensure_ascii=False, indent=2), encoding="utf-8")


def configure_lighting() -> None:
    base.add_lighting()
    area_data = bpy.data.lights.new(name="Highrise_Area_Data", type="AREA")
    area_data.energy = 1450
    area_data.shape = "RECTANGLE"
    area_data.size = 18.0
    area_data.size_y = 12.0
    area = bpy.data.objects.new("Highrise_Area", area_data)
    bpy.context.scene.collection.objects.link(area)
    area.location = (-2.0, 4.5, 14.0)


def main() -> None:
    base.reset_file()
    scene = bpy.context.scene
    scene.name = "Chinese_Small_Highrise_Reference_Floor"
    scene["house_id"] = HOUSE_ID
    scene["schema_version"] = "2.0.0"
    scene["marketed_gross_area_m2"] = 127.0
    scene["modeled_net_usable_area_m2"] = round(sum(room["area_m2"] for room in ROOMS), 2)
    scene["prototype"] = "中国板式小高层一梯两户东边户"

    materials = build_materials()
    export_root = base.make_collection("HIGHRISE_V2_EXPORT")
    collections = {
        "surfaces": base.make_collection("UNIT_SURFACES", export_root),
        "walls": base.make_collection("UNIT_WALL_CORES", export_root),
        "finishes": base.make_collection("UNIT_WALL_FINISHES", export_root),
        "openings": base.make_collection("UNIT_OPENINGS", export_root),
        "furniture": base.make_collection("LAYOUT_REFERENCES", export_root),
        "context": base.make_collection("STANDARD_FLOOR_CONTEXT", export_root),
    }
    labels = base.make_collection("PREVIEW_LABELS")
    build_unit(collections, materials)
    build_layout_references(collections["furniture"], materials)
    build_core_context(collections["context"], materials)
    build_labels(labels, materials)
    configure_lighting()

    standard_camera = base.add_camera("Camera_StandardFloor", (-2.20, 5.10, 31.0), (-2.20, 5.10, 0.0), ortho_scale=28.0)
    unit_camera = base.add_camera("Camera_EastUnit", (15.2, -13.5, 14.8), (5.20, 5.00, 0.55), lens=52.0)

    # Hide ceilings and the cutaway facades for readable plan previews.
    for obj in export_root.all_objects:
        obj.hide_render = bool(obj.get("preview_hide", False) or obj.get("surface_role") == "ceiling")
    base.set_collection_render(labels, False)
    base.render_preview(standard_camera, PREVIEW_DIR / "highrise_standard_floor_overview.png", (1500, 900))
    base.render_preview(unit_camera, PREVIEW_DIR / "highrise_east_unit_overview.png", (1200, 900))

    # GLB contains the active east unit and the circulation context, but no text.
    export_glb(export_root)
    wall_faces = json.loads(scene["wall_faces_json"])
    write_manifest(wall_faces)

    for obj in export_root.all_objects:
        obj.hide_render = False
    bpy.ops.wm.save_as_mainfile(filepath=str(BLEND_PATH), compress=True)
    print("HIGHRISE_V2_GENERATION_COMPLETE")
    print(f"BLEND={BLEND_PATH}")
    print(f"GLB={GLB_PATH}")
    print(f"ROOMS={len(ROOMS)}")
    print(f"NET_AREA_M2={sum(room['area_m2'] for room in ROOMS):.2f}")


if __name__ == "__main__":
    main()
