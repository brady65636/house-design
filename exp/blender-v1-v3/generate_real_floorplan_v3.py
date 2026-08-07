"""Rebuild the approved real 127.99 sqm Chinese high-rise apartment.

Reference prototype:
    长江广电·光谷家 A1 臻景, 127.99㎡, 3室2厅2卫

The published diagram is calibrated from its dimension strings rather than
treated as a decorative mood reference:
    overall grid 10.20m x 10.80m
    south body width 7.60m
    north-east wing depth 6.10m

Run with:
    blender --background --factory-startup --python blender/generate_real_floorplan_v3.py
"""

from __future__ import annotations

import importlib.util
import json
from datetime import datetime, timezone
from pathlib import Path

import bpy


ROOT_DIR = Path(__file__).resolve().parents[1]
OUTPUT_DIR = ROOT_DIR / "output"
PREVIEW_DIR = OUTPUT_DIR / "previews"
REFERENCE_PATH = OUTPUT_DIR / "research" / "real_floorplans" / "wuhan_guanggu_127.jpg"
BLEND_PATH = OUTPUT_DIR / "house_real_guanggu_12799_v3.blend"
GLB_PATH = OUTPUT_DIR / "house_real_guanggu_12799_v3.glb"
MANIFEST_PATH = OUTPUT_DIR / "scene_manifest_real_v3.json"
HOUSE_ID = "house_real_guanggu_12799_v3"

WIDTH = 10.20
DEPTH = 10.80
SOUTH_BODY_WIDTH = 7.60
NORTH_EAST_WING_DEPTH = 6.10
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
    {"id": "master_bedroom", "name_zh": "主卧", "type": "bedroom", "rect": [1.00, 0.20, 4.15, 4.55], "orientation": "south_west"},
    {"id": "living_room", "name_zh": "客厅", "type": "living_room", "rect": [4.35, 0.20, 8.35, 4.75], "orientation": "south"},
    {"id": "bedroom_2", "name_zh": "次卧", "type": "bedroom", "rect": [0.20, 7.35, 4.05, 10.60], "orientation": "north_west"},
    {"id": "bedroom_3", "name_zh": "儿童房 / 书房", "type": "bedroom", "rect": [4.25, 6.85, 7.15, 10.60], "orientation": "north"},
    {"id": "kitchen", "name_zh": "厨房", "type": "kitchen", "rect": [7.35, 8.15, 10.00, 10.60], "orientation": "north"},
    {"id": "dining_room", "name_zh": "餐厅", "type": "dining_room", "rect": [7.35, 6.15, 10.00, 8.00], "orientation": "east"},
    {"id": "foyer", "name_zh": "玄关", "type": "foyer", "rect": [7.35, 4.85, 10.00, 6.00], "orientation": "east"},
    {"id": "guest_bath", "name_zh": "公卫", "type": "bathroom", "rect": [0.20, 6.05, 2.45, 7.15], "orientation": "west"},
    {"id": "master_bath", "name_zh": "主卫", "type": "bathroom", "rect": [0.20, 4.80, 2.65, 5.90], "orientation": "west"},
    {"id": "central_hall", "name_zh": "过厅", "type": "hall", "rect": [2.80, 4.85, 7.15, 6.65], "orientation": "internal"},
]
for room in ROOMS:
    x1, y1, x2, y2 = room["rect"]
    room["area_m2"] = round((x2 - x1) * (y2 - y1), 2)

BALCONIES = [
    {"id": "south_living_balcony", "name_zh": "南向客厅阳台", "rect": [4.30, -1.30, 8.50, 0.00], "area_m2": 5.46, "orientation": "south"},
    {"id": "north_bedroom_balcony", "name_zh": "北向生活阳台", "rect": [4.20, 10.80, 7.25, 11.60], "area_m2": 2.44, "orientation": "north"},
]

OPENINGS = {
    "wall_ext_south": [
        {"id": "opening_master_south_window", "start": 1.30, "end": 3.70, "bottom": 0.72, "top": 2.35, "kind": "window"},
        {"id": "opening_living_balcony_slider", "start": 4.60, "end": 8.15, "bottom": 0.00, "top": 2.42, "kind": "window"},
    ],
    "wall_ext_west_lower": [
        {"id": "opening_master_west_window", "start": 1.35, "end": 2.30, "bottom": 0.92, "top": 2.25, "kind": "window"},
    ],
    "wall_ext_west_upper": [
        {"id": "opening_master_bath_window", "start": 5.02, "end": 5.70, "bottom": 1.35, "top": 2.30, "kind": "window"},
        {"id": "opening_guest_bath_window", "start": 6.15, "end": 6.85, "bottom": 1.35, "top": 2.30, "kind": "window"},
        {"id": "opening_bed2_west_window", "start": 8.20, "end": 9.85, "bottom": 0.82, "top": 2.35, "kind": "window"},
    ],
    "wall_ext_north": [
        {"id": "opening_bed2_north_window", "start": 0.70, "end": 3.35, "bottom": 0.72, "top": 2.35, "kind": "window"},
        {"id": "opening_bed3_balcony_door", "start": 4.55, "end": 6.90, "bottom": 0.00, "top": 2.40, "kind": "window"},
        {"id": "opening_kitchen_north_window", "start": 7.65, "end": 9.55, "bottom": 1.05, "top": 2.35, "kind": "window"},
    ],
    "wall_ext_east_upper": [
        {"id": "opening_entry_door", "start": 4.92, "end": 6.00, "bottom": 0.00, "top": 2.30, "kind": "door"},
        {"id": "opening_dining_east_window", "start": 6.42, "end": 7.72, "bottom": 0.82, "top": 2.35, "kind": "window"},
    ],
    "wall_master_east": [{"id": "opening_master_door", "start": 3.62, "end": 4.52, "bottom": 0.00, "top": 2.20, "kind": "door"}],
    "wall_master_north": [{"id": "opening_master_hall", "start": 3.10, "end": 4.00, "bottom": 0.00, "top": 2.20, "kind": "door"}],
    "wall_baths_east": [
        {"id": "opening_master_bath_door", "start": 5.02, "end": 5.78, "bottom": 0.00, "top": 2.18, "kind": "door"},
        {"id": "opening_guest_bath_door", "start": 6.20, "end": 6.96, "bottom": 0.00, "top": 2.18, "kind": "door"},
    ],
    "wall_bed2_south": [{"id": "opening_bed2_door", "start": 3.15, "end": 4.00, "bottom": 0.00, "top": 2.20, "kind": "door"}],
    "wall_bed3_south": [{"id": "opening_bed3_door", "start": 4.45, "end": 5.32, "bottom": 0.00, "top": 2.20, "kind": "door"}],
    "wall_kitchen_south": [{"id": "opening_kitchen_door", "start": 7.52, "end": 8.48, "bottom": 0.00, "top": 2.22, "kind": "door"}],
    "wall_dining_west": [{"id": "opening_dining_hall", "start": 5.05, "end": 6.42, "bottom": 0.00, "top": 2.45, "kind": "passage"}],
    "wall_living_north": [{"id": "opening_living_hall", "start": 5.00, "end": 6.55, "bottom": 0.00, "top": 2.45, "kind": "passage"}],
}

WALLS = [
    ("wall_ext_south", (0.90, 0.00), (8.50, 0.00), OUTER_WALL, ["master_bedroom", "living_room"], True),
    ("wall_ext_west_lower", (0.90, 0.00), (0.90, 4.70), OUTER_WALL, ["master_bedroom"], False),
    ("wall_ext_step_west", (0.00, 4.70), (0.90, 4.70), OUTER_WALL, ["master_bath"], False),
    ("wall_ext_west_upper", (0.00, 4.70), (0.00, 10.80), OUTER_WALL, ["master_bath", "guest_bath", "bedroom_2"], False),
    ("wall_ext_north", (0.00, 10.80), (10.20, 10.80), OUTER_WALL, ["bedroom_2", "bedroom_3", "kitchen"], False),
    ("wall_ext_east_upper", (10.20, 4.70), (10.20, 10.80), OUTER_WALL, ["foyer", "dining_room", "kitchen"], True),
    ("wall_ext_step_east", (8.50, 4.70), (10.20, 4.70), OUTER_WALL, ["foyer"], True),
    ("wall_ext_east_lower", (8.50, 0.00), (8.50, 4.70), OUTER_WALL, ["living_room"], True),
    ("wall_master_east", (4.25, 0.20), (4.25, 4.70), INNER_WALL, ["master_bedroom", "living_room"], True),
    ("wall_master_north", (0.90, 4.70), (4.25, 4.70), INNER_WALL, ["master_bedroom", "master_bath", "central_hall"], False),
    ("wall_baths_east", (2.70, 4.70), (2.70, 7.25), INNER_WALL, ["master_bath", "guest_bath", "central_hall"], False),
    ("wall_baths_split", (0.20, 5.98), (2.70, 5.98), INNER_WALL, ["master_bath", "guest_bath"], False),
    ("wall_bed2_south", (0.00, 7.25), (4.15, 7.25), INNER_WALL, ["bedroom_2", "guest_bath", "central_hall"], False),
    ("wall_bed2_east", (4.15, 7.25), (4.15, 10.80), INNER_WALL, ["bedroom_2", "bedroom_3"], False),
    ("wall_bed3_south", (4.15, 6.70), (7.25, 6.70), INNER_WALL, ["bedroom_3", "central_hall"], False),
    ("wall_bed3_east", (7.25, 6.70), (7.25, 10.80), INNER_WALL, ["bedroom_3", "dining_room", "kitchen"], False),
    ("wall_kitchen_south", (7.25, 8.05), (10.20, 8.05), INNER_WALL, ["kitchen", "dining_room"], False),
    ("wall_dining_west", (7.25, 4.70), (7.25, 6.70), INNER_WALL, ["dining_room", "foyer", "central_hall"], False),
    ("wall_living_north", (4.25, 4.78), (7.25, 4.78), INNER_WALL, ["living_room", "central_hall"], False),
]


def build_materials():
    cream = next(asset for asset in base.PAINT_ASSETS if asset["id"] == "paint_warm_cream_matte_01")
    greige = next(asset for asset in base.PAINT_ASSETS if asset["id"] == "paint_light_greige_eggshell_01")
    linen = next(asset for asset in base.WALLPAPER_ASSETS if asset["id"] == "wallpaper_linen_natural_01")
    mats = {
        cream["id"]: base.make_paint_material(cream),
        greige["id"]: base.make_paint_material(greige),
        linen["id"]: base.make_wallpaper_material(linen),
        "floor_light_oak_matte_01": base.make_wood_material("floor_light_oak_matte_01", ((0.38, 0.25, 0.12), (0.82, 0.62, 0.35))),
        "floor_honey_oak_matte_01": base.make_wood_material("floor_honey_oak_matte_01", ((0.30, 0.13, 0.045), (0.72, 0.39, 0.12))),
        "tile_warm_travertine_01": base.make_noise_material("tile_warm_travertine_01", ((0.39, 0.29, 0.18), (0.77, 0.62, 0.42)), 5.5, 0.56, 0.16),
        "tile_light_microcement_01": base.make_noise_material("tile_light_microcement_01", ((0.34, 0.36, 0.36), (0.67, 0.69, 0.67)), 8.0, 0.72, 0.10),
    }
    plain = {
        "wall_core": ((0.72, 0.72, 0.70), .82), "ceiling_white": ((.86, .85, .80), .82),
        "glass": ((.18, .36, .44), .18), "frame": ((.08, .07, .06), .34),
        "door": ((.22, .12, .055), .46), "label": ((.025, .025, .025), .55),
        "fabric": ((.48, .49, .45), .88), "fabric_light": ((.75, .72, .65), .92),
        "wood_light": ((.58, .40, .22), .68), "wood_dark": ((.16, .11, .08), .58),
        "metal": ((.09, .10, .09), .35), "sanitary": ((.90, .90, .86), .34),
        "rail": ((.10, .11, .11), .32),
    }
    for key, (color, roughness) in plain.items():
        mats[key] = base.make_plain_material(key, color, roughness)
    shader = mats["glass"].node_tree.nodes.get("Principled BSDF")
    if shader and "Transmission Weight" in shader.inputs:
        shader.inputs["Transmission Weight"].default_value = .55
    return mats


def add_surface(name, rect, z, thickness, collection, material, props):
    x1, y1, x2, y2 = rect
    return base.add_box(name, (x2-x1, y2-y1, thickness), ((x1+x2)/2, (y1+y2)/2, z), collection, material, props)


def wall_openings(wall_id, start, end):
    horizontal = abs(start[1] - end[1]) < 1e-6
    offset = min(start[0], end[0]) if horizontal else min(start[1], end[1])
    return [{**item, "start": item["start"]-offset, "end": item["end"]-offset} for item in OPENINGS.get(wall_id, [])]


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


def build_chair(prefix, x, y, collection, mats, room):
    ref_box(prefix+"_seat", (.42, .42, .08), (x, y, .47), collection, mats["wood_light"], room, "chair", .025)
    ref_box(prefix+"_back", (.42, .07, .48), (x, y+.18, .73), collection, mats["fabric"], room, "chair", .025)
    for index, (dx, dy) in enumerate([(-.16,-.16),(.16,-.16),(-.16,.16),(.16,.16)]):
        add_cylinder(prefix+f"_leg_{index}", .018, .43, (x+dx,y+dy,.215), collection, mats["metal"], {"room_id":room,"reference_only":True,"asset_role":"chair_leg"}, 12)


def build_furniture(collection, mats):
    build_bed("MasterBed", (2.48, 2.00), 1.80, 2.05, "master_bedroom", collection, mats)
    build_bed("Bedroom2Bed", (1.55, 9.15), 1.50, 2.00, "bedroom_2", collection, mats)
    build_bed("Bedroom3Bed", (5.75, 8.65), 1.20, 1.95, "bedroom_3", collection, mats)
    ref_box("MasterWardrobe", (.55, 2.00, 2.35), (3.78, 2.95, 1.18), collection, mats["wood_light"], "master_bedroom", "wardrobe", .02)
    ref_box("Bedroom2Wardrobe", (1.45, .55, 2.30), (3.05, 7.72, 1.16), collection, mats["wood_light"], "bedroom_2", "wardrobe", .02)
    ref_box("Bedroom3Desk", (1.10, .50, .07), (6.25, 10.05, .76), collection, mats["wood_light"], "bedroom_3", "desk", .03)

    # Airy sofa assembled from separate pieces rather than one oversized block.
    ref_box("SofaSeat", (.72, 2.55, .18), (4.82, 2.55, .42), collection, mats["fabric_light"], "living_room", "sofa", .08)
    ref_box("SofaBack", (.16, 2.55, .66), (4.51, 2.55, .70), collection, mats["fabric"], "living_room", "sofa", .07)
    for y in (1.38, 3.72):
        ref_box(f"SofaArm_{y}", (.72, .15, .45), (4.82, y, .50), collection, mats["fabric"], "living_room", "sofa", .05)
    ref_box("CoffeeTableTop", (1.15, .62, .07), (6.15, 2.55, .42), collection, mats["wood_light"], "living_room", "coffee_table", .05)
    for index, (x,y) in enumerate([(5.72,2.33),(6.58,2.77)]):
        add_cylinder(f"CoffeeLeg_{index}", .025, .38, (x,y,.20), collection, mats["metal"], {"room_id":"living_room","reference_only":True,"asset_role":"coffee_table_leg"}, 12)
    ref_box("TVConsole", (.38, 1.75, .42), (8.05, 2.55, .24), collection, mats["wood_dark"], "living_room", "media_console", .03)

    ref_box("DiningTop", (1.55, .82, .08), (8.62, 7.05, .76), collection, mats["wood_light"], "dining_room", "dining_table", .04)
    for index, (dx,dy) in enumerate([(-.62,-.28),(.62,-.28),(-.62,.28),(.62,.28)]):
        add_cylinder(f"DiningTableLeg_{index}", .025, .72, (8.62+dx,7.05+dy,.36), collection, mats["metal"], {"room_id":"dining_room","reference_only":True,"asset_role":"table_leg"}, 12)
    for index, (x,y) in enumerate([(7.75,6.55),(7.75,7.55),(9.49,6.55),(9.49,7.55)]):
        build_chair(f"DiningChair_{index}", x, y, collection, mats, "dining_room")

    ref_box("KitchenCounterNorth", (2.35, .58, .88), (8.62, 10.14, .45), collection, mats["wood_light"], "kitchen", "kitchen_counter", .02)
    ref_box("KitchenCounterEast", (.58, 1.55, .88), (9.70, 9.15, .45), collection, mats["wood_light"], "kitchen", "kitchen_counter", .02)
    for prefix, room, pos in [("GuestToilet","guest_bath",(.70,6.58)),("MasterToilet","master_bath",(.72,5.32))]:
        ref_box(prefix, (.40,.66,.42), (pos[0],pos[1],.23), collection, mats["sanitary"], room, "toilet", .10)
    ref_box("GuestVanity", (.78,.42,.74), (1.82,6.55,.39), collection, mats["sanitary"], "guest_bath", "vanity", .04)
    ref_box("MasterVanity", (.78,.42,.74), (1.90,5.32,.39), collection, mats["sanitary"], "master_bath", "vanity", .04)


def build_model(collections, mats):
    for room in ROOMS:
        floor_asset = "tile_light_microcement_01" if room["type"] in {"bathroom","kitchen","foyer"} else ("floor_honey_oak_matte_01" if room["id"]=="master_bedroom" else "floor_light_oak_matte_01")
        add_surface("Floor_"+room["id"], room["rect"], .015, .03, collections["surfaces"], mats[floor_asset], {"surface_id":f"surface_real3_floor_{room['id']}","surface_role":"floor","room_id":room["id"],"asset_id":floor_asset,"area_m2":room["area_m2"]})
        add_surface("Ceiling_"+room["id"], room["rect"], WALL_HEIGHT-.015, .03, collections["surfaces"], mats["ceiling_white"], {"surface_id":f"surface_real3_ceiling_{room['id']}","surface_role":"ceiling","room_id":room["id"],"asset_id":"ceiling_white","preview_hide":True})
    for balcony in BALCONIES:
        add_surface("Floor_"+balcony["id"], balcony["rect"], 0, .08, collections["surfaces"], mats["tile_warm_travertine_01"], {"surface_id":f"surface_real3_floor_{balcony['id']}","surface_role":"balcony_floor","room_id":balcony["id"],"asset_id":"tile_warm_travertine_01","area_m2":balcony["area_m2"]})

    base.WALL_FACE_OPENINGS = OPENINGS
    for wall_id,start,end,thickness,rooms,hide in WALLS:
        base.add_wall(wall_id,start,end,thickness,mats["wall_core"],collections["walls"],rooms,wall_openings(wall_id,start,end),hide)
        horizontal = abs(start[1]-end[1]) < 1e-6
        for opening in OPENINGS.get(wall_id,[]):
            if opening["kind"] == "passage": continue
            base.add_opening_fixture(opening["id"],"X" if horizontal else "Y",start[1] if horizontal else start[0],opening["start"],opening["end"],opening["bottom"],opening["top"],"window" if opening["kind"]=="window" else "door",collections["openings"],mats)

    faces=[]; index=1
    for wall_id,start,end,thickness,rooms,hide in WALLS:
        horizontal=abs(start[1]-end[1])<1e-6
        for side,room_id in enumerate(rooms[:2]):
            orientation=("north" if side==0 else "south") if horizontal else ("east" if side==0 else "west")
            coordinate=(start[1]+(thickness/2-FINISH/2)*(1 if orientation=="north" else -1)) if horizontal else (start[0]+(thickness/2-FINISH/2)*(1 if orientation=="east" else -1))
            asset_id="wallpaper_linen_natural_01" if wall_id=="wall_master_east" and room_id=="living_room" else ("paint_light_greige_eggshell_01" if room_id in {"master_bedroom","bedroom_3"} else "paint_warm_cream_matte_01")
            face={"id":f"wall_face_real3_{index:03d}","code":f"REAL3-{index:03d}","name_zh":f"{next((r['name_zh'] for r in ROOMS if r['id']==room_id),room_id)}墙面","room_id":room_id,"host_wall_id":wall_id,"orientation":orientation,"axis":"X" if horizontal else "Y","coordinate":coordinate,"start":min(start[0],end[0]) if horizontal else min(start[1],end[1]),"end":max(start[0],end[0]) if horizontal else max(start[1],end[1]),"asset_id":asset_id,"preview_hide":hide}
            base.add_wall_face(face,mats[asset_id],collections["finishes"]); faces.append(face); index+=1
    bpy.context.scene["wall_faces_json"]=json.dumps(faces,ensure_ascii=False)

    for name,size,loc in [("SouthRail",(4.20,.05,1.10),(6.40,-1.27,.55)),("SouthRailW",(.05,1.30,1.10),(4.32,-.65,.55)),("SouthRailE",(.05,1.30,1.10),(8.48,-.65,.55)),("NorthRail",(3.05,.05,1.10),(5.72,11.57,.55))]:
        base.add_box(name,size,loc,collections["openings"],mats["rail"],{"asset_role":"guardrail"})
    build_furniture(collections["furniture"],mats)


def add_reference_layer(collection):
    if not REFERENCE_PATH.exists(): return
    image=bpy.data.images.load(str(REFERENCE_PATH),check_existing=True); image.pack()
    empty=bpy.data.objects.new("REFERENCE_RealFloorplan_12799",None)
    empty.empty_display_type="IMAGE"; empty.data=image; empty.empty_display_size=10.8
    empty.location=(WIDTH/2,DEPTH/2,-.12); empty["reference_source"]="长江广电·光谷家 A1 臻景 127.99㎡"
    empty["calibration_grid_m"]="10.20 x 10.80"; empty.hide_render=True
    collection.objects.link(empty)


def build_labels(collection,mats):
    for room in ROOMS:
        x1,y1,x2,y2=room["rect"]
        label=base.add_floor_text(room["name_zh"],((x1+x2)/2,(y1+y2)/2,.075),.22,collection,mats["label"])
        label["preview_only"]=True


def export_glb(root):
    bpy.ops.object.select_all(action="DESELECT")
    for obj in root.all_objects:
        if obj.type in {"MESH","CURVE"} and not obj.get("preview_only",False): obj.hide_set(False); obj.select_set(True)
    bpy.ops.export_scene.gltf(filepath=str(GLB_PATH),export_format="GLB",use_selection=True,export_apply=True,export_extras=True,export_yup=True,export_materials="PLACEHOLDER")
    bpy.ops.object.select_all(action="DESELECT")


def write_manifest(faces):
    manifest={
        "schema_version":"3.0.0","generated_at":datetime.now(timezone.utc).isoformat(),"generator":"blender/generate_real_floorplan_v3.py","blender_version":bpy.app.version_string,
        "house_id":HOUSE_ID,"prototype":"长江广电·光谷家 A1 臻景 127.99㎡真实户型复刻","units":"meters","up_axis":"Z",
        "reference":{"local_file":"output/research/real_floorplans/wuhan_guanggu_127.jpg","source_url":"https://imgwcs2.soufunimg.com/house/2022_08/09/f7336c3c-a9c2-4855-ba93-b297185c3ad7.jpg","project_page":"https://m.fang.com/xf/housereport/wuhan/2610162136.html","use":"geometry_and_dimension_reference_only"},
        "dimension_calibration_m":{"overall_width":WIDTH,"overall_depth":DEPTH,"south_body_width":SOUTH_BODY_WIDTH,"north_east_wing_depth":NORTH_EAST_WING_DEPTH,"wall_height":WALL_HEIGHT},
        "area_basis":{"published_building_area_m2":127.99,"modeled_room_rectangles_m2":round(sum(r["area_m2"] for r in ROOMS),2),"balconies_m2":round(sum(b["area_m2"] for b in BALCONIES),2),"note_zh":"建筑面积沿用真实项目公开口径；房间矩形面积仅用于模型自检，不替代测绘套内面积。"},
        "rooms":[{**r,"surface_ids":{"floor":f"surface_real3_floor_{r['id']}","ceiling":f"surface_real3_ceiling_{r['id']}"},"wall_face_ids":[f["id"] for f in faces if f["room_id"]==r["id"]]} for r in ROOMS],
        "balconies":BALCONIES,"openings":[{**o,"host_wall_id":host} for host,items in OPENINGS.items() for o in items],"wall_faces":faces,
        "files":{"blend":BLEND_PATH.name,"glb":GLB_PATH.name,"preview":"previews/house_real_guanggu_12799_v3.png","validation":"validation_report_real_v3.json"},
        "copyright_note_zh":"原户型图仅作内部几何尺度参考；3D几何和家具由本项目重新建模，前端不分发原户型图片。",
        "disclaimer":"概念复刻用于学习与作品演示，不是施工图、测绘图或商品房合同附件。"
    }
    MANIFEST_PATH.write_text(json.dumps(manifest,ensure_ascii=False,indent=2),encoding="utf-8")


def main():
    base.reset_file(); scene=bpy.context.scene; scene.name="Real_Chinese_Highrise_12799_V3"
    scene["house_id"]=HOUSE_ID; scene["schema_version"]="3.0.0"; scene["published_building_area_m2"]=127.99
    scene["reference_prototype"]="长江广电·光谷家 A1 臻景"
    mats=build_materials(); root=base.make_collection("REAL_V3_EXPORT")
    cols={key:base.make_collection(name,root) for key,name in {"surfaces":"SURFACES","walls":"WALL_CORES","finishes":"WALL_FINISHES","openings":"OPENINGS","furniture":"FURNITURE_SCALE_REFERENCES"}.items()}
    labels=base.make_collection("PREVIEW_LABELS"); refs=base.make_collection("REFERENCE_DRAWING")
    build_model(cols,mats); build_labels(labels,mats); add_reference_layer(refs); base.add_lighting()
    camera=base.add_camera("Camera_RealV3",(15.2,-13.5,14.8),(5.1,5.0,.55),lens=52.0)
    for obj in root.all_objects: obj.hide_render=bool(obj.get("preview_hide",False) or obj.get("surface_role")=="ceiling")
    base.set_collection_render(labels,False); base.render_preview(camera,PREVIEW_DIR/"house_real_guanggu_12799_v3.png",(1300,950))
    export_glb(root); faces=json.loads(scene["wall_faces_json"]); write_manifest(faces)
    for obj in root.all_objects: obj.hide_render=False
    bpy.ops.wm.save_as_mainfile(filepath=str(BLEND_PATH),compress=True)
    print("REAL_V3_GENERATION_COMPLETE"); print(f"BLEND={BLEND_PATH}"); print(f"GLB={GLB_PATH}"); print(f"ROOMS={len(ROOMS)}"); print(f"WALL_FACES={len(faces)}")


if __name__=="__main__": main()
