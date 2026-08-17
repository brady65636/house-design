"""Build the spacious v4 apartment from the real Heda Yun Kuo 135 sqm plan.

The public drawing is used as a proportional reference.  The 7.6 m south
frontage, 14.4 sqm open balcony, 39 sqm advertised public zone, 20 sqm master
suite and 96.53 sqm published internal area are explicit calibration anchors.

The dashed convertible room is absorbed into one continuous living room.
All three formal bedrooms retain complete walls and doors for realistic fit-out.
"""

from __future__ import annotations

import importlib.util
import json
import math
import shutil
from datetime import datetime, timezone
from pathlib import Path

import bpy


ROOT_DIR = Path(__file__).resolve().parents[1]
OUTPUT_DIR = ROOT_DIR / "output"
PREVIEW_DIR = OUTPUT_DIR / "previews"
REFERENCE_PATH = OUTPUT_DIR / "research" / "spacious_floorplans" / "heda_135_ldkg.jpg"
BLEND_PATH = OUTPUT_DIR / "house_spacious_yunkuo_135_v4.blend"
GLB_PATH = OUTPUT_DIR / "house_spacious_yunkuo_135_v4.glb"
MANIFEST_PATH = OUTPUT_DIR / "scene_manifest_spacious_v4.json"
ACTIVE_SCENE_MANIFEST_PATH = OUTPUT_DIR / "scene_manifest.json"
ROOT_SCENE_MANIFEST_PATH = ROOT_DIR / "scene_manifest.json"
ROOT_ASSET_MANIFEST_PATH = ROOT_DIR / "asset_manifest.json"
ROOT_ASSET_CARDS_PATH = ROOT_DIR / "asset_cards.json"
VIEWER_MODELS_DIR = ROOT_DIR / "viewer" / "public" / "models"
HOUSE_ID = "house_spacious_yunkuo_135_v4"
GEOMETRY_REVISION = "hard-finish-realism-pass-v5-wall-coverage"

WIDTH = 13.40
DEPTH = 9.80
PUBLIC_FRONTAGE = 7.60
BALCONY_DEPTH = 1.90
WALL_HEIGHT = 3.10
OUTER_WALL = 0.20
INNER_WALL = 0.12
FINISH = 0.001
SURFACE_UNDERLAY = 0.11
WET_ROOM_IDS = {"kitchen", "guest_bath", "master_bath"}
DOOR_OPEN_ANGLES_DEG = {
    "opening_entry_door": -82.0,
    "opening_bed3_door": 82.0,
    "opening_master_suite_door": -82.0,
    "opening_master_dressing": 82.0,
    "opening_master_bath_door": 82.0,
    "opening_bed2_door": 82.0,
    "opening_guest_bath_door": 82.0,
}

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
    {
        "id": "open_public",
        "name_zh": "完整横厅客厅",
        "type": "living_room",
        "rect": [3.20, 0.20, 9.85, 6.35],
        # The public zone is L-shaped: this short circulation bay reaches the
        # guest-bath door.  Keeping only the main rectangle previously left a
        # real floor/ceiling gap and made wall_face_real4_028 look detached.
        "topology_rects": [[3.20, 0.20, 9.85, 6.35], [5.30, 6.35, 7.25, 7.20]],
        "orientation": "south",
    },
    {"id": "bedroom_3", "name_zh": "南次卧", "type": "bedroom", "rect": [0.20, 0.20, 3.05, 4.35], "orientation": "south_west"},
    {"id": "foyer", "name_zh": "玄关", "type": "foyer", "rect": [0.20, 4.65, 3.05, 6.35], "orientation": "west"},
    {"id": "dining_room", "name_zh": "餐厅", "type": "dining_room", "rect": [0.20, 6.55, 3.05, 9.60], "orientation": "north"},
    {"id": "kitchen", "name_zh": "玻璃移门厨房", "type": "kitchen", "rect": [3.25, 6.65, 5.20, 9.60], "orientation": "north"},
    {"id": "guest_bath", "name_zh": "公卫", "type": "bathroom", "rect": [5.40, 7.20, 7.15, 9.60], "orientation": "north"},
    {"id": "bedroom_2", "name_zh": "北次卧", "type": "bedroom", "rect": [7.35, 6.55, 10.35, 9.60], "orientation": "north"},
    {"id": "master_bedroom", "name_zh": "主卧", "type": "bedroom", "rect": [10.05, 0.20, 13.20, 4.15], "orientation": "south_east"},
    {"id": "master_dressing", "name_zh": "主卧衣帽间", "type": "dressing", "rect": [10.05, 4.35, 11.85, 6.35], "orientation": "internal"},
    {"id": "master_bath", "name_zh": "主卫", "type": "bathroom", "rect": [12.05, 4.35, 13.20, 6.35], "orientation": "east"},
]
for room in ROOMS:
    rects = room.get("topology_rects", [room["rect"]])
    room["area_m2"] = round(sum((x2 - x1) * (y2 - y1) for x1, y1, x2, y2 in rects), 2)

BALCONIES = [
    {
        "id": "south_panorama_balcony",
        "name_zh": "7.6米南向开放阳台",
        "rect": [2.70, -BALCONY_DEPTH, 10.30, 0.00],
        "area_m2": round(PUBLIC_FRONTAGE * BALCONY_DEPTH, 2),
        "orientation": "south",
    }
]

OPENINGS = {
    "wall_ext_south": [
        {"id": "opening_bed3_south_window", "start": 0.45, "end": 2.85, "bottom": 0.72, "top": 2.46, "kind": "window"},
        {"id": "opening_public_panorama_slider", "start": 3.28, "end": 9.82, "bottom": 0.00, "top": 2.55, "kind": "window"},
        {"id": "opening_master_south_window", "start": 10.08, "end": 13.05, "bottom": 0.55, "top": 2.48, "kind": "window"},
    ],
    "wall_ext_west": [
        {"id": "opening_entry_door", "start": 4.78, "end": 5.92, "bottom": 0.00, "top": 2.36, "kind": "door"},
        {"id": "opening_dining_west_window", "start": 7.00, "end": 9.15, "bottom": 0.76, "top": 2.45, "kind": "window"},
    ],
    "wall_ext_north": [
        {"id": "opening_dining_north_window", "start": 0.55, "end": 2.75, "bottom": 0.80, "top": 2.45, "kind": "window"},
        {"id": "opening_kitchen_north_window", "start": 3.45, "end": 5.00, "bottom": 1.02, "top": 2.42, "kind": "window"},
        {"id": "opening_guest_bath_window", "start": 5.72, "end": 6.72, "bottom": 1.32, "top": 2.40, "kind": "window"},
        {"id": "opening_bed2_north_window", "start": 7.62, "end": 10.02, "bottom": 0.72, "top": 2.46, "kind": "window"},
    ],
    "wall_ext_east": [
        {"id": "opening_master_bath_east_window", "start": 4.70, "end": 5.65, "bottom": 1.32, "top": 2.42, "kind": "window"},
    ],
    "wall_bed3_east": [
        {"id": "opening_bed3_door", "start": 3.35, "end": 4.25, "bottom": 0.00, "top": 2.24, "kind": "door"},
    ],
    "wall_master_west": [
        {"id": "opening_master_suite_door", "start": 5.25, "end": 6.18, "bottom": 0.00, "top": 2.30, "kind": "door"},
    ],
    "wall_master_split": [
        {"id": "opening_master_dressing", "start": 10.72, "end": 11.62, "bottom": 0.00, "top": 2.28, "kind": "door"},
    ],
    "wall_master_service_split": [
        {"id": "opening_master_bath_door", "start": 5.26, "end": 6.12, "bottom": 0.00, "top": 2.24, "kind": "door"},
    ],
    "wall_bed2_south": [
        {"id": "opening_bed2_door", "start": 7.56, "end": 8.46, "bottom": 0.00, "top": 2.24, "kind": "door"},
    ],
    "wall_guest_bath_south": [
        {"id": "opening_guest_bath_door", "start": 5.54, "end": 6.38, "bottom": 0.00, "top": 2.20, "kind": "door"},
    ],
    "wall_kitchen_south": [
        {"id": "opening_kitchen_glass_slider", "start": 3.34, "end": 5.12, "bottom": 0.00, "top": 2.44, "kind": "window"},
    ],
}

WALLS = [
    ("wall_ext_south", (0.00, 0.00), (WIDTH, 0.00), OUTER_WALL, ["bedroom_3", "open_public"], True),
    ("wall_ext_west", (0.00, 0.00), (0.00, DEPTH), OUTER_WALL, ["bedroom_3", "foyer"], False),
    ("wall_ext_north", (0.00, DEPTH), (WIDTH, DEPTH), OUTER_WALL, ["dining_room", "kitchen"], False),
    ("wall_ext_east", (WIDTH, 0.00), (WIDTH, DEPTH), OUTER_WALL, ["master_bedroom", "master_bath"], True),
    ("wall_bed3_east", (3.15, 0.00), (3.15, 4.50), INNER_WALL, ["bedroom_3", "open_public"], False),
    ("wall_bed3_north", (0.00, 4.50), (3.15, 4.50), INNER_WALL, ["bedroom_3", "foyer"], False),
    ("wall_master_west", (9.95, 0.00), (9.95, 6.45), INNER_WALL, ["open_public", "master_bedroom"], False),
    ("wall_master_split", (9.95, 4.25), (WIDTH, 4.25), INNER_WALL, ["master_bedroom", "master_dressing"], False),
    ("wall_master_service_split", (11.95, 4.25), (11.95, 6.45), INNER_WALL, ["master_dressing", "master_bath"], False),
    ("wall_master_service_north", (10.45, 6.45), (WIDTH, 6.45), INNER_WALL, ["master_dressing", "bedroom_2"], False),
    ("wall_bed2_south", (7.25, 6.45), (10.45, 6.45), INNER_WALL, ["bedroom_2", "open_public"], False),
    ("wall_bed2_west", (7.25, 6.45), (7.25, DEPTH), INNER_WALL, ["bedroom_2", "guest_bath"], False),
    ("wall_bed2_east", (10.45, 6.45), (10.45, DEPTH), INNER_WALL, ["bedroom_2", "master_dressing"], False),
    ("wall_guest_bath_south", (5.30, 7.10), (7.25, 7.10), INNER_WALL, ["guest_bath", "open_public"], False),
    ("wall_guest_bath_west", (5.30, 7.10), (5.30, DEPTH), INNER_WALL, ["guest_bath", "kitchen"], False),
    ("wall_kitchen_south", (3.15, 6.55), (5.30, 6.55), INNER_WALL, ["kitchen", "open_public"], False),
    ("wall_kitchen_west", (3.15, 6.55), (3.15, DEPTH), INNER_WALL, ["kitchen", "dining_room"], False),
]

# Preserve the published stable wall-face IDs while correcting two bad legacy
# room/host-wall pairings.  The old generator silently expanded a non-overlap
# to the full wall, which put 020 in the master service zone and 026 inside the
# north bedroom.  These IDs now point at the physically adjacent missing sides.
WALL_FACE_SOURCE_OVERRIDES = {
    20: "wall_ext_north",       # bedroom_2 north exterior wall
    26: "wall_master_west",     # master_dressing west wall
}

# Long exterior walls can border more than the two rooms stored in the legacy
# WALLS tuple.  Append the omitted room-facing finishes after the published
# 001-034 range so every existing Scheme target keeps its stable ID.
ADDITIONAL_WALL_FACE_SOURCES = [
    (35, "wall_ext_west", "dining_room"),
    (36, "wall_ext_south", "master_bedroom"),
    (37, "wall_ext_north", "guest_bath"),
]


def build_materials():
    # Keep the full approved asset library inside the active 135 m² source
    # file. Only the currently assigned materials are exported in the house
    # GLB; the other data-blocks remain available for Blender authoring and
    # correspond one-to-one with the runtime catalog IDs.
    mats = {
        asset["id"]: base.make_paint_material(asset)
        for asset in base.PAINT_ASSETS
    }
    mats.update({
        asset["id"]: base.make_wallpaper_material(asset)
        for asset in base.WALLPAPER_ASSETS
    })
    mats.update({
        asset["id"]: base.make_surface_pbr_material(asset)
        for asset in [*base.FLOOR_ASSETS, *base.TILE_ASSETS]
    })
    plain = {
        "wall_core": ((0.64, 0.62, 0.58), .90), "ceiling_white": ((.86, .85, .80), .82),
        "glass": ((.18, .36, .44), .18), "frame": ((.08, .07, .06), .34),
        "door": ((.22, .12, .055), .46), "label": ((.025, .025, .025), .55),
        "fabric": ((.45, .47, .43), .88), "fabric_light": ((.75, .72, .65), .92),
        "wood_light": ((.58, .40, .22), .68), "wood_dark": ((.16, .11, .08), .58),
        "metal": ((.09, .10, .09), .35), "sanitary": ((.90, .90, .86), .34),
        "rail": ((.10, .11, .11), .32), "green": ((.16, .28, .14), .80),
        "catalog_base": ((.16, .17, .18), .78), "label_light": ((.82, .82, .78), .55),
        "ceiling_panel": ((.78, .79, .76), .66), "ceiling_shadow_gap": ((.035, .038, .037), .96),
        "ceiling_cove_light": ((.98, .78, .48), .55),
        "threshold_stone": ((.50, .47, .42), .72),
    }
    for key, (color, roughness) in plain.items():
        mats[key] = base.make_plain_material(key, color, roughness)
    shader = mats["glass"].node_tree.nodes.get("Principled BSDF")
    if shader and "Transmission Weight" in shader.inputs:
        shader.inputs["Transmission Weight"].default_value = .62
    return mats


def add_surface(name, rect, z, thickness, collection, material, props):
    x1, y1, x2, y2 = rect
    obj = base.add_box(name, (x2-x1, y2-y1, thickness), ((x1+x2)/2, (y1+y2)/2, z), collection, material, props)
    uv_layer = obj.data.uv_layers.active or obj.data.uv_layers.new(name="SurfaceMetricUV")
    for polygon in obj.data.polygons:
        for loop_index in polygon.loop_indices:
            vertex_index = obj.data.loops[loop_index].vertex_index
            world = obj.matrix_world @ obj.data.vertices[vertex_index].co
            uv_layer.data[loop_index].uv = (world.x, world.y)
    obj["uv_scale"] = "metric_xy_meters"
    return obj


def expand_rect(rect, amount):
    """Extend finish slabs beneath walls without changing their design area."""
    x1, y1, x2, y2 = rect
    return [x1 - amount, y1 - amount, x2 + amount, y2 + amount]


def build_architectural_details(collection, mats):
    """Add thin construction joints that keep floor transitions from reading as gaps."""
    for host_wall_id, start, end, _thickness, _rooms, _hide in WALLS:
        horizontal = abs(start[1] - end[1]) < 1e-6
        wall_coordinate = start[1] if horizontal else start[0]
        for opening in OPENINGS.get(host_wall_id, []):
            if float(opening.get("bottom", 0.0)) > 0.001:
                continue
            along_start = float(opening["start"])
            along_end = float(opening["end"])
            along_length = along_end - along_start
            if horizontal:
                size = (along_length, 0.18, 0.012)
                location = ((along_start + along_end) / 2, wall_coordinate, 0.036)
            else:
                size = (0.18, along_length, 0.012)
                location = (wall_coordinate, (along_start + along_end) / 2, 0.036)
            base.add_box(
                f"Threshold_{opening['id']}",
                size,
                location,
                collection,
                mats["threshold_stone"],
                {
                    "asset_role": "architectural_threshold",
                    "opening_id": opening["id"],
                    "host_wall_id": host_wall_id,
                    "hard_finish_detail": True,
                },
                bevel=0.002,
            )


def build_glass_guardrail(collection, mats):
    """Replace opaque balcony blocks with a buildable glass-and-metal assembly."""
    frame_props = {
        "asset_role": "guardrail_frame",
        "opening_id": "balcony_guardrail",
        "opening_type": "window",
        "hard_finish_detail": True,
        "detail_group": "guardrail_frame_architecture",
    }
    glass_props = {
        "asset_role": "guardrail_glass",
        "opening_id": "balcony_guardrail",
        "opening_type": "window",
        "hard_finish_detail": True,
        "detail_group": "guardrail_balcony_glass",
    }

    def add_run(axis, fixed, start, end):
        run_length = end - start
        panel_count = max(1, math.ceil(run_length / 1.18))
        module = run_length / panel_count
        for index in range(panel_count + 1):
            along = start + index * module
            location = (along, fixed, 0.55) if axis == "X" else (fixed, along, 0.55)
            base.add_box(
                f"BalconyGuardrail_frame_post_{axis}_{index}_{start:.2f}",
                (0.04, 0.04, 1.02),
                location,
                collection,
                mats["rail"],
                frame_props,
                bevel=0.003,
            )
        for index in range(panel_count):
            along_start = start + index * module + 0.035
            along_end = start + (index + 1) * module - 0.035
            panel_length = along_end - along_start
            if axis == "X":
                size = (panel_length, 0.012, 0.83)
                location = ((along_start + along_end) / 2, fixed, 0.575)
            else:
                size = (0.012, panel_length, 0.83)
                location = (fixed, (along_start + along_end) / 2, 0.575)
            base.add_box(
                f"BalconyGuardrail_{axis}_{index}_glass",
                size,
                location,
                collection,
                mats["glass"],
                glass_props,
                bevel=0.001,
            )
        top_size = (run_length + 0.04, 0.055, 0.055) if axis == "X" else (0.055, run_length + 0.04, 0.055)
        top_location = ((start + end) / 2, fixed, 1.085) if axis == "X" else (fixed, (start + end) / 2, 1.085)
        base.add_box(
            f"BalconyGuardrail_frame_top_{axis}_{start:.2f}",
            top_size,
            top_location,
            collection,
            mats["rail"],
            frame_props,
            bevel=0.006,
        )

    add_run("X", -1.87, 2.72, 10.28)
    add_run("Y", 2.72, -1.87, 0.0)
    add_run("Y", 10.28, -1.87, 0.0)
    merge_meshes_by_property(collection, "detail_group")


def pose_door_leaf(leaf, wall_axis, wall_coord, along_start, angle_deg):
    """Rotate the existing reference leaf around its hinge without adding geometry."""
    angle = angle_deg * 3.141592653589793 / 180.0
    leaf_width = max(leaf.dimensions.x, leaf.dimensions.y)
    if wall_axis == "X":
        leaf.location.x = along_start + 0.05 + (leaf_width / 2) * math.cos(angle)
        leaf.location.y = wall_coord + (leaf_width / 2) * math.sin(angle)
    else:
        leaf.location.x = wall_coord - (leaf_width / 2) * math.sin(angle)
        leaf.location.y = along_start + 0.05 + (leaf_width / 2) * math.cos(angle)
    leaf.rotation_euler.z = angle
    leaf["door_pose"] = "open_reference"
    leaf["open_angle_deg"] = angle_deg


def merge_meshes_by_property(collection, property_name):
    """Join disjoint wall pieces while preserving one stable target per Mesh."""
    groups = {}
    for obj in list(collection.objects):
        value = obj.get(property_name)
        if obj.type == "MESH" and isinstance(value, str):
            groups.setdefault(value, []).append(obj)
    for value, objects in groups.items():
        if len(objects) < 2:
            continue
        bpy.ops.object.select_all(action="DESELECT")
        active = objects[0]
        for obj in objects:
            obj.select_set(True)
        bpy.context.view_layer.objects.active = active
        bpy.ops.object.join()
        active.name = value
        active[property_name] = value


def wall_openings(wall_id, start, end):
    horizontal = abs(start[1] - end[1]) < 1e-6
    offset = min(start[0], end[0]) if horizontal else min(start[1], end[1])
    return [{**item, "start": item["start"]-offset, "end": item["end"]-offset} for item in OPENINGS.get(wall_id, [])]


def room_side_geometry(room_id, start, end):
    """Resolve the actual room-facing side instead of trusting list order."""
    room = next(item for item in ROOMS if item["id"] == room_id)
    horizontal = abs(start[1] - end[1]) < 1e-6
    wall_coordinate = start[1] if horizontal else start[0]
    candidates = []
    for x1, y1, x2, y2 in room.get("topology_rects", [room["rect"]]):
        if horizontal:
            segment_start = max(min(start[0], end[0]), x1)
            segment_end = min(max(start[0], end[0]), x2)
            distance = abs((y1 + y2) / 2 - wall_coordinate)
            positive_side = (y1 + y2) / 2 > wall_coordinate
        else:
            segment_start = max(min(start[1], end[1]), y1)
            segment_end = min(max(start[1], end[1]), y2)
            distance = abs((x1 + x2) / 2 - wall_coordinate)
            positive_side = (x1 + x2) / 2 > wall_coordinate
        if segment_end - segment_start >= 0.05:
            candidates.append((distance, positive_side, segment_start, segment_end))
    if not candidates:
        raise ValueError(f"Room {room_id} does not intersect wall segment {start}->{end}")
    _distance, positive_side, segment_start, segment_end = min(candidates, key=lambda item: item[0])
    orientation = (
        ("north" if positive_side else "south")
        if horizontal
        else ("east" if positive_side else "west")
    )
    return orientation, (1 if positive_side else -1), segment_start, segment_end


def add_cylinder(name, radius, height, location, collection, material, props=None, vertices=20):
    bpy.ops.mesh.primitive_cylinder_add(vertices=vertices, radius=radius, depth=height, location=location)
    obj = bpy.context.object
    obj.name = name
    base.move_to_collection(obj, collection)
    base.assign_material(obj, material)
    for key, value in (props or {}).items():
        obj[key] = value
    return obj


def ref_box(name, size, location, collection, material, room, role, bevel=.035):
    return base.add_box(name, size, location, collection, material, {"room_id": room, "asset_role": role, "reference_only": True}, bevel=bevel)


def build_bed(prefix, center, width, length, room, collection, mats):
    x, y = center
    ref_box(prefix+"_base", (width, length, .18), (x, y, .13), collection, mats["wood_dark"], room, "bed_frame", .05)
    ref_box(prefix+"_mattress", (width-.06, length-.10, .24), (x, y-.02, .35), collection, mats["fabric_light"], room, "mattress", .09)
    ref_box(prefix+"_headboard", (width+.12, .10, .82), (x, y+length/2-.03, .52), collection, mats["fabric"], room, "headboard", .06)
    ref_box(prefix+"_duvet", (width-.16, length*.56, .08), (x, y-length*.12, .52), collection, mats["fabric"], room, "duvet", .05)


def build_chair(prefix, x, y, collection, mats, room, rotate=False):
    seat = ref_box(prefix+"_seat", (.42, .42, .08), (x, y, .47), collection, mats["wood_light"], room, "chair", .025)
    back = ref_box(prefix+"_back", (.42, .07, .48), (x, y+.18, .73), collection, mats["fabric"], room, "chair", .025)
    if rotate:
        seat.rotation_euler[2] = 1.5708
        back.rotation_euler[2] = 1.5708
    for index, (dx, dy) in enumerate([(-.16,-.16),(.16,-.16),(-.16,.16),(.16,.16)]):
        add_cylinder(prefix+f"_leg_{index}", .018, .43, (x+dx,y+dy,.215), collection, mats["metal"], {"room_id":room,"reference_only":True,"asset_role":"chair_leg"}, 12)


def build_furniture(collection, mats):
    # Keep the two expanded south bedrooms visually open by placing each
    # headboard against a complete north wall instead of floating the bed.
    build_bed("MasterBed", (11.86, 3.10), 1.80, 2.05, "master_bedroom", collection, mats)
    build_bed("Bedroom2Bed", (8.82, 8.25), 1.50, 2.00, "bedroom_2", collection, mats)
    build_bed("Bedroom3Bed", (1.90, 3.37), 1.50, 2.00, "bedroom_3", collection, mats)
    ref_box("MasterWardrobe", (.55, 1.80, 2.36), (10.82, 5.30, 1.19), collection, mats["wood_light"], "master_dressing", "wardrobe", .02)
    ref_box("Bedroom2Wardrobe", (1.55, .55, 2.30), (9.35, 6.87, 1.16), collection, mats["wood_light"], "bedroom_2", "wardrobe", .02)
    ref_box("Bedroom3Wardrobe", (.52, 1.55, 2.30), (.48, 3.15, 1.16), collection, mats["wood_light"], "bedroom_3", "wardrobe", .02)

    # Normal-size 3.0 m sofa; spaciousness comes from the room, not underscaling.
    ref_box("SofaSeat", (.82, 3.00, .18), (5.15, 2.40, .42), collection, mats["fabric_light"], "open_public", "sofa", .08)
    ref_box("SofaBack", (.16, 3.00, .68), (4.81, 2.40, .70), collection, mats["fabric"], "open_public", "sofa", .07)
    for y in (1.00, 3.80):
        ref_box(f"SofaArm_{y}", (.82, .15, .46), (5.15, y, .51), collection, mats["fabric"], "open_public", "sofa", .05)
    ref_box("CoffeeTableTop", (1.40, .72, .07), (6.90, 2.40, .42), collection, mats["wood_light"], "open_public", "coffee_table", .05)
    for index, (x,y) in enumerate([(6.42,2.18),(7.38,2.62)]):
        add_cylinder(f"CoffeeLeg_{index}", .025, .38, (x,y,.20), collection, mats["metal"], {"room_id":"open_public","reference_only":True,"asset_role":"coffee_table_leg"}, 12)
    ref_box("TVConsole", (.36, 2.30, .42), (9.62, 2.40, .24), collection, mats["wood_dark"], "open_public", "media_console", .03)
    add_cylinder("LivingSideTable", .28, .48, (5.70,.70,.24), collection, mats["wood_dark"], {"room_id":"open_public","reference_only":True,"asset_role":"side_table"}, 24)
    ref_box("LivingBench", (1.35, .48, .42), (8.15, 4.72, .24), collection, mats["fabric"], "open_public", "bench", .08)

    ref_box("DiningTop", (1.75, .88, .08), (1.72, 7.92, .76), collection, mats["wood_light"], "dining_room", "dining_table", .04)
    for index, (dx,dy) in enumerate([(-.70,-.30),(.70,-.30),(-.70,.30),(.70,.30)]):
        add_cylinder(f"DiningTableLeg_{index}", .025, .72, (1.72+dx,7.92+dy,.36), collection, mats["metal"], {"room_id":"dining_room","reference_only":True,"asset_role":"table_leg"}, 12)
    for index, (x,y) in enumerate([(0.70,7.43),(0.70,8.41),(2.74,7.43),(2.74,8.41),(1.25,7.15),(2.18,8.69)]):
        build_chair(f"DiningChair_{index}", x, y, collection, mats, "dining_room")

    ref_box("KitchenCounterNorth", (1.70, .58, .88), (4.22, 9.22, .45), collection, mats["wood_light"], "kitchen", "kitchen_counter", .02)
    ref_box("KitchenCounterWest", (.58, 1.72, .88), (3.55, 8.08, .45), collection, mats["wood_light"], "kitchen", "kitchen_counter", .02)
    ref_box("EntryCabinet", (.42, 1.45, 2.25), (.45, 5.38, 1.14), collection, mats["wood_light"], "foyer", "entry_storage", .02)

    ref_box("GuestToilet", (.40,.66,.42), (5.82,8.88,.23), collection, mats["sanitary"], "guest_bath", "toilet", .10)
    ref_box("GuestVanity", (.78,.42,.74), (6.63,9.22,.39), collection, mats["sanitary"], "guest_bath", "vanity", .04)
    ref_box("MasterToilet", (.40,.66,.42), (12.45,5.55,.23), collection, mats["sanitary"], "master_bath", "toilet", .10)
    ref_box("MasterVanity", (.72,.42,.74), (12.80,4.72,.39), collection, mats["sanitary"], "master_bath", "vanity", .04)


def build_model(collections, mats):
    for room in ROOMS:
        floor_asset = default_floor_asset(room["type"])
        design_rects = room.get("topology_rects", [room["rect"]])
        for rect_index, design_rect in enumerate(design_rects):
            underlay_rect = expand_rect(design_rect, SURFACE_UNDERLAY)
            suffix = "" if rect_index == 0 else f"_zone_{rect_index + 1}"
            underlay_props = {"surface_underlay_m": SURFACE_UNDERLAY, "design_rect_m": json.dumps(design_rect)}
            add_surface("Floor_"+room["id"]+suffix, underlay_rect, .015, .03, collections["surfaces"], mats[floor_asset], {"surface_id":f"surface_real4_floor_{room['id']}","surface_role":"floor","room_id":room["id"],"asset_id":floor_asset,"area_m2":room["area_m2"],**underlay_props})
            add_surface("Ceiling_"+room["id"]+suffix, underlay_rect, WALL_HEIGHT-.015, .03, collections["surfaces"], mats["ceiling_white"], {"surface_id":f"surface_real4_ceiling_{room['id']}","surface_role":"ceiling","room_id":room["id"],"asset_id":"ceiling_white","preview_hide":True,**underlay_props})
    for balcony in BALCONIES:
        add_surface("Floor_"+balcony["id"], balcony["rect"], 0, .08, collections["surfaces"], mats["tile_warm_travertine_01"], {"surface_id":f"surface_real4_floor_{balcony['id']}","surface_role":"balcony_floor","room_id":balcony["id"],"asset_id":"tile_warm_travertine_01","area_m2":balcony["area_m2"]})

    base.WALL_FACE_OPENINGS = OPENINGS
    for wall_id, start, end, thickness, rooms, hide in WALLS:
        base.add_wall(wall_id, start, end, thickness, mats["wall_core"], collections["walls"], rooms, wall_openings(wall_id,start,end), hide)
        horizontal = abs(start[1]-end[1]) < 1e-6
        for opening in OPENINGS.get(wall_id, []):
            wall_axis = "X" if horizontal else "Y"
            wall_coord = start[1] if horizontal else start[0]
            leaf = base.add_opening_fixture(opening["id"], wall_axis, wall_coord, opening["start"], opening["end"], opening["bottom"], opening["top"], "window" if opening["kind"] == "window" else "door", collections["openings"], mats)
            if leaf is not None and opening["id"] in DOOR_OPEN_ANGLES_DEG:
                pose_door_leaf(leaf, wall_axis, wall_coord, opening["start"], DOOR_OPEN_ANGLES_DEG[opening["id"]])
            if hide:
                for fixture in collections["openings"].objects:
                    if fixture.get("opening_id") == opening["id"]:
                        fixture["preview_hide"] = True

    faces = []
    index = 1
    for wall_id, start, end, thickness, rooms, hide in WALLS:
        horizontal = abs(start[1]-end[1]) < 1e-6
        for room_id in rooms[:2]:
            source_wall_id = WALL_FACE_SOURCE_OVERRIDES.get(index, wall_id)
            source = next(item for item in WALLS if item[0] == source_wall_id)
            _source_id, source_start, source_end, source_thickness, _source_rooms, source_hide = source
            source_horizontal = abs(source_start[1]-source_end[1]) < 1e-6
            orientation, outward_sign, face_start, face_end = room_side_geometry(room_id, source_start, source_end)
            wall_core_center = source_start[1] if source_horizontal else source_start[0]
            # Keep the finish's inner face flush with the wall core and its visible
            # outer face FINISH metres beyond it. Subtracting FINISH/2 here makes
            # the two visible faces coplanar and causes severe depth-buffer fighting.
            coordinate = wall_core_center + outward_sign * (source_thickness / 2 + FINISH / 2)
            asset_id = (
                "tile_light_microcement_01"
                if room_id in WET_ROOM_IDS
                else "wallpaper_linen_natural_01"
                if source_wall_id == "wall_master_west" and room_id == "open_public"
                else "paint_greige_01"
                if room_id in {"master_bedroom", "bedroom_2"}
                else "paint_warm_white_01"
            )
            room_name = next((room["name_zh"] for room in ROOMS if room["id"] == room_id), room_id)
            face = {"id":f"wall_face_real4_{index:03d}","code":f"REAL4-{index:03d}","name_zh":f"{room_name}墙面","room_id":room_id,"host_wall_id":source_wall_id,"orientation":orientation,"axis":"X" if source_horizontal else "Y","coordinate":coordinate,"start":face_start,"end":face_end,"asset_id":asset_id,"preview_hide":source_hide,"surface_zone":"wet_wall" if room_id in WET_ROOM_IDS else "dry_wall","allowed_asset_categories":["tile"] if room_id in WET_ROOM_IDS else ["wall_paint","wallpaper"]}
            face.update({
                "wall_core_center_coordinate": wall_core_center,
                "wall_core_thickness_m": source_thickness,
                "finish_thickness_m": FINISH,
                "finish_outer_clearance_m": FINISH,
            })
            base.add_wall_face(face, mats[asset_id], collections["finishes"])
            faces.append(face)
            index += 1

    if index != ADDITIONAL_WALL_FACE_SOURCES[0][0]:
        raise RuntimeError(
            f"Stable wall-face range changed: expected next ID "
            f"{ADDITIONAL_WALL_FACE_SOURCES[0][0]:03d}, got {index:03d}"
        )
    for stable_index, source_wall_id, room_id in ADDITIONAL_WALL_FACE_SOURCES:
        if index != stable_index:
            raise RuntimeError(f"Expected wall-face ID {stable_index:03d}, got {index:03d}")
        source = next(item for item in WALLS if item[0] == source_wall_id)
        _source_id, source_start, source_end, source_thickness, _source_rooms, source_hide = source
        source_horizontal = abs(source_start[1]-source_end[1]) < 1e-6
        orientation, outward_sign, face_start, face_end = room_side_geometry(
            room_id, source_start, source_end
        )
        wall_core_center = source_start[1] if source_horizontal else source_start[0]
        coordinate = wall_core_center + outward_sign * (source_thickness / 2 + FINISH / 2)
        asset_id = "tile_light_microcement_01" if room_id in WET_ROOM_IDS else (
            "paint_greige_01" if room_id in {"master_bedroom", "bedroom_2"}
            else "paint_warm_white_01"
        )
        room_name = next(
            (room["name_zh"] for room in ROOMS if room["id"] == room_id), room_id
        )
        face = {
            "id": f"wall_face_real4_{stable_index:03d}",
            "code": f"REAL4-{stable_index:03d}",
            "name_zh": f"{room_name}墙面",
            "room_id": room_id,
            "host_wall_id": source_wall_id,
            "orientation": orientation,
            "axis": "X" if source_horizontal else "Y",
            "coordinate": coordinate,
            "start": face_start,
            "end": face_end,
            "asset_id": asset_id,
            "preview_hide": source_hide,
            "surface_zone": "wet_wall" if room_id in WET_ROOM_IDS else "dry_wall",
            "allowed_asset_categories": ["tile"] if room_id in WET_ROOM_IDS else ["wall_paint", "wallpaper"],
            "wall_core_center_coordinate": wall_core_center,
            "wall_core_thickness_m": source_thickness,
            "finish_thickness_m": FINISH,
            "finish_outer_clearance_m": FINISH,
        }
        base.add_wall_face(face, mats[asset_id], collections["finishes"])
        faces.append(face)
        index += 1
    merge_meshes_by_property(collections["walls"], "host_wall_id")
    merge_meshes_by_property(collections["finishes"], "wall_face_id")
    bpy.context.scene["wall_faces_json"] = json.dumps(faces, ensure_ascii=False)

    build_architectural_details(collections["details"], mats)
    build_glass_guardrail(collections["details"], mats)
    build_furniture(collections["furniture"], mats)


def add_reference_layer(collection):
    if not REFERENCE_PATH.exists():
        return
    image = bpy.data.images.load(str(REFERENCE_PATH), check_existing=True)
    image.pack()
    empty = bpy.data.objects.new("REFERENCE_YunKuo_135", None)
    empty.empty_display_type = "IMAGE"
    empty.data = image
    empty.empty_display_size = 13.4
    empty.location = (WIDTH/2, DEPTH/2, -.12)
    empty["reference_source"] = "和达智慧生态城 云阔 135㎡"
    empty["calibration_anchor"] = "7.6m south frontage"
    empty.hide_render = True
    collection.objects.link(empty)


def build_labels(collection, mats):
    for room in ROOMS:
        x1,y1,x2,y2 = room["rect"]
        label = base.add_floor_text(room["name_zh"], ((x1+x2)/2,(y1+y2)/2,.075), .22, collection, mats["label"])
        label["preview_only"] = True


def export_glb(root):
    bpy.ops.object.select_all(action="DESELECT")
    for obj in collection_objects_recursive(root):
        if obj.type in {"MESH", "CURVE"} and not obj.get("preview_only", False):
            obj.hide_set(False)
            obj.select_set(True)
    bpy.ops.export_scene.gltf(filepath=str(GLB_PATH), export_format="GLB", use_selection=True, export_apply=True, export_extras=True, export_yup=True, export_materials="PLACEHOLDER")
    bpy.ops.object.select_all(action="DESELECT")


def collection_objects_recursive(root):
    """Avoid Blender 5.2's unstable Collection.all_objects iterator."""
    objects = []
    pending = [root]
    while pending:
        collection = pending.pop()
        objects.extend(list(collection.objects))
        pending.extend(list(collection.children))
    return objects


def default_floor_asset(room_type):
    if room_type in {"bathroom", "kitchen", "foyer"}:
        return "tile_light_microcement_01"
    return "floor_light_oak_matte_01"


def write_manifest(faces):
    room_records = []
    for room in ROOMS:
        floor_asset = default_floor_asset(room["type"])
        room_records.append({
            **room,
            "surface_ids": {
                "floor": f"surface_real4_floor_{room['id']}",
                "ceiling": f"surface_real4_ceiling_{room['id']}",
            },
            "surface_asset_ids": {
                "floor": floor_asset,
                "ceiling": "ceiling_flat_01",
            },
            "wall_face_ids": [f["id"] for f in faces if f["room_id"] == room["id"]],
        })

    balcony_records = []
    for balcony in BALCONIES:
        balcony_record = {
            **balcony,
            "type": "balcony",
            "surface_ids": {
                "floor": f"surface_real4_floor_{balcony['id']}",
            },
            "surface_asset_ids": {
                "floor": "tile_warm_travertine_01",
            },
            "wall_face_ids": [],
        }
        balcony_records.append(balcony_record)
        room_records.append(balcony_record)

    design_targets = [
        {
            "kind": "wall_face",
            "id": face["id"],
            "role": "wall",
            "room_id": face["room_id"],
            "name_zh": face["name_zh"],
            "default_asset_id": face["asset_id"],
            "surface_zone": face["surface_zone"],
            "allowed_asset_categories": face["allowed_asset_categories"],
        }
        for face in faces
    ]
    for room in room_records:
        for role, surface_id in room["surface_ids"].items():
            design_targets.append({
                "kind": "surface",
                "id": surface_id,
                "role": role,
                "room_id": room["id"],
                "name_zh": f"{room['name_zh']}{'地面' if role == 'floor' else '顶面'}",
                "default_asset_id": room["surface_asset_ids"][role],
                "allowed_asset_categories": ["wood_floor", "tile"] if role == "floor" else ["ceiling"],
            })

    manifest = {
        "schema_version":"4.1.0","generated_at":datetime.now(timezone.utc).isoformat(),"generator":"blender/generate_spacious_floorplan_v4.py","blender_version":bpy.app.version_string,
        "house_id":HOUSE_ID,"geometry_revision":GEOMETRY_REVISION,"prototype":"和达智慧生态城 云阔 135㎡真实户型 · 少隔断优化","units":"meters","up_axis":"Z",
        "origin":{"location_m":[0.0,0.0,0.0],"description":"住宅主体西南外墙角；Blender Z-up，导出 glTF 时转换为 Y-up。"},
        "dimensions_m":{"width":WIDTH,"depth":DEPTH,"wall_height":WALL_HEIGHT},
        "reference":{"local_file":"output/research/spacious_floorplans/heda_135_ldkg.jpg","source_url":"https://imgwcs2.soufunimg.com/house/2022_08/17/a6c9f2a8-ca2d-45da-baae-eb126e42c7bc.jpg","project_page":"https://m.fang.com/xf/qd/2411123269/122289.htm","use":"proportional_geometry_and_published_anchor_reference"},
        "dimension_calibration_m":{"overall_width":WIDTH,"overall_depth":DEPTH,"public_frontage":PUBLIC_FRONTAGE,"balcony_depth":BALCONY_DEPTH,"wall_height":WALL_HEIGHT},
        "area_basis":{"published_building_area_m2":135.0,"published_internal_area_m2":96.53,"advertised_public_zone_m2":39.0,"modeled_open_public_m2":next(r["area_m2"] for r in ROOMS if r["id"]=="open_public"),"modeled_room_rectangles_m2":round(sum(r["area_m2"] for r in ROOMS),2),"balconies_m2":round(sum(b["area_m2"] for b in BALCONIES),2),"note_zh":"公开面积用于比例校准；矩形面积为概念模型自检值，不替代测绘或施工图。"},
        "space_strategy":{"solid_partition_count":len(WALLS)-4,"formal_bedroom_walls_complete":True,"convertible_room_program":"living_room","open_study_integrated":False,"kitchen_boundary":"full_height_glass_slider","visual_axis":"foyer_to_living_room_to_7.6m_balcony"},
        "rooms":room_records,
        "balconies":balcony_records,
        "openings":[{**o,"host_wall_id":host} for host,items in OPENINGS.items() for o in items],
        "wall_faces":faces,
        "design_targets":design_targets,
        "agent_assignment":{"target_kinds":["wall_face","surface"],"asset_field":"asset_id","cardinality":"one_asset_per_target"},
        "agent_wall_assignment":{"target_field":"wall_face_id","asset_field":"asset_id","operation":"assign_wall_asset","cardinality":"one_asset_per_wall_face"},
        "files":{"blend":BLEND_PATH.name,"glb":GLB_PATH.name,"preview":"previews/house_spacious_yunkuo_135_v4.png","validation":"validation_report_spacious_v4.json","asset_catalog":"asset_manifest.json"},
        "copyright_note_zh":"原户型图仅作内部几何比例参考；3D几何和家具由本项目重新建模，前端不分发原户型图片。",
        "disclaimer":"概念复刻用于学习与作品演示，不是施工图、测绘图或商品房合同附件。"
    }
    MANIFEST_PATH.write_text(json.dumps(manifest, ensure_ascii=False, indent=2), encoding="utf-8")


def activate_outputs():
    """Atomically synchronize the reproducible v4 outputs to active consumers."""
    # A list is used for manifests because one source has multiple consumers.
    copies = [
        (GLB_PATH, VIEWER_MODELS_DIR / GLB_PATH.name),
        (MANIFEST_PATH, ACTIVE_SCENE_MANIFEST_PATH),
        (MANIFEST_PATH, ROOT_SCENE_MANIFEST_PATH),
        (MANIFEST_PATH, VIEWER_MODELS_DIR / "scene_manifest.json"),
        (base.ASSET_MANIFEST_PATH, ROOT_ASSET_MANIFEST_PATH),
        (base.ASSET_MANIFEST_PATH, VIEWER_MODELS_DIR / "asset_manifest.json"),
        (base.ASSET_CARDS_PATH, ROOT_ASSET_CARDS_PATH),
    ]
    for source, destination in copies:
        destination.parent.mkdir(parents=True, exist_ok=True)
        temporary = destination.with_suffix(destination.suffix + ".tmp")
        shutil.copy2(source, temporary)
        temporary.replace(destination)


def main():
    base.reset_file()
    scene = bpy.context.scene
    scene.name = "Spacious_Chinese_Apartment_135_V4"
    scene["house_id"] = HOUSE_ID
    scene["schema_version"] = "4.1.0"
    scene["geometry_revision"] = GEOMETRY_REVISION
    scene["published_building_area_m2"] = 135.0
    scene["published_internal_area_m2"] = 96.53
    scene["reference_prototype"] = "和达智慧生态城 云阔"
    mats = build_materials()
    root = base.make_collection("REAL_V4_EXPORT")
    cols = {key:base.make_collection(name,root) for key,name in {"surfaces":"SURFACES","walls":"WALL_CORES","finishes":"WALL_FINISHES","openings":"OPENINGS","details":"ARCHITECTURAL_DETAILS","furniture":"FURNITURE_SCALE_REFERENCES"}.items()}
    asset_library = base.make_collection("V4_ASSET_LIBRARY")
    material_catalog = base.make_collection("V4_ASSET_CATALOG_MATERIALS", asset_library)
    paint_catalog = base.make_collection("V4_ASSET_CATALOG_PAINTS", asset_library)
    ceiling_catalog = base.make_collection("V4_ASSET_CATALOG_CEILINGS", asset_library)
    labels = base.make_collection("PREVIEW_LABELS")
    refs = base.make_collection("REFERENCE_DRAWING")
    build_model(cols,mats)
    base.build_asset_catalog(material_catalog, mats)
    base.build_paint_catalog(paint_catalog, mats)
    base.build_ceiling_catalog(ceiling_catalog, mats)
    base.set_collection_render(asset_library, True)
    asset_library.hide_viewport = True
    build_labels(labels,mats)
    add_reference_layer(refs)
    base.add_lighting()
    camera = base.add_camera("Camera_RealV4", (18.8,-15.6,16.8), (6.65,4.15,.45), lens=54.0)
    for obj in collection_objects_recursive(root):
        obj.hide_render = bool(obj.get("preview_hide",False) or obj.get("surface_role")=="ceiling")
    base.set_collection_render(labels,False)
    base.render_preview(camera,PREVIEW_DIR/"house_spacious_yunkuo_135_v4.png",(1400,1000))
    export_glb(root)
    faces = json.loads(scene["wall_faces_json"])
    write_manifest(faces)
    base.write_manifests()
    for obj in collection_objects_recursive(root):
        obj.hide_render = False
    bpy.ops.wm.save_as_mainfile(filepath=str(BLEND_PATH),compress=True)
    activate_outputs()
    print("SPACIOUS_V4_GENERATION_COMPLETE")
    print(f"BLEND={BLEND_PATH}")
    print(f"GLB={GLB_PATH}")
    print(f"ROOMS={len(ROOMS)}")
    print(f"WALL_FACES={len(faces)}")


if __name__ == "__main__":
    main()
