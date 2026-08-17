"""Generate the first reproducible house and representative asset library.

Run with:
    blender --background --factory-startup --python blender/generate_house_assets.py

The script intentionally uses only Blender's bundled Python API.  It creates a
stable, metric scene that can later be driven by Scheme JSON and Three.js.
"""

from __future__ import annotations

import json
import math
import os
import sys
from datetime import datetime, timezone
from pathlib import Path

import bpy
from mathutils import Vector


ROOT_DIR = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT_DIR))

from asset_knowledge import build_asset_knowledge

OUTPUT_DIR = ROOT_DIR / "output"
PREVIEW_DIR = OUTPUT_DIR / "previews"
BLEND_PATH = OUTPUT_DIR / "house_2b2l_90_v1.blend"
GLB_PATH = OUTPUT_DIR / "house_2b2l_90_v1.glb"
ASSET_MANIFEST_PATH = OUTPUT_DIR / "asset_manifest.json"
ASSET_CARDS_PATH = OUTPUT_DIR / "asset_cards.json"
SCENE_MANIFEST_PATH = OUTPUT_DIR / "scene_manifest.json"
DEDICATED_SCENE_MANIFEST_PATH = OUTPUT_DIR / "scene_manifest_house_2b2l_90_v1.json"
PAINT_CATALOG_PATH = ROOT_DIR / "viewer" / "app" / "data" / "paintCatalog.json"
PAINT_TEXTURE_DIR = ROOT_DIR / "viewer" / "public" / "assets" / "paints"
WALLPAPER_CATALOG_PATH = ROOT_DIR / "viewer" / "app" / "data" / "wallpaperCatalog.json"
WALLPAPER_TEXTURE_DIR = OUTPUT_DIR / "wallpapers_pbr"
FLOOR_CATALOG_PATH = ROOT_DIR / "viewer" / "app" / "data" / "floorCatalog.json"
TILE_CATALOG_PATH = ROOT_DIR / "viewer" / "app" / "data" / "tileCatalog.json"
CEILING_CATALOG_PATH = ROOT_DIR / "viewer" / "app" / "data" / "ceilingCatalog.json"
SURFACE_TEXTURE_DIR = OUTPUT_DIR / "surfaces_pbr"
SURFACE_RUNTIME_TEXTURE_DIR = ROOT_DIR / "viewer" / "public" / "assets" / "surfaces"

HOUSE_ID = "house_2b2l_90_v1"
HOUSE_WIDTH = 10.8
HOUSE_DEPTH = 8.4
WALL_HEIGHT = 2.8
OUTER_WALL = 0.20
INNER_WALL = 0.12
WALL_FINISH_THICKNESS = 0.001

OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
PREVIEW_DIR.mkdir(parents=True, exist_ok=True)


PAINT_CATALOG = json.loads(PAINT_CATALOG_PATH.read_text(encoding="utf-8"))
WALLPAPER_CATALOG = json.loads(WALLPAPER_CATALOG_PATH.read_text(encoding="utf-8"))
FLOOR_CATALOG = json.loads(FLOOR_CATALOG_PATH.read_text(encoding="utf-8"))
TILE_CATALOG = json.loads(TILE_CATALOG_PATH.read_text(encoding="utf-8"))
CEILING_CATALOG = json.loads(CEILING_CATALOG_PATH.read_text(encoding="utf-8"))


def expand_paint_assets() -> list[dict]:
    variants = []
    for paint in PAINT_CATALOG["paints"]:
        default_tone = PAINT_CATALOG["parameter_schema"]["lightness"]["default"]
        default_finish_id = PAINT_CATALOG["parameter_schema"]["finish"]["default"]
        finish = next(item for item in PAINT_CATALOG["finishes"] if item["id"] == default_finish_id)
        variants.append(
            {
                "id": paint["asset_id"],
                "name": f"{paint['name_en']} parameterized wall paint",
                "name_zh": f"{paint['name_zh']}墙漆",
                "category": "wall_paint",
                "representation": "parameterized_material",
                "slug": paint["id"],
                "coating_system": "solid_paint",
                "color_srgb": paint["colors"][default_tone],
                "tone_color_anchors": paint["colors"],
                "parameter_schema": PAINT_CATALOG["parameter_schema"],
                "default_parameters": {
                    "lightness": default_tone,
                    "saturation": PAINT_CATALOG["parameter_schema"]["saturation"]["default"],
                    "finish": default_finish_id,
                },
                "finish_material_anchors": {
                    item["id"]: {
                        "roughness_mean": item["roughness_mean"],
                        "roughness_range": item["roughness_range"],
                        "normal_scale": item["normal_scale"],
                        "env_map_intensity": item["env_map_intensity"],
                    }
                    for item in PAINT_CATALOG["finishes"]
                },
                "legacy_asset_ids": paint.get("legacy_asset_ids", []),
                "tone": default_tone,
                "finish": default_finish_id,
                "roughness_mean": finish["roughness_mean"],
                "roughness_range": finish["roughness_range"],
                "normal_scale": finish["normal_scale"],
                "texture_set_id": PAINT_CATALOG["texture_set"]["id"],
                "license": "project_owned_procedural",
            }
        )
    for product in PAINT_CATALOG.get("specialty_products", []):
        variants.append(
            {
                **product,
                "name": product["name_en"],
                "category": "wall_paint",
                "representation": "procedural_specialty_coating",
                "tone": "fixed",
                "color_srgb": product["color_srgb"],
                "license": "project_owned_procedural",
            }
        )
    return variants


PAINT_ASSETS = expand_paint_assets()
WALLPAPER_ASSETS = [
    {
        **product,
        "name": product["name_en"],
        "category": "wallpaper",
        "representation": "imagegen_original_pbr",
        "license": "project_owned",
    }
    for product in WALLPAPER_CATALOG["products"]
]
FLOOR_ASSETS = [
    {
        **product,
        "name": product["name_en"],
        "category": "wood_floor",
        "representation": "pbr_texture_material",
        "license": "cc0" if product["source_type"] == "cc0_reference" else "project_owned",
    }
    for product in FLOOR_CATALOG["products"]
]
TILE_ASSETS = [
    {
        **product,
        "name": product["name_en"],
        "category": "tile",
        "representation": "pbr_texture_material",
        "license": "project_owned",
    }
    for product in TILE_CATALOG["products"]
]
CEILING_ASSETS = [
    {
        **product,
        "name": product["name_en"],
        "category": "ceiling",
        "license": "project_owned",
    }
    for product in CEILING_CATALOG["products"]
]


ASSETS = [
    *PAINT_ASSETS,
    *WALLPAPER_ASSETS,
    *FLOOR_ASSETS,
    *TILE_ASSETS,
    *CEILING_ASSETS,
]


ROOMS = [
    {
        "id": "living_room",
        "name_zh": "客厅",
        "bounds": [0.20, 0.20, 4.10, 4.60],
        "floor_asset": "floor_light_oak_matte_01",
    },
    {
        "id": "dining_room",
        "name_zh": "餐厅",
        "bounds": [4.10, 0.20, 6.60, 4.60],
        "floor_asset": "floor_light_oak_matte_01",
    },
    {
        "id": "master_bedroom",
        "name_zh": "主卧",
        "bounds": [0.20, 4.72, 3.80, 8.20],
        "floor_asset": "floor_honey_oak_matte_01",
    },
    {
        "id": "bedroom_2",
        "name_zh": "次卧",
        "bounds": [3.92, 4.72, 6.60, 8.20],
        "floor_asset": "floor_light_oak_matte_01",
    },
    {
        "id": "kitchen",
        "name_zh": "厨房",
        "bounds": [6.72, 0.20, 10.60, 2.78],
        "floor_asset": "tile_warm_travertine_01",
    },
    {
        "id": "foyer_corridor",
        "name_zh": "玄关与走廊",
        "bounds": [6.72, 2.90, 10.60, 4.60],
        "floor_asset": "tile_light_microcement_01",
    },
    {
        "id": "bathroom",
        "name_zh": "卫生间",
        "bounds": [6.72, 4.72, 8.92, 8.20],
        "floor_asset": "tile_light_microcement_01",
    },
    {
        "id": "utility_balcony",
        "name_zh": "生活阳台",
        "bounds": [9.04, 4.72, 10.60, 8.20],
        "floor_asset": "tile_warm_travertine_01",
    },
]


# A wall face is the room-facing side of a physical host wall.  These IDs are
# stable Agent targets: one physical wall may expose a different numbered face
# to each adjacent room.  Door and window openings do not create extra IDs;
# all mesh pieces around an opening share the same wall_face_id.
WALL_FACE_OPENINGS = {
    "wall_exterior_south": [
        {"id": "window_south_01", "start": 0.75, "end": 3.55, "bottom": 0.55, "top": 2.30},
        {"id": "window_south_02", "start": 4.35, "end": 6.05, "bottom": 0.80, "top": 2.25},
        {"id": "window_south_03", "start": 7.45, "end": 9.55, "bottom": 0.95, "top": 2.20},
    ],
    "wall_exterior_north": [
        {"id": "window_north_01", "start": 0.95, "end": 3.05, "bottom": 0.85, "top": 2.25},
        {"id": "window_north_02", "start": 4.25, "end": 6.10, "bottom": 0.85, "top": 2.25},
        {"id": "window_north_03", "start": 7.25, "end": 8.25, "bottom": 1.25, "top": 2.20},
        {"id": "window_north_04", "start": 9.35, "end": 10.25, "bottom": 1.00, "top": 2.20},
    ],
    "wall_exterior_east": [
        {"id": "door_entry_01", "start": 3.15, "end": 4.20, "bottom": 0.0, "top": 2.20},
    ],
    "wall_bedrooms_south": [
        {"id": "door_master_01", "start": 2.75, "end": 3.65, "bottom": 0.0, "top": 2.15},
        {"id": "door_bedroom_2_01", "start": 4.85, "end": 5.75, "bottom": 0.0, "top": 2.15},
    ],
    "wall_central_spine": [
        {"id": "opening_living_foyer_01", "start": 3.15, "end": 4.25, "bottom": 0.0, "top": 2.25},
        {"id": "door_bathroom_01", "start": 5.45, "end": 6.35, "bottom": 0.0, "top": 2.15},
    ],
    "wall_kitchen_north": [
        {"id": "door_kitchen_01", "start": 7.91, "end": 8.91, "bottom": 0.0, "top": 2.15},
    ],
    "wall_service_south": [
        {"id": "door_bathroom_02", "start": 7.21, "end": 8.11, "bottom": 0.0, "top": 2.15},
        {"id": "door_utility_01", "start": 9.41, "end": 10.31, "bottom": 0.0, "top": 2.15},
    ],
}


WALL_FACES = [
    # Public open area: the living/dining boundary is virtual, so there is no
    # wall between them, but their coplanar south faces retain separate IDs.
    {"id": "wall_face_001", "code": "LIV-S", "name_zh": "客厅南墙", "room_id": "living_room", "orientation": "south", "host_wall_id": "wall_exterior_south", "axis": "X", "coordinate": 0.1005, "start": 0.10, "end": 4.10, "asset_id": "paint_warm_white_01", "preview_hide": True},
    {"id": "wall_face_002", "code": "LIV-W", "name_zh": "客厅西墙", "room_id": "living_room", "orientation": "west", "host_wall_id": "wall_exterior_west", "axis": "Y", "coordinate": 0.1005, "start": 0.095, "end": 4.605, "asset_id": "wallpaper_linen_natural_01"},
    {"id": "wall_face_003", "code": "LIV-N", "name_zh": "客厅北墙", "room_id": "living_room", "orientation": "north", "host_wall_id": "wall_bedrooms_south", "axis": "X", "coordinate": 4.5995, "start": 0.20, "end": 4.10, "asset_id": "paint_warm_white_01"},
    {"id": "wall_face_004", "code": "DIN-S", "name_zh": "餐厅南墙", "room_id": "dining_room", "orientation": "south", "host_wall_id": "wall_exterior_south", "axis": "X", "coordinate": 0.1005, "start": 4.10, "end": 6.60, "asset_id": "paint_warm_white_01", "preview_hide": True},
    {"id": "wall_face_005", "code": "DIN-E", "name_zh": "餐厅东墙", "room_id": "dining_room", "orientation": "east", "host_wall_id": "wall_central_spine", "axis": "Y", "coordinate": 6.5995, "start": 0.20, "end": 4.60, "asset_id": "paint_warm_white_01"},
    {"id": "wall_face_006", "code": "DIN-N", "name_zh": "餐厅北墙", "room_id": "dining_room", "orientation": "north", "host_wall_id": "wall_bedrooms_south", "axis": "X", "coordinate": 4.5995, "start": 4.10, "end": 6.60, "asset_id": "paint_warm_white_01"},
    {"id": "wall_face_007", "code": "MBR-N", "name_zh": "主卧北墙", "room_id": "master_bedroom", "orientation": "north", "host_wall_id": "wall_exterior_north", "axis": "X", "coordinate": 8.2995, "start": 0.10, "end": 3.80, "asset_id": "paint_greige_01"},
    {"id": "wall_face_008", "code": "MBR-E", "name_zh": "主卧东墙", "room_id": "master_bedroom", "orientation": "east", "host_wall_id": "wall_between_bedrooms", "axis": "Y", "coordinate": 3.7995, "start": 4.72, "end": 8.30, "asset_id": "paint_greige_01"},
    {"id": "wall_face_009", "code": "MBR-S", "name_zh": "主卧南墙", "room_id": "master_bedroom", "orientation": "south", "host_wall_id": "wall_bedrooms_south", "axis": "X", "coordinate": 4.7205, "start": 0.20, "end": 3.80, "asset_id": "paint_greige_01"},
    {"id": "wall_face_010", "code": "MBR-W", "name_zh": "主卧西墙", "room_id": "master_bedroom", "orientation": "west", "host_wall_id": "wall_exterior_west", "axis": "Y", "coordinate": 0.1005, "start": 4.72, "end": 8.30, "asset_id": "paint_greige_01"},
    {"id": "wall_face_011", "code": "BR2-N", "name_zh": "次卧北墙", "room_id": "bedroom_2", "orientation": "north", "host_wall_id": "wall_exterior_north", "axis": "X", "coordinate": 8.2995, "start": 3.92, "end": 6.60, "asset_id": "wallpaper_linear_geometry_01"},
    {"id": "wall_face_012", "code": "BR2-E", "name_zh": "次卧东墙", "room_id": "bedroom_2", "orientation": "east", "host_wall_id": "wall_central_spine", "axis": "Y", "coordinate": 6.5995, "start": 4.72, "end": 8.20, "asset_id": "paint_greige_01"},
    {"id": "wall_face_013", "code": "BR2-S", "name_zh": "次卧南墙", "room_id": "bedroom_2", "orientation": "south", "host_wall_id": "wall_bedrooms_south", "axis": "X", "coordinate": 4.7205, "start": 3.92, "end": 6.60, "asset_id": "paint_greige_01"},
    {"id": "wall_face_014", "code": "BR2-W", "name_zh": "次卧西墙", "room_id": "bedroom_2", "orientation": "west", "host_wall_id": "wall_between_bedrooms", "axis": "Y", "coordinate": 3.9205, "start": 4.72, "end": 8.30, "asset_id": "paint_greige_01"},
    {"id": "wall_face_015", "code": "KIT-S", "name_zh": "厨房南墙", "room_id": "kitchen", "orientation": "south", "host_wall_id": "wall_exterior_south", "axis": "X", "coordinate": 0.1005, "start": 6.72, "end": 10.70, "asset_id": "tile_warm_travertine_01", "preview_hide": True},
    {"id": "wall_face_016", "code": "KIT-E", "name_zh": "厨房东墙", "room_id": "kitchen", "orientation": "east", "host_wall_id": "wall_exterior_east", "axis": "Y", "coordinate": 10.6995, "start": 0.10, "end": 2.78, "asset_id": "tile_warm_travertine_01", "preview_hide": True},
    {"id": "wall_face_017", "code": "KIT-N", "name_zh": "厨房北墙", "room_id": "kitchen", "orientation": "north", "host_wall_id": "wall_kitchen_north", "axis": "X", "coordinate": 2.7795, "start": 6.72, "end": 10.70, "asset_id": "tile_warm_travertine_01"},
    {"id": "wall_face_018", "code": "KIT-W", "name_zh": "厨房西墙", "room_id": "kitchen", "orientation": "west", "host_wall_id": "wall_central_spine", "axis": "Y", "coordinate": 6.7205, "start": 0.20, "end": 2.78, "asset_id": "tile_warm_travertine_01"},
    {"id": "wall_face_019", "code": "FOY-S", "name_zh": "玄关走廊南墙", "room_id": "foyer_corridor", "orientation": "south", "host_wall_id": "wall_kitchen_north", "axis": "X", "coordinate": 2.9005, "start": 6.72, "end": 10.70, "asset_id": "paint_warm_white_01"},
    {"id": "wall_face_020", "code": "FOY-E", "name_zh": "玄关走廊东墙", "room_id": "foyer_corridor", "orientation": "east", "host_wall_id": "wall_exterior_east", "axis": "Y", "coordinate": 10.6995, "start": 2.90, "end": 4.60, "asset_id": "paint_warm_white_01", "preview_hide": True},
    {"id": "wall_face_021", "code": "FOY-N", "name_zh": "玄关走廊北墙", "room_id": "foyer_corridor", "orientation": "north", "host_wall_id": "wall_service_south", "axis": "X", "coordinate": 4.5995, "start": 6.72, "end": 10.70, "asset_id": "paint_warm_white_01"},
    {"id": "wall_face_022", "code": "FOY-W", "name_zh": "玄关走廊西墙", "room_id": "foyer_corridor", "orientation": "west", "host_wall_id": "wall_central_spine", "axis": "Y", "coordinate": 6.7205, "start": 2.90, "end": 4.60, "asset_id": "paint_warm_white_01"},
    {"id": "wall_face_023", "code": "BTH-N", "name_zh": "卫生间北墙", "room_id": "bathroom", "orientation": "north", "host_wall_id": "wall_exterior_north", "axis": "X", "coordinate": 8.2995, "start": 6.72, "end": 8.92, "asset_id": "tile_light_microcement_01"},
    {"id": "wall_face_024", "code": "BTH-E", "name_zh": "卫生间东墙", "room_id": "bathroom", "orientation": "east", "host_wall_id": "wall_bath_utility", "axis": "Y", "coordinate": 8.9195, "start": 4.72, "end": 8.30, "asset_id": "tile_light_microcement_01"},
    {"id": "wall_face_025", "code": "BTH-S", "name_zh": "卫生间南墙", "room_id": "bathroom", "orientation": "south", "host_wall_id": "wall_service_south", "axis": "X", "coordinate": 4.7205, "start": 6.72, "end": 8.92, "asset_id": "tile_light_microcement_01"},
    {"id": "wall_face_026", "code": "BTH-W", "name_zh": "卫生间西墙", "room_id": "bathroom", "orientation": "west", "host_wall_id": "wall_central_spine", "axis": "Y", "coordinate": 6.7205, "start": 4.72, "end": 8.20, "asset_id": "tile_light_microcement_01"},
    {"id": "wall_face_027", "code": "UTL-N", "name_zh": "生活阳台北墙", "room_id": "utility_balcony", "orientation": "north", "host_wall_id": "wall_exterior_north", "axis": "X", "coordinate": 8.2995, "start": 9.04, "end": 10.70, "asset_id": "tile_warm_travertine_01"},
    {"id": "wall_face_028", "code": "UTL-E", "name_zh": "生活阳台东墙", "room_id": "utility_balcony", "orientation": "east", "host_wall_id": "wall_exterior_east", "axis": "Y", "coordinate": 10.6995, "start": 4.72, "end": 8.30, "asset_id": "tile_warm_travertine_01", "preview_hide": True},
    {"id": "wall_face_029", "code": "UTL-S", "name_zh": "生活阳台南墙", "room_id": "utility_balcony", "orientation": "south", "host_wall_id": "wall_service_south", "axis": "X", "coordinate": 4.7205, "start": 9.04, "end": 10.70, "asset_id": "tile_warm_travertine_01"},
    {"id": "wall_face_030", "code": "UTL-W", "name_zh": "生活阳台西墙", "room_id": "utility_balcony", "orientation": "west", "host_wall_id": "wall_bath_utility", "axis": "Y", "coordinate": 9.0405, "start": 4.72, "end": 8.30, "asset_id": "tile_warm_travertine_01"},
]


def reset_file() -> None:
    bpy.ops.object.select_all(action="SELECT")
    bpy.ops.object.delete(use_global=False)
    for collection in list(bpy.data.collections):
        bpy.data.collections.remove(collection)
    for material in list(bpy.data.materials):
        bpy.data.materials.remove(material)
    scene = bpy.context.scene
    scene.name = "House_And_Asset_Library"
    scene.unit_settings.system = "METRIC"
    scene.unit_settings.length_unit = "METERS"
    scene.unit_settings.scale_length = 1.0
    # Blender 5.2 exposes Eevee as BLENDER_EEVEE (the older NEXT suffix was removed).
    scene.render.engine = "BLENDER_EEVEE"
    scene.render.resolution_percentage = 100
    scene.render.image_settings.file_format = "PNG"
    scene.render.film_transparent = False
    try:
        scene.view_settings.look = "AgX - Medium High Contrast"
    except (TypeError, ValueError):
        pass


def make_collection(name: str, parent: bpy.types.Collection | None = None) -> bpy.types.Collection:
    collection = bpy.data.collections.new(name)
    if parent is None:
        bpy.context.scene.collection.children.link(collection)
    else:
        parent.children.link(collection)
    return collection


def move_to_collection(obj: bpy.types.Object, collection: bpy.types.Collection) -> None:
    for current in list(obj.users_collection):
        current.objects.unlink(obj)
    collection.objects.link(obj)


def assign_material(obj: bpy.types.Object, material: bpy.types.Material) -> None:
    if obj.data and hasattr(obj.data, "materials"):
        obj.data.materials.clear()
        obj.data.materials.append(material)


def add_box(
    name: str,
    size: tuple[float, float, float],
    location: tuple[float, float, float],
    collection: bpy.types.Collection,
    material: bpy.types.Material | None = None,
    props: dict | None = None,
    bevel: float = 0.0,
) -> bpy.types.Object:
    bpy.ops.mesh.primitive_cube_add(location=location)
    obj = bpy.context.object
    obj.name = name
    obj.dimensions = size
    bpy.ops.object.transform_apply(location=False, rotation=False, scale=True)
    move_to_collection(obj, collection)
    if material:
        assign_material(obj, material)
    if props:
        for key, value in props.items():
            obj[key] = value
    if bevel > 0.0:
        modifier = obj.modifiers.new(name="EdgeSoftening", type="BEVEL")
        modifier.width = bevel
        modifier.segments = 2
    return obj


def add_text(
    body: str,
    location: tuple[float, float, float],
    size: float,
    collection: bpy.types.Collection,
    material: bpy.types.Material,
) -> bpy.types.Object:
    bpy.ops.object.text_add(location=location, rotation=(math.radians(90), 0.0, 0.0))
    obj = bpy.context.object
    obj.name = f"Label_{body}"
    obj.data.body = body
    obj.data.align_x = "CENTER"
    obj.data.size = size
    obj.data.extrude = 0.002
    move_to_collection(obj, collection)
    assign_material(obj, material)
    return obj


def add_floor_text(
    body: str,
    location: tuple[float, float, float],
    size: float,
    collection: bpy.types.Collection,
    material: bpy.types.Material,
) -> bpy.types.Object:
    """Add a label lying on the XY plane for the house cutaway preview."""
    bpy.ops.object.text_add(location=location)
    obj = bpy.context.object
    obj.name = f"RoomLabel_{body}"
    obj.data.body = body
    obj.data.align_x = "CENTER"
    obj.data.align_y = "CENTER"
    obj.data.size = size
    obj.data.extrude = 0.002
    move_to_collection(obj, collection)
    assign_material(obj, material)
    return obj


def set_principled(material: bpy.types.Material, base_color, roughness: float) -> bpy.types.Node:
    material.use_nodes = True
    nodes = material.node_tree.nodes
    nodes.clear()
    output = nodes.new("ShaderNodeOutputMaterial")
    shader = nodes.new("ShaderNodeBsdfPrincipled")
    shader.inputs["Base Color"].default_value = (*base_color, 1.0)
    shader.inputs["Roughness"].default_value = roughness
    material.node_tree.links.new(shader.outputs["BSDF"], output.inputs["Surface"])
    return shader


def make_plain_material(asset_id: str, color, roughness: float) -> bpy.types.Material:
    material = bpy.data.materials.new(name=f"MAT_{asset_id}")
    material["asset_id"] = asset_id
    material["source_type"] = "procedural_original"
    set_principled(material, color, roughness)
    material.diffuse_color = (*color, 1.0)
    return material


def srgb_hex_to_linear(hex_color: str) -> tuple[float, float, float]:
    """Convert the catalog's display-referred sRGB hex value to Blender linear RGB."""
    values = [int(hex_color[index:index + 2], 16) / 255.0 for index in (1, 3, 5)]

    def convert(channel: float) -> float:
        return channel / 12.92 if channel <= 0.04045 else ((channel + 0.055) / 1.055) ** 2.4

    return tuple(convert(channel) for channel in values)


def load_paint_image(filename: str, colorspace: str) -> bpy.types.Image:
    image = bpy.data.images.load(str(PAINT_TEXTURE_DIR / filename), check_existing=True)
    image.colorspace_settings.name = colorspace
    image.pack()
    return image


def make_paint_material(asset: dict) -> bpy.types.Material:
    """Build a subtle roller-applied interior paint, shared by all catalog colours."""
    material = bpy.data.materials.new(name=f"MAT_{asset['id']}")
    material["asset_id"] = asset["id"]
    material["source_type"] = "project_owned_parametric_pbr"
    material["paint_slug"] = asset.get("slug", "")
    material["paint_tone"] = asset["tone"]
    material["paint_finish"] = asset["finish"]
    material["coating_system"] = asset.get("coating_system", "solid_paint")
    material["color_srgb"] = asset["color_srgb"]
    material["texture_set_id"] = asset["texture_set_id"]
    material.use_nodes = True
    nodes = material.node_tree.nodes
    links = material.node_tree.links
    nodes.clear()

    output = nodes.new("ShaderNodeOutputMaterial")
    shader = nodes.new("ShaderNodeBsdfPrincipled")
    shader.inputs["Roughness"].default_value = 1.0
    texcoord = nodes.new("ShaderNodeTexCoord")
    mapping = nodes.new("ShaderNodeMapping")
    physical_size = asset.get("physical_size_m", PAINT_CATALOG["texture_set"]["physical_size_m"])
    mapping.inputs["Scale"].default_value = (1.0 / physical_size[0], 1.0 / physical_size[1], 1.0)
    links.new(texcoord.outputs["Object"], mapping.inputs["Vector"])

    base_texture = nodes.new("ShaderNodeTexImage")
    base_texture.name = "Paint micro base colour"
    specialty = asset.get("coating_system", "solid_paint") != "solid_paint"
    base_filename = f"{asset['id']}_basecolor_4k.jpg" if specialty else "paint_micro_basecolor_4k.jpg"
    base_texture.image = load_paint_image(base_filename, "sRGB")
    base_texture.projection = "BOX"
    base_texture.projection_blend = 0.12

    tint = nodes.new("ShaderNodeMixRGB")
    tint.blend_type = "MULTIPLY"
    tint.inputs[0].default_value = 1.0
    linear_color = srgb_hex_to_linear(asset["color_srgb"])
    tint.inputs[2].default_value = (*linear_color, 1.0)

    normal_texture = nodes.new("ShaderNodeTexImage")
    normal_texture.name = "Paint roller normal"
    normal_filename = f"{asset['id']}_normal_gl_4k.jpg" if specialty else "paint_micro_normal_gl_4k.jpg"
    normal_texture.image = load_paint_image(normal_filename, "Non-Color")
    normal_texture.projection = "BOX"
    normal_texture.projection_blend = 0.12
    normal_map = nodes.new("ShaderNodeNormalMap")
    normal_map.inputs["Strength"].default_value = asset["normal_scale"]

    roughness_filename = (
        f"{asset['id']}_roughness_4k.jpg"
        if specialty
        else "paint_micro_roughness_eggshell_4k.jpg"
        if asset["finish"] == "eggshell"
        else "paint_micro_roughness_matte_4k.jpg"
    )
    roughness_texture = nodes.new("ShaderNodeTexImage")
    roughness_texture.name = f"Paint {asset['finish']} roughness"
    roughness_texture.image = load_paint_image(roughness_filename, "Non-Color")
    roughness_texture.projection = "BOX"
    roughness_texture.projection_blend = 0.12

    for texture_node in (base_texture, normal_texture, roughness_texture):
        links.new(mapping.outputs["Vector"], texture_node.inputs["Vector"])
    if specialty:
        links.new(base_texture.outputs["Color"], shader.inputs["Base Color"])
    else:
        links.new(base_texture.outputs["Color"], tint.inputs[1])
        links.new(tint.outputs["Color"], shader.inputs["Base Color"])
    links.new(normal_texture.outputs["Color"], normal_map.inputs["Color"])
    links.new(normal_map.outputs["Normal"], shader.inputs["Normal"])
    links.new(roughness_texture.outputs["Color"], shader.inputs["Roughness"])
    links.new(shader.outputs["BSDF"], output.inputs["Surface"])

    material.diffuse_color = (*linear_color, 1.0)
    return material


def load_wallpaper_image(asset_id: str, suffix: str, colorspace: str) -> bpy.types.Image:
    filename = f"{asset_id}_{suffix}_4k" + (".jpg" if suffix == "basecolor" else ".png")
    image = bpy.data.images.load(str(WALLPAPER_TEXTURE_DIR / filename), check_existing=True)
    image.colorspace_settings.name = colorspace
    image.pack()
    return image


def make_wallpaper_material(asset: dict) -> bpy.types.Material:
    """Build a physically scaled wallpaper material from the approved catalog."""
    material = bpy.data.materials.new(name=f"MAT_{asset['id']}")
    material["asset_id"] = asset["id"]
    material["source_type"] = "project_original_imagegen_pbr"
    material["wallpaper_slug"] = asset.get("slug", "")
    material["match_type"] = asset["match_type"]
    material["texture_mode"] = asset["texture_mode"]
    material["repeat_size_m"] = asset["repeat_size_m"]
    material.use_nodes = True
    nodes = material.node_tree.nodes
    links = material.node_tree.links
    nodes.clear()

    output = nodes.new("ShaderNodeOutputMaterial")
    shader = nodes.new("ShaderNodeBsdfPrincipled")
    shader.inputs["Roughness"].default_value = 1.0
    if "Sheen Weight" in shader.inputs:
        shader.inputs["Sheen Weight"].default_value = asset["sheen"]
    if "Sheen Roughness" in shader.inputs:
        shader.inputs["Sheen Roughness"].default_value = 0.88

    texcoord = nodes.new("ShaderNodeTexCoord")
    mapping = nodes.new("ShaderNodeMapping")
    repeat_width, repeat_height = asset["repeat_size_m"]
    mapping.inputs["Scale"].default_value = (1.0 / repeat_width, 1.0 / repeat_height, 1.0)
    links.new(texcoord.outputs["UV"], mapping.inputs["Vector"])

    base_texture = nodes.new("ShaderNodeTexImage")
    base_texture.name = "Wallpaper base colour"
    base_texture.image = load_wallpaper_image(asset["id"], "basecolor", "sRGB")
    normal_texture = nodes.new("ShaderNodeTexImage")
    normal_texture.name = "Wallpaper OpenGL normal"
    normal_texture.image = load_wallpaper_image(asset["id"], "normal_gl", "Non-Color")
    roughness_texture = nodes.new("ShaderNodeTexImage")
    roughness_texture.name = "Wallpaper roughness"
    roughness_texture.image = load_wallpaper_image(asset["id"], "roughness", "Non-Color")
    height_texture = nodes.new("ShaderNodeTexImage")
    height_texture.name = "Wallpaper height"
    height_texture.image = load_wallpaper_image(asset["id"], "height", "Non-Color")

    extension = "EXTEND" if asset["texture_mode"] == "panel_mural" else "REPEAT"
    for texture_node in (base_texture, normal_texture, roughness_texture, height_texture):
        texture_node.extension = extension
        links.new(mapping.outputs["Vector"], texture_node.inputs["Vector"])

    normal_map = nodes.new("ShaderNodeNormalMap")
    normal_map.inputs["Strength"].default_value = asset["normal_scale"]
    bump = nodes.new("ShaderNodeBump")
    bump.inputs["Strength"].default_value = asset["height_strength"]
    bump.inputs["Distance"].default_value = 0.0006

    links.new(base_texture.outputs["Color"], shader.inputs["Base Color"])
    links.new(roughness_texture.outputs["Color"], shader.inputs["Roughness"])
    links.new(normal_texture.outputs["Color"], normal_map.inputs["Color"])
    links.new(normal_map.outputs["Normal"], bump.inputs["Normal"])
    links.new(height_texture.outputs["Color"], bump.inputs["Height"])
    links.new(bump.outputs["Normal"], shader.inputs["Normal"])
    links.new(shader.outputs["BSDF"], output.inputs["Surface"])

    linear_color = srgb_hex_to_linear(asset["tint"])
    material.diffuse_color = (*linear_color, 1.0)
    return material


def load_surface_image(asset_id: str, suffix: str, colorspace: str) -> bpy.types.Image:
    filename = f"{asset_id}_{suffix}_web" + (".jpg" if suffix == "basecolor" else ".webp")
    image = bpy.data.images.load(str(SURFACE_RUNTIME_TEXTURE_DIR / filename), check_existing=True)
    image.colorspace_settings.name = colorspace
    image.pack()
    return image


def make_surface_pbr_material(asset: dict) -> bpy.types.Material:
    """Build a physically scaled floor or tile PBR material from a catalog record."""
    material = bpy.data.materials.new(name=f"MAT_{asset['id']}")
    material["asset_id"] = asset["id"]
    material["source_type"] = asset["source_type"]
    material["surface_group"] = asset.get("material_group") or asset.get("preset") or ""
    material["repeat_size_m"] = asset["repeat_size_m"]
    material["supported_layouts"] = asset["supported_layouts"]
    material.use_nodes = True
    nodes = material.node_tree.nodes
    links = material.node_tree.links
    nodes.clear()

    output = nodes.new("ShaderNodeOutputMaterial")
    shader = nodes.new("ShaderNodeBsdfPrincipled")
    shader.inputs["Metallic"].default_value = 0.0
    shader.inputs["Roughness"].default_value = asset["roughness_mean"]

    texcoord = nodes.new("ShaderNodeTexCoord")
    mapping = nodes.new("ShaderNodeMapping")
    repeat_width, repeat_height = asset["repeat_size_m"]
    mapping.inputs["Scale"].default_value = (1.0 / repeat_width, 1.0 / repeat_height, 1.0)
    links.new(texcoord.outputs["UV"], mapping.inputs["Vector"])

    base_texture = nodes.new("ShaderNodeTexImage")
    base_texture.name = "Surface base colour"
    base_texture.image = load_surface_image(asset["id"], "basecolor", "sRGB")
    normal_texture = nodes.new("ShaderNodeTexImage")
    normal_texture.name = "Surface OpenGL normal"
    normal_texture.image = load_surface_image(asset["id"], "normal_gl", "Non-Color")
    roughness_texture = nodes.new("ShaderNodeTexImage")
    roughness_texture.name = "Surface roughness"
    roughness_texture.image = load_surface_image(asset["id"], "roughness", "Non-Color")
    for texture_node in (base_texture, normal_texture, roughness_texture):
        texture_node.extension = "REPEAT"
        links.new(mapping.outputs["Vector"], texture_node.inputs["Vector"])

    normal_map = nodes.new("ShaderNodeNormalMap")
    normal_map.inputs["Strength"].default_value = asset["normal_scale"]
    links.new(base_texture.outputs["Color"], shader.inputs["Base Color"])
    links.new(roughness_texture.outputs["Color"], shader.inputs["Roughness"])
    links.new(normal_texture.outputs["Color"], normal_map.inputs["Color"])
    links.new(normal_map.outputs["Normal"], shader.inputs["Normal"])
    links.new(shader.outputs["BSDF"], output.inputs["Surface"])

    material.diffuse_color = (*srgb_hex_to_linear(asset["tint"]), 1.0)
    return material


def make_noise_material(asset_id: str, colors, scale: float, roughness: float, bump_strength: float) -> bpy.types.Material:
    material = bpy.data.materials.new(name=f"MAT_{asset_id}")
    material["asset_id"] = asset_id
    material["source_type"] = "procedural_original"
    material.use_nodes = True
    nodes = material.node_tree.nodes
    links = material.node_tree.links
    nodes.clear()
    output = nodes.new("ShaderNodeOutputMaterial")
    shader = nodes.new("ShaderNodeBsdfPrincipled")
    shader.inputs["Roughness"].default_value = roughness
    texcoord = nodes.new("ShaderNodeTexCoord")
    noise = nodes.new("ShaderNodeTexNoise")
    noise.inputs["Scale"].default_value = scale
    noise.inputs["Detail"].default_value = 4.0
    noise.inputs["Roughness"].default_value = 0.62
    ramp = nodes.new("ShaderNodeValToRGB")
    ramp.color_ramp.elements[0].color = (*colors[0], 1.0)
    ramp.color_ramp.elements[1].color = (*colors[1], 1.0)
    bump = nodes.new("ShaderNodeBump")
    bump.inputs["Strength"].default_value = bump_strength
    bump.inputs["Distance"].default_value = 0.025
    links.new(texcoord.outputs["Generated"], noise.inputs["Vector"])
    links.new(noise.outputs["Fac"], ramp.inputs["Fac"])
    links.new(ramp.outputs["Color"], shader.inputs["Base Color"])
    links.new(noise.outputs["Fac"], bump.inputs["Height"])
    links.new(bump.outputs["Normal"], shader.inputs["Normal"])
    links.new(shader.outputs["BSDF"], output.inputs["Surface"])
    material.diffuse_color = (*colors[0], 1.0)
    return material


def make_linear_wallpaper(asset_id: str) -> bpy.types.Material:
    material = bpy.data.materials.new(name=f"MAT_{asset_id}")
    material["asset_id"] = asset_id
    material["source_type"] = "procedural_original"
    material.use_nodes = True
    nodes = material.node_tree.nodes
    links = material.node_tree.links
    nodes.clear()
    output = nodes.new("ShaderNodeOutputMaterial")
    shader = nodes.new("ShaderNodeBsdfPrincipled")
    shader.inputs["Roughness"].default_value = 0.72
    texcoord = nodes.new("ShaderNodeTexCoord")
    wave = nodes.new("ShaderNodeTexWave")
    wave.wave_type = "BANDS"
    wave.bands_direction = "X"
    wave.inputs["Scale"].default_value = 22.0
    wave.inputs["Distortion"].default_value = 1.2
    wave.inputs["Detail"].default_value = 2.0
    ramp = nodes.new("ShaderNodeValToRGB")
    ramp.color_ramp.interpolation = "CONSTANT"
    ramp.color_ramp.elements[0].position = 0.46
    ramp.color_ramp.elements[0].color = (0.55, 0.51, 0.45, 1.0)
    ramp.color_ramp.elements[1].position = 0.52
    ramp.color_ramp.elements[1].color = (0.83, 0.79, 0.70, 1.0)
    bump = nodes.new("ShaderNodeBump")
    bump.inputs["Strength"].default_value = 0.16
    bump.inputs["Distance"].default_value = 0.012
    links.new(texcoord.outputs["Generated"], wave.inputs["Vector"])
    links.new(wave.outputs["Color"], ramp.inputs["Fac"])
    links.new(ramp.outputs["Color"], shader.inputs["Base Color"])
    links.new(wave.outputs["Fac"], bump.inputs["Height"])
    links.new(bump.outputs["Normal"], shader.inputs["Normal"])
    links.new(shader.outputs["BSDF"], output.inputs["Surface"])
    material.diffuse_color = (0.76, 0.72, 0.65, 1.0)
    return material


def make_wood_material(asset_id: str, colors) -> bpy.types.Material:
    material = bpy.data.materials.new(name=f"MAT_{asset_id}")
    material["asset_id"] = asset_id
    material["source_type"] = "procedural_original"
    material.use_nodes = True
    nodes = material.node_tree.nodes
    links = material.node_tree.links
    nodes.clear()
    output = nodes.new("ShaderNodeOutputMaterial")
    shader = nodes.new("ShaderNodeBsdfPrincipled")
    shader.inputs["Roughness"].default_value = 0.48
    texcoord = nodes.new("ShaderNodeTexCoord")
    mapping = nodes.new("ShaderNodeMapping")
    mapping.inputs["Scale"].default_value = (0.7, 5.0, 2.0)
    noise = nodes.new("ShaderNodeTexNoise")
    noise.noise_dimensions = "3D"
    noise.inputs["Scale"].default_value = 3.2
    noise.inputs["Detail"].default_value = 7.0
    noise.inputs["Roughness"].default_value = 0.72
    ramp = nodes.new("ShaderNodeValToRGB")
    ramp.color_ramp.elements[0].color = (*colors[0], 1.0)
    ramp.color_ramp.elements[1].color = (*colors[1], 1.0)
    bump = nodes.new("ShaderNodeBump")
    bump.inputs["Strength"].default_value = 0.22
    bump.inputs["Distance"].default_value = 0.018
    links.new(texcoord.outputs["Generated"], mapping.inputs["Vector"])
    links.new(mapping.outputs["Vector"], noise.inputs["Vector"])
    links.new(noise.outputs["Fac"], ramp.inputs["Fac"])
    links.new(ramp.outputs["Color"], shader.inputs["Base Color"])
    links.new(noise.outputs["Fac"], bump.inputs["Height"])
    links.new(bump.outputs["Normal"], shader.inputs["Normal"])
    links.new(shader.outputs["BSDF"], output.inputs["Surface"])
    material.diffuse_color = (*colors[0], 1.0)
    return material


def build_materials() -> dict[str, bpy.types.Material]:
    materials = {asset["id"]: make_paint_material(asset) for asset in PAINT_ASSETS}
    materials.update({asset["id"]: make_wallpaper_material(asset) for asset in WALLPAPER_ASSETS})
    materials.update({asset["id"]: make_surface_pbr_material(asset) for asset in [*FLOOR_ASSETS, *TILE_ASSETS]})
    materials["wall_core"] = make_plain_material("wall_core", (0.72, 0.72, 0.70), 0.82)
    materials["ceiling_white"] = make_plain_material("ceiling_white", (0.86, 0.85, 0.80), 0.82)
    materials["ceiling_panel"] = make_plain_material("ceiling_panel", (0.78, 0.79, 0.76), 0.66)
    materials["ceiling_shadow_gap"] = make_plain_material("ceiling_shadow_gap", (0.035, 0.038, 0.037), 0.96)
    materials["ceiling_cove_light"] = make_plain_material("ceiling_cove_light", (0.98, 0.78, 0.48), 0.55)
    cove_shader = materials["ceiling_cove_light"].node_tree.nodes.get("Principled BSDF")
    if cove_shader:
        cove_shader.inputs["Emission Color"].default_value = (1.0, 0.52, 0.18, 1.0)
        cove_shader.inputs["Emission Strength"].default_value = 2.0
    materials["glass"] = make_plain_material("glass", (0.18, 0.36, 0.44), 0.18)
    glass_shader = materials["glass"].node_tree.nodes.get("Principled BSDF")
    if glass_shader:
        glass_shader.inputs["Metallic"].default_value = 0.0
        if "Transmission Weight" in glass_shader.inputs:
            glass_shader.inputs["Transmission Weight"].default_value = 0.55
    materials["frame"] = make_plain_material("frame", (0.08, 0.07, 0.06), 0.34)
    materials["door"] = make_plain_material("door", (0.22, 0.12, 0.055), 0.46)
    materials["label"] = make_plain_material("label", (0.025, 0.025, 0.025), 0.55)
    materials["label_light"] = make_plain_material("label_light", (0.82, 0.82, 0.78), 0.55)
    materials["catalog_base"] = make_plain_material("catalog_base", (0.16, 0.17, 0.18), 0.78)
    return materials


def add_wall(
    host_wall_id: str,
    start: tuple[float, float],
    end: tuple[float, float],
    thickness: float,
    material: bpy.types.Material,
    collection: bpy.types.Collection,
    room_ids: list[str],
    openings: list[dict] | None = None,
    preview_hide: bool = False,
) -> list[bpy.types.Object]:
    openings = sorted(openings or [], key=lambda item: item["start"])
    x1, y1 = start
    x2, y2 = end
    horizontal = abs(y2 - y1) < 1e-6
    length = abs(x2 - x1) if horizontal else abs(y2 - y1)
    origin_x = min(x1, x2)
    origin_y = min(y1, y2)
    created = []

    def add_interval(a: float, b: float, z0: float, z1: float, suffix: str) -> None:
        if b - a <= 0.001 or z1 - z0 <= 0.001:
            return
        if horizontal:
            size = (b - a, thickness, z1 - z0)
            location = (origin_x + (a + b) / 2.0, y1, (z0 + z1) / 2.0)
        else:
            size = (thickness, b - a, z1 - z0)
            location = (x1, origin_y + (a + b) / 2.0, (z0 + z1) / 2.0)
        obj = add_box(
            f"{host_wall_id}_{suffix}_{len(created):02d}",
            size,
            location,
            collection,
            material,
            {
                "host_wall_id": host_wall_id,
                "surface_role": "wall_core",
                "room_ids": json.dumps(room_ids, ensure_ascii=False),
                "preview_hide": preview_hide,
            },
        )
        created.append(obj)

    cursor = 0.0
    for index, opening in enumerate(openings):
        a = max(0.0, float(opening["start"]))
        b = min(length, float(opening["end"]))
        add_interval(cursor, a, 0.0, WALL_HEIGHT, f"solid_{index}")
        bottom = float(opening.get("bottom", 0.0))
        top = float(opening.get("top", 2.1))
        add_interval(a, b, 0.0, bottom, f"below_{index}")
        add_interval(a, b, top, WALL_HEIGHT, f"above_{index}")
        cursor = b
    add_interval(cursor, length, 0.0, WALL_HEIGHT, "solid_end")
    return created


def add_wall_face(
    face: dict,
    material: bpy.types.Material,
    collection: bpy.types.Collection,
) -> list[bpy.types.Object]:
    """Create one numbered room-side finish, preserving one ID around openings."""
    start = float(face["start"])
    end = float(face["end"])
    axis = face["axis"]
    coordinate = float(face["coordinate"])
    openings = []
    for opening in WALL_FACE_OPENINGS.get(face["host_wall_id"], []):
        clipped_start = max(start, float(opening["start"]))
        clipped_end = min(end, float(opening["end"]))
        if clipped_end - clipped_start > 0.001:
            openings.append({**opening, "start": clipped_start, "end": clipped_end})
    openings.sort(key=lambda item: item["start"])
    created = []

    def assign_metric_uv(obj: bpy.types.Object) -> None:
        """Map U to horizontal metres and V to height metres across all pieces."""
        uv_layer = obj.data.uv_layers.active or obj.data.uv_layers.new(name="WallMetricUV")
        reverse_u = face["orientation"] in {"east", "south"}
        for polygon in obj.data.polygons:
            for loop_index in polygon.loop_indices:
                vertex_index = obj.data.loops[loop_index].vertex_index
                world = obj.matrix_world @ obj.data.vertices[vertex_index].co
                horizontal = world.x if axis == "X" else world.y
                u = (end - horizontal) if reverse_u else (horizontal - start)
                uv_layer.data[loop_index].uv = (u, world.z)

    def add_interval(a: float, b: float, z0: float, z1: float, suffix: str) -> None:
        if b - a <= 0.001 or z1 - z0 <= 0.001:
            return
        if axis == "X":
            size = (b - a, WALL_FINISH_THICKNESS, z1 - z0)
            location = ((a + b) / 2.0, coordinate, (z0 + z1) / 2.0)
        else:
            size = (WALL_FINISH_THICKNESS, b - a, z1 - z0)
            location = (coordinate, (a + b) / 2.0, (z0 + z1) / 2.0)
        obj = add_box(
            f"{face['id']}_{suffix}_{len(created):02d}",
            size,
            location,
            collection,
            material,
            {
                "wall_face_id": face["id"],
                "wall_code": face["code"],
                "wall_name_zh": face["name_zh"],
                "room_id": face["room_id"],
                "host_wall_id": face["host_wall_id"],
                "orientation": face["orientation"],
                "surface_role": "wall_face",
                "asset_id": face["asset_id"],
                "preview_hide": bool(face.get("preview_hide", False)),
                "surface_zone": face.get("surface_zone", "dry_wall"),
                "allowed_asset_categories": json.dumps(
                    face.get("allowed_asset_categories", ["wall_paint", "wallpaper"]),
                    ensure_ascii=False,
                ),
            },
        )
        assign_metric_uv(obj)
        created.append(obj)

    cursor = start
    for index, opening in enumerate(openings):
        a = float(opening["start"])
        b = float(opening["end"])
        add_interval(cursor, a, 0.0, WALL_HEIGHT, f"solid_{index}")
        add_interval(a, b, 0.0, float(opening.get("bottom", 0.0)), f"below_{index}")
        add_interval(a, b, float(opening.get("top", 2.1)), WALL_HEIGHT, f"above_{index}")
        cursor = b
    add_interval(cursor, end, 0.0, WALL_HEIGHT, "solid_end")
    return created


def add_opening_fixture(
    opening_id: str,
    wall_axis: str,
    wall_coord: float,
    along_start: float,
    along_end: float,
    bottom: float,
    top: float,
    kind: str,
    collection: bpy.types.Collection,
    materials: dict[str, bpy.types.Material],
) -> bpy.types.Object | None:
    width = along_end - along_start
    frame_width = 0.055
    frame_depth = 0.055
    center_along = (along_start + along_end) / 2.0
    center_z = (bottom + top) / 2.0
    opening_height = top - bottom
    props = {"opening_id": opening_id, "opening_type": kind}

    if wall_axis == "X":
        def box(name, size_along, size_depth, size_z, along, z, mat, bevel=0.0):
            return add_box(name, (size_along, size_depth, size_z), (along, wall_coord, z), collection, mat, props, bevel=bevel)
    else:
        def box(name, size_along, size_depth, size_z, along, z, mat, bevel=0.0):
            return add_box(name, (size_depth, size_along, size_z), (wall_coord, along, z), collection, mat, props, bevel=bevel)

    box(f"{opening_id}_frame_left", frame_width, frame_depth, opening_height, along_start, center_z, materials["frame"], .004)
    box(f"{opening_id}_frame_right", frame_width, frame_depth, opening_height, along_end, center_z, materials["frame"], .004)
    box(f"{opening_id}_frame_top", width, frame_depth, frame_width, center_along, top, materials["frame"], .004)
    if kind == "window":
        box(f"{opening_id}_frame_bottom", width, frame_depth, frame_width, center_along, bottom, materials["frame"], .004)
        box(f"{opening_id}_glass", width - 0.10, 0.018, opening_height - 0.10, center_along, center_z, materials["glass"], .001)
        box(f"{opening_id}_mullion", 0.035, 0.045, opening_height - 0.08, center_along, center_z, materials["frame"], .003)
        return None
    else:
        leaf_width = width - 0.10
        leaf = box(
            f"{opening_id}_leaf",
            leaf_width,
            0.035,
            opening_height - 0.08,
            center_along,
            center_z - 0.02,
            materials["door"],
            .006,
        )
        leaf["asset_role"] = "door_leaf_reference"
        return leaf


def build_house(
    house_collection: bpy.types.Collection,
    materials: dict[str, bpy.types.Material],
) -> dict[str, bpy.types.Collection]:
    shell = make_collection("ARCHITECTURE", house_collection)
    wall_faces = make_collection("SURFACES_WALL", house_collection)
    floors = make_collection("SURFACES_FLOOR", house_collection)
    ceilings = make_collection("SURFACES_CEILING", house_collection)
    fixtures = make_collection("DOORS_WINDOWS", house_collection)

    # Floor zones are deliberately separate meshes so Scheme can replace them independently.
    for room in ROOMS:
        x1, y1, x2, y2 = room["bounds"]
        floor = add_box(
            f"Floor_{room['id']}",
            (x2 - x1, y2 - y1, 0.08),
            ((x1 + x2) / 2.0, (y1 + y2) / 2.0, -0.04),
            floors,
            materials[room["floor_asset"]],
            {
                "room_id": room["id"],
                "surface_id": f"surface_floor_{room['id']}",
                "surface_role": "floor",
                "asset_id": room["floor_asset"],
            },
        )
        floor["house_id"] = HOUSE_ID

        ceiling = add_box(
            f"Ceiling_{room['id']}",
            (x2 - x1, y2 - y1, 0.04),
            ((x1 + x2) / 2.0, (y1 + y2) / 2.0, WALL_HEIGHT - 0.02),
            ceilings,
            materials["ceiling_white"],
            {
                "room_id": room["id"],
                "surface_id": f"surface_ceiling_{room['id']}",
                "surface_role": "ceiling",
                "preset_id": "ceiling_flat_01",
                "preview_hide": True,
            },
        )
        ceiling["house_id"] = HOUSE_ID

    # Exterior shell. South and east walls are hidden only for the cutaway preview.
    south_openings = [
        {"start": 0.75, "end": 3.55, "bottom": 0.55, "top": 2.30, "kind": "window"},
        {"start": 4.35, "end": 6.05, "bottom": 0.80, "top": 2.25, "kind": "window"},
        {"start": 7.45, "end": 9.55, "bottom": 0.95, "top": 2.20, "kind": "window"},
    ]
    add_wall("wall_exterior_south", (0.0, 0.0), (HOUSE_WIDTH, 0.0), OUTER_WALL, materials["wall_core"], shell, ["living_room", "dining_room", "kitchen"], south_openings, True)
    for i, op in enumerate(south_openings, 1):
        add_opening_fixture(f"window_south_{i:02d}", "X", 0.0, op["start"], op["end"], op["bottom"], op["top"], "window", fixtures, materials)

    north_openings = [
        {"start": 0.95, "end": 3.05, "bottom": 0.85, "top": 2.25, "kind": "window"},
        {"start": 4.25, "end": 6.10, "bottom": 0.85, "top": 2.25, "kind": "window"},
        {"start": 7.25, "end": 8.25, "bottom": 1.25, "top": 2.20, "kind": "window"},
        {"start": 9.35, "end": 10.25, "bottom": 1.00, "top": 2.20, "kind": "window"},
    ]
    add_wall("wall_exterior_north", (0.0, HOUSE_DEPTH), (HOUSE_WIDTH, HOUSE_DEPTH), OUTER_WALL, materials["wall_core"], shell, ["master_bedroom", "bedroom_2", "bathroom", "utility_balcony"], north_openings)
    for i, op in enumerate(north_openings, 1):
        add_opening_fixture(f"window_north_{i:02d}", "X", HOUSE_DEPTH, op["start"], op["end"], op["bottom"], op["top"], "window", fixtures, materials)

    add_wall("wall_exterior_west", (0.0, 0.0), (0.0, HOUSE_DEPTH), OUTER_WALL, materials["wall_core"], shell, ["living_room", "master_bedroom"], [])
    east_openings = [{"start": 3.15, "end": 4.20, "bottom": 0.0, "top": 2.20, "kind": "door"}]
    add_wall("wall_exterior_east", (HOUSE_WIDTH, 0.0), (HOUSE_WIDTH, HOUSE_DEPTH), OUTER_WALL, materials["wall_core"], shell, ["kitchen", "foyer_corridor", "utility_balcony"], east_openings, True)
    add_opening_fixture("door_entry_01", "Y", HOUSE_WIDTH, 3.15, 4.20, 0.0, 2.20, "door", fixtures, materials)

    # Internal walls. Openings use distances measured from the wall start.
    add_wall(
        "wall_bedrooms_south",
        (0.20, 4.66),
        (6.66, 4.66),
        INNER_WALL,
        materials["wall_core"],
        shell,
        ["living_room", "dining_room", "master_bedroom", "bedroom_2"],
        [
            {"start": 2.55, "end": 3.45, "bottom": 0.0, "top": 2.15, "kind": "door"},
            {"start": 4.65, "end": 5.55, "bottom": 0.0, "top": 2.15, "kind": "door"},
        ],
    )
    add_opening_fixture("door_master_01", "X", 4.66, 2.75, 3.65, 0.0, 2.15, "door", fixtures, materials)
    add_opening_fixture("door_bedroom_2_01", "X", 4.66, 4.85, 5.75, 0.0, 2.15, "door", fixtures, materials)

    add_wall("wall_between_bedrooms", (3.86, 4.66), (3.86, 8.30), INNER_WALL, materials["wall_core"], shell, ["master_bedroom", "bedroom_2"], [])

    add_wall(
        "wall_central_spine",
        (6.66, 0.20),
        (6.66, 8.20),
        INNER_WALL,
        materials["wall_core"],
        shell,
        ["dining_room", "bedroom_2", "kitchen", "foyer_corridor", "bathroom"],
        [
            {"start": 2.95, "end": 4.05, "bottom": 0.0, "top": 2.25, "kind": "door"},
            {"start": 5.25, "end": 6.15, "bottom": 0.0, "top": 2.15, "kind": "door"},
        ],
    )
    add_opening_fixture("opening_living_foyer_01", "Y", 6.66, 3.15, 4.25, 0.0, 2.25, "door", fixtures, materials)
    add_opening_fixture("door_bathroom_01", "Y", 6.66, 5.45, 6.35, 0.0, 2.15, "door", fixtures, materials)

    add_wall(
        "wall_kitchen_north",
        (6.66, 2.84),
        (10.70, 2.84),
        INNER_WALL,
        materials["wall_core"],
        shell,
        ["kitchen", "foyer_corridor"],
        [{"start": 1.25, "end": 2.25, "bottom": 0.0, "top": 2.15, "kind": "door"}],
    )
    add_opening_fixture("door_kitchen_01", "X", 2.84, 7.91, 8.91, 0.0, 2.15, "door", fixtures, materials)

    add_wall(
        "wall_service_south",
        (6.66, 4.66),
        (10.70, 4.66),
        INNER_WALL,
        materials["wall_core"],
        shell,
        ["foyer_corridor", "bathroom", "utility_balcony"],
        [
            {"start": 0.55, "end": 1.45, "bottom": 0.0, "top": 2.15, "kind": "door"},
            {"start": 2.75, "end": 3.65, "bottom": 0.0, "top": 2.15, "kind": "door"},
        ],
    )
    add_opening_fixture("door_bathroom_02", "X", 4.66, 7.21, 8.11, 0.0, 2.15, "door", fixtures, materials)
    add_opening_fixture("door_utility_01", "X", 4.66, 9.41, 10.31, 0.0, 2.15, "door", fixtures, materials)

    add_wall("wall_bath_utility", (8.98, 4.66), (8.98, 8.30), INNER_WALL, materials["wall_core"], shell, ["bathroom", "utility_balcony"], [])

    for face in WALL_FACES:
        add_wall_face(face, materials[face["asset_id"]], wall_faces)

    return {"shell": shell, "wall_faces": wall_faces, "floors": floors, "ceilings": ceilings, "fixtures": fixtures}


def build_asset_catalog(collection: bpy.types.Collection, materials: dict[str, bpy.types.Material]) -> None:
    material_assets = [
        asset
        for asset in ASSETS
        if asset["representation"] != "geometry_preset" and asset["category"] != "wall_paint"
    ]
    # Six-column catalog for the current wallpaper, floor and tile libraries.
    add_box("Catalog_Backdrop", (13.6, 0.12, 15.7), (18.0, 0.35, -0.45), collection, materials["catalog_base"])
    for index, asset in enumerate(material_assets):
        col = index % 6
        row = index // 6
        x = 12.75 + col * 2.10
        z = 6.25 - row * 1.92
        panel = add_box(
            f"AssetPanel_{asset['id']}",
            (1.72, 0.10, 1.20),
            (x, 0.20, z),
            collection,
            materials[asset["id"]],
            {"asset_id": asset["id"], "category": asset["category"], "preview_object": True},
            bevel=0.035,
        )
        panel["display_name"] = asset["name"]
        short_label = asset["id"].replace("_01", "").replace("paint_", "").replace("wallpaper_", "").replace("floor_", "").replace("tile_", "")
        add_text(short_label, (x, 0.125, z - 0.72), 0.12, collection, materials["label"])


def build_paint_catalog(collection: bpy.types.Collection, materials: dict[str, bpy.types.Material]) -> None:
    """Build one physical panel per paint Asset; parameters are not extra panels."""
    center_x = 18.0
    add_box("PaintCatalog_Backdrop", (11.2, 0.12, 10.9), (center_x, 0.36, 4.4), collection, materials["catalog_base"])
    add_text("ONE ASSET · LIGHTNESS + SATURATION + FINISH ARE PARAMETERS", (13.0, 0.22, 9.30), 0.105, collection, materials["label_light"])
    assets_by_paint = {asset["slug"]: asset for asset in PAINT_ASSETS if asset.get("coating_system") == "solid_paint"}
    for row, paint in enumerate(PAINT_CATALOG["paints"]):
        z = 8.72 - row * 0.91
        label = paint["name_en"].upper().replace(" & ", " / ")
        add_text(label, (12.80, 0.22, z), 0.105, collection, materials["label_light"])
        asset = assets_by_paint[paint["id"]]
        panel = add_box(
            f"PaintPanel_{asset['id']}",
            (7.72, 0.12, 0.68),
            (16.62, 0.23, z),
            collection,
            materials[asset["id"]],
            {
                "asset_id": asset["id"],
                "category": "wall_paint",
                "slug": paint["id"],
                "parameterized": True,
                "preview_object": True,
            },
            bevel=0.025,
        )
        panel["display_name"] = asset["name"]

    specialty_assets = [asset for asset in PAINT_ASSETS if asset.get("coating_system") != "solid_paint"]
    add_text("MINERAL COATINGS", (12.80, 0.22, -0.38), 0.105, collection, materials["label_light"])
    for column, asset in enumerate(specialty_assets):
        x = 14.55 + column * 2.18
        panel = add_box(
            f"PaintPanel_{asset['id']}",
            (1.92, 0.12, 0.68),
            (x, 0.23, -0.38),
            collection,
            materials[asset["id"]],
            {
                "asset_id": asset["id"],
                "category": "wall_paint",
                "slug": asset.get("slug", ""),
                "tone": "fixed",
                "finish": asset["finish"],
                "coating_system": asset["coating_system"],
                "preview_object": True,
            },
            bevel=0.025,
        )
        panel["display_name"] = asset["name"]


def build_room_labels(collection: bpy.types.Collection, materials: dict[str, bpy.types.Material]) -> None:
    labels = {
        "living_room": "LIVING",
        "dining_room": "DINING",
        "master_bedroom": "MASTER",
        "bedroom_2": "BEDROOM 2",
        "kitchen": "KITCHEN",
        "foyer_corridor": "FOYER",
        "bathroom": "BATH",
        "utility_balcony": "UTILITY",
    }
    for room in ROOMS:
        x1, y1, x2, y2 = room["bounds"]
        add_floor_text(
            labels[room["id"]],
            ((x1 + x2) / 2.0, (y1 + y2) / 2.0, 0.015),
            0.24 if room["id"] != "utility_balcony" else 0.16,
            collection,
            materials["label"],
        )


def add_ceiling_mockup(
    center_x: float,
    center_y: float,
    preset_id: str,
    collection: bpy.types.Collection,
    materials: dict[str, bpy.types.Material],
) -> None:
    room_w = 3.4
    room_d = 3.0
    wall_h = 2.15
    thickness = 0.09
    # Three walls make a readable cutaway miniature.
    add_box(f"{preset_id}_wall_back", (room_w, thickness, wall_h), (center_x, center_y + room_d / 2, wall_h / 2), collection, materials["wall_core"], {"preset_id": preset_id})
    add_box(f"{preset_id}_wall_left", (thickness, room_d, wall_h), (center_x - room_w / 2, center_y, wall_h / 2), collection, materials["wall_core"], {"preset_id": preset_id})
    add_box(f"{preset_id}_floor", (room_w, room_d, 0.08), (center_x, center_y, -0.04), collection, materials["floor_light_oak_matte_01"], {"preset_id": preset_id})
    preset = next(asset for asset in CEILING_ASSETS if asset["id"] == preset_id)
    drop_height_m = preset["drop_height_mm"] / 1000.0
    shared = {"preset_id": preset_id, "drop_height_mm": preset["drop_height_mm"]}
    if preset_id == "ceiling_flat_01":
        add_box(f"{preset_id}_slab", (room_w, room_d, 0.04), (center_x, center_y, wall_h - 0.02), collection, materials["ceiling_white"], shared)
    elif preset_id == "ceiling_perimeter_step_01":
        band = 0.34
        z = wall_h - 0.13
        add_box(f"{preset_id}_band_left", (band, room_d, 0.18), (center_x - room_w / 2 + band / 2, center_y, z), collection, materials["ceiling_white"], shared)
        add_box(f"{preset_id}_band_right", (band, room_d, 0.18), (center_x + room_w / 2 - band / 2, center_y, z), collection, materials["ceiling_white"], shared)
        add_box(f"{preset_id}_band_back", (room_w - 2 * band, band, 0.18), (center_x, center_y + room_d / 2 - band / 2, z), collection, materials["ceiling_white"], shared)
        add_box(f"{preset_id}_band_front", (room_w - 2 * band, band, 0.18), (center_x, center_y - room_d / 2 + band / 2, z), collection, materials["ceiling_white"], shared)
        add_box(f"{preset_id}_center", (room_w - 2 * band, room_d - 2 * band, 0.04), (center_x, center_y, wall_h - 0.02), collection, materials["ceiling_white"], shared)
    elif preset_id == "ceiling_perimeter_cove_01":
        band = preset["perimeter_band_mm"] / 1000.0
        cove = preset["cove_width_mm"] / 1000.0
        z = wall_h - drop_height_m / 2
        for name, size, position in (
            ("left", (band, room_d, drop_height_m), (center_x - room_w / 2 + band / 2, center_y, z)),
            ("right", (band, room_d, drop_height_m), (center_x + room_w / 2 - band / 2, center_y, z)),
            ("back", (room_w - 2 * band, band, drop_height_m), (center_x, center_y + room_d / 2 - band / 2, z)),
            ("front", (room_w - 2 * band, band, drop_height_m), (center_x, center_y - room_d / 2 + band / 2, z)),
        ):
            add_box(f"{preset_id}_band_{name}", size, position, collection, materials["ceiling_white"], shared)
        add_box(f"{preset_id}_center", (room_w - 2 * (band + cove), room_d - 2 * (band + cove), 0.04), (center_x, center_y, wall_h - 0.02), collection, materials["ceiling_white"], shared)
        light_z = wall_h - drop_height_m + 0.018
        add_box(f"{preset_id}_cove_light", (room_w - 2 * band, room_d - 2 * band, 0.018), (center_x, center_y, light_z), collection, materials["ceiling_cove_light"], {**shared, "surface_role": "cove_light_reference"})
    elif preset_id == "ceiling_floating_shadow_gap_01":
        gap = preset["shadow_gap_mm"] / 1000.0
        z = wall_h - drop_height_m / 2
        add_box(f"{preset_id}_shadow_recess", (room_w - 2 * gap, room_d - 2 * gap, 0.025), (center_x, center_y, wall_h - 0.015), collection, materials["ceiling_shadow_gap"], {**shared, "surface_role": "shadow_gap"})
        add_box(f"{preset_id}_floating_plate", (room_w - 4 * gap, room_d - 4 * gap, drop_height_m), (center_x, center_y, z), collection, materials["ceiling_white"], shared)
    elif preset_id == "ceiling_timber_slatted_01":
        slat_width = preset["slat_width_mm"] / 1000.0
        slat_gap = preset["slat_gap_mm"] / 1000.0
        pitch = slat_width + slat_gap
        count = max(1, int((room_w - 0.08) / pitch))
        used_width = count * pitch - slat_gap
        start_x = center_x - used_width / 2 + slat_width / 2
        underside = wall_h - drop_height_m
        add_box(
            f"{preset_id}_shadow_backing",
            (room_w - 0.08, room_d - 0.08, 0.02),
            (center_x, center_y, wall_h - 0.04),
            collection,
            materials["ceiling_shadow_gap"],
            {**shared, "surface_role": "slat_shadow_backing"},
        )
        timber_material = materials.get("floor_character_oak_wideplank_matte_01", materials["floor_light_oak_matte_01"])
        for index in range(count):
            add_box(
                f"{preset_id}_slat_{index}",
                (slat_width, room_d - 0.08, 0.045),
                (start_x + index * pitch, center_y, underside + 0.0225),
                collection,
                timber_material,
                {**shared, "surface_role": "timber_slat", "slat_index": index},
                bevel=0.006,
            )
    elif preset_id == "ceiling_shallow_coffer_grid_01":
        beam_width = preset["beam_width_mm"] / 1000.0
        module = preset["grid_module_mm"] / 1000.0
        add_box(f"{preset_id}_base", (room_w - 0.04, room_d - 0.04, 0.035), (center_x, center_y, wall_h - 0.0175), collection, materials["ceiling_white"], shared)
        beam_z = wall_h - drop_height_m / 2
        x = center_x - room_w / 2 + module
        beam_index = 0
        while x < center_x + room_w / 2 - module * 0.35:
            add_box(f"{preset_id}_beam_x_{beam_index}", (beam_width, room_d - 0.08, drop_height_m), (x, center_y, beam_z), collection, materials["ceiling_white"], {**shared, "surface_role": "coffer_beam"}, bevel=0.012)
            x += module
            beam_index += 1
        y = center_y - room_d / 2 + module
        while y < center_y + room_d / 2 - module * 0.35:
            add_box(f"{preset_id}_beam_y_{beam_index}", (room_w - 0.08, beam_width, drop_height_m), (center_x, y, beam_z), collection, materials["ceiling_white"], {**shared, "surface_role": "coffer_beam"}, bevel=0.012)
            y += module
            beam_index += 1
    elif preset_id == "ceiling_exposed_concrete_shadow_track_01":
        concrete_material = materials.get("tile_light_microcement_01", materials["wall_core"])
        add_box(f"{preset_id}_slab", (room_w - 0.04, room_d - 0.04, 0.035), (center_x, center_y, wall_h - 0.0175), collection, concrete_material, {**shared, "surface_role": "exposed_concrete"})
        track_width = preset["track_width_mm"] / 1000.0
        track_offset = min(preset["track_offset_mm"] / 1000.0, room_w * 0.28)
        for index, offset in enumerate((-track_offset, track_offset)):
            add_box(f"{preset_id}_track_{index}", (track_width, room_d - 0.12, 0.028), (center_x + offset, center_y, wall_h - 0.049), collection, materials["ceiling_shadow_gap"], {**shared, "surface_role": "shadow_track"}, bevel=0.004)
    elif preset_id == "ceiling_curved_cove_01":
        band_total = min(preset["perimeter_band_mm"] / 1000.0, room_w * 0.22, room_d * 0.22)
        steps = 5
        step_band = band_total / steps
        for step in range(steps):
            inset = step * step_band
            ring_width = step_band + 0.012
            progress = step / max(1, steps - 1)
            underside = wall_h - drop_height_m * (1 - progress * progress)
            for name, size, position in (
                ("left", (ring_width, room_d - inset * 2, 0.04), (center_x - room_w / 2 + inset + ring_width / 2, center_y, underside)),
                ("right", (ring_width, room_d - inset * 2, 0.04), (center_x + room_w / 2 - inset - ring_width / 2, center_y, underside)),
                ("front", (room_w - (inset + ring_width) * 2, ring_width, 0.04), (center_x, center_y - room_d / 2 + inset + ring_width / 2, underside)),
                ("back", (room_w - (inset + ring_width) * 2, ring_width, 0.04), (center_x, center_y + room_d / 2 - inset - ring_width / 2, underside)),
            ):
                add_box(f"{preset_id}_{name}_{step}", size, position, collection, materials["ceiling_white"], {**shared, "surface_role": "curved_cove_step", "curve_step": step}, bevel=0.015)
        cove = preset["cove_width_mm"] / 1000.0
        add_box(f"{preset_id}_cove_light", (room_w - band_total * 2, room_d - band_total * 2, 0.012), (center_x, center_y, wall_h - drop_height_m + cove * 0.3), collection, materials["ceiling_cove_light"], {**shared, "surface_role": "cove_light_reference"})
    elif preset_id == "ceiling_kitchen_bath_panel_01":
        module_w, module_d = [value / 1000.0 for value in preset["module_size_mm"]]
        underside = wall_h - drop_height_m
        columns = math.ceil(room_w / module_w)
        rows = math.ceil(room_d / module_d)
        for column_index in range(columns):
            for row_index in range(rows):
                x1 = center_x - room_w / 2 + column_index * module_w
                y1 = center_y - room_d / 2 + row_index * module_d
                width = min(module_w - 0.006, center_x + room_w / 2 - x1)
                depth = min(module_d - 0.006, center_y + room_d / 2 - y1)
                if width <= 0 or depth <= 0:
                    continue
                add_box(
                    f"{preset_id}_panel_{column_index}_{row_index}",
                    (width, depth, 0.025),
                    (x1 + width / 2, y1 + depth / 2, underside + 0.0125),
                    collection,
                    materials["ceiling_panel"],
                    {**shared, "module_size_mm": preset["module_size_mm"]},
                )
    add_text(preset_id.replace("_01", ""), (center_x, center_y - room_d / 2 - 0.28, 0.06), 0.20, collection, materials["label_light"])


def build_ceiling_catalog(collection: bpy.types.Collection, materials: dict[str, bpy.types.Material]) -> None:
    # Arrange the cutaways on an X-Z presentation wall. Depth-stacking the
    # rooms makes the rear labels and ceiling undersides occlude each other.
    for index, preset in enumerate(CEILING_ASSETS):
        center_x = 14.0 + (index % 3) * 4.0
        row = index // 3
        existing_objects = set(collection.objects)
        add_ceiling_mockup(center_x, 4.3, preset["id"], collection, materials)
        z_offset = (2 - row) * 3.2
        for obj in set(collection.objects) - existing_objects:
            obj.location.z += z_offset


def add_camera(name: str, location, target, lens: float = 45.0, ortho_scale: float | None = None) -> bpy.types.Object:
    camera_data = bpy.data.cameras.new(name=f"{name}_Data")
    camera = bpy.data.objects.new(name, camera_data)
    bpy.context.scene.collection.objects.link(camera)
    camera.location = location
    direction = Vector(target) - camera.location
    camera.rotation_euler = direction.to_track_quat("-Z", "Y").to_euler()
    camera_data.lens = lens
    if ortho_scale is not None:
        camera_data.type = "ORTHO"
        camera_data.ortho_scale = ortho_scale
    return camera


def add_lighting() -> None:
    world = bpy.context.scene.world
    world.use_nodes = True
    world.node_tree.nodes["Background"].inputs["Color"].default_value = (0.055, 0.065, 0.080, 1.0)
    world.node_tree.nodes["Background"].inputs["Strength"].default_value = 0.42

    sun_data = bpy.data.lights.new(name="Sun_Key_Data", type="SUN")
    sun_data.energy = 2.2
    sun_data.angle = math.radians(25)
    sun = bpy.data.objects.new("Sun_Key", sun_data)
    bpy.context.scene.collection.objects.link(sun)
    sun.rotation_euler = (math.radians(30), math.radians(-20), math.radians(-35))

    area_data = bpy.data.lights.new(name="Area_Fill_Data", type="AREA")
    area_data.energy = 1100
    area_data.shape = "DISK"
    area_data.size = 7.0
    area = bpy.data.objects.new("Area_Fill", area_data)
    bpy.context.scene.collection.objects.link(area)
    area.location = (5.4, 3.0, 9.0)
    area.rotation_euler = (0.0, 0.0, 0.0)

    catalog_data = bpy.data.lights.new(name="Catalog_Area_Data", type="AREA")
    catalog_data.energy = 950
    catalog_data.shape = "RECTANGLE"
    catalog_data.size = 8.0
    catalog_data.size_y = 5.0
    catalog = bpy.data.objects.new("Catalog_Area", catalog_data)
    bpy.context.scene.collection.objects.link(catalog)
    catalog.location = (18.0, -4.0, 5.0)
    direction = Vector((18.0, 2.0, 2.0)) - catalog.location
    catalog.rotation_euler = direction.to_track_quat("-Z", "Y").to_euler()


def set_collection_render(collection: bpy.types.Collection, hidden: bool) -> None:
    for obj in collection.all_objects:
        obj.hide_render = hidden


def render_preview(
    camera: bpy.types.Object,
    filepath: Path,
    resolution: tuple[int, int],
) -> None:
    scene = bpy.context.scene
    scene.camera = camera
    scene.render.resolution_x = resolution[0]
    scene.render.resolution_y = resolution[1]
    scene.render.resolution_percentage = 100
    scene.render.filepath = str(filepath)
    bpy.ops.render.render(write_still=True)


def export_house_glb(house_collection: bpy.types.Collection) -> None:
    bpy.ops.object.select_all(action="DESELECT")
    for obj in house_collection.all_objects:
        if obj.type in {"MESH", "CURVE"}:
            obj.hide_set(False)
            obj.select_set(True)
    bpy.ops.export_scene.gltf(
        filepath=str(GLB_PATH),
        export_format="GLB",
        use_selection=True,
        export_apply=True,
        export_extras=True,
        export_yup=True,
        # The browser replaces surface materials from the canonical paint/PBR
        # catalog. Placeholder materials preserve stable names without embedding
        # the same 4K maps repeatedly inside the structural house GLB.
        export_materials="PLACEHOLDER",
    )
    bpy.ops.object.select_all(action="DESELECT")


def write_manifests() -> None:
    generated_at = datetime.now(timezone.utc).isoformat()
    manifest, cards = build_asset_knowledge(
        ASSETS,
        generated_at=generated_at,
        generator="blender/generate_house_assets.py",
    )
    manifest["blender_version"] = bpy.app.version_string
    cards["blender_version"] = bpy.app.version_string
    ASSET_MANIFEST_PATH.write_text(
        json.dumps(manifest, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    ASSET_CARDS_PATH.write_text(
        json.dumps(cards, ensure_ascii=False, indent=2), encoding="utf-8"
    )

    wall_face_manifest = []
    for face in WALL_FACES:
        opening_ids = [
            opening["id"]
            for opening in WALL_FACE_OPENINGS.get(face["host_wall_id"], [])
            if min(float(face["end"]), float(opening["end"]))
            - max(float(face["start"]), float(opening["start"])) > 0.001
        ]
        wall_face_manifest.append(
            {
                "id": face["id"],
                "code": face["code"],
                "name_zh": face["name_zh"],
                "room_id": face["room_id"],
                "host_wall_id": face["host_wall_id"],
                "orientation": face["orientation"],
                "default_asset_id": face["asset_id"],
                "geometry": {
                    "axis": face["axis"],
                    "coordinate_m": face["coordinate"],
                    "start_m": face["start"],
                    "end_m": face["end"],
                    "height_m": WALL_HEIGHT,
                    "finish_thickness_m": WALL_FINISH_THICKNESS,
                },
                "opening_ids": opening_ids,
            }
        )

    scene_manifest = {
        "schema_version": "1.1.0",
        "house_id": HOUSE_ID,
        "units": "meters",
        "up_axis": "Z",
        "origin": "southwest_exterior_corner_at_floor_level",
        "dimensions_m": {"width": HOUSE_WIDTH, "depth": HOUSE_DEPTH, "wall_height": WALL_HEIGHT},
        "rooms": [
            {
                **room,
                "surface_ids": {
                    "floor": f"surface_floor_{room['id']}",
                    "ceiling": f"surface_ceiling_{room['id']}",
                },
                "wall_face_ids": [face["id"] for face in WALL_FACES if face["room_id"] == room["id"]],
            }
            for room in ROOMS
        ],
        "wall_faces": wall_face_manifest,
        "agent_wall_assignment": {
            "target_field": "wall_face_id",
            "asset_field": "asset_id",
            "operation": "assign_wall_asset",
            "cardinality": "one_asset_per_wall_face",
        },
        "files": {
            "blend": BLEND_PATH.name,
            "glb": GLB_PATH.name,
            "house_preview": "previews/house_overview.png",
            "material_preview": "previews/material_catalog.png",
            "paint_preview": "previews/paint_catalog.png",
            "ceiling_preview": "previews/ceiling_catalog.png",
        },
        "disclaimer": "Concept/demo geometry; not a construction drawing or code-compliance document.",
    }
    scene_manifest_text = json.dumps(scene_manifest, ensure_ascii=False, indent=2)
    SCENE_MANIFEST_PATH.write_text(scene_manifest_text, encoding="utf-8")
    # Keep a stable, house-specific validation source even when another house
    # is later activated as the viewer's current scene_manifest.json.
    DEDICATED_SCENE_MANIFEST_PATH.write_text(scene_manifest_text, encoding="utf-8")


def main() -> None:
    catalog_only = os.environ.get("ASSET_CATALOG_ONLY") == "1"
    catalog_target = os.environ.get("ASSET_CATALOG_TARGET", "all")
    reset_file()
    scene = bpy.context.scene
    scene["house_id"] = HOUSE_ID
    scene["schema_version"] = "1.1.0"

    materials = build_materials()
    house_collection = make_collection("HOUSE_EXPORT")
    material_catalog = make_collection("ASSET_CATALOG_MATERIALS")
    paint_catalog = make_collection("ASSET_CATALOG_PAINTS")
    ceiling_catalog = make_collection("ASSET_CATALOG_CEILINGS")
    room_labels = make_collection("PREVIEW_ROOM_LABELS")
    build_house(house_collection, materials)
    build_asset_catalog(material_catalog, materials)
    build_paint_catalog(paint_catalog, materials)
    build_ceiling_catalog(ceiling_catalog, materials)
    build_room_labels(room_labels, materials)
    add_lighting()

    house_camera = add_camera("Camera_House_Overview", (14.8, -11.5, 14.2), (5.3, 4.1, 0.65), lens=50.0)
    material_camera = add_camera("Camera_Material_Catalog", (18.0, -13.0, -0.45), (18.0, 0.25, -0.45), ortho_scale=28.0)
    paint_camera = add_camera("Camera_Paint_Catalog", (18.0, -15.0, 4.4), (18.0, 0.25, 4.4), ortho_scale=12.6)
    ceiling_camera = add_camera("Camera_Ceiling_Catalog", (18.0, -12.0, 10.0), (18.0, 4.3, 4.3), ortho_scale=17.5)

    if not catalog_only:
        # House cutaway preview.
        set_collection_render(material_catalog, True)
        set_collection_render(paint_catalog, True)
        set_collection_render(ceiling_catalog, True)
        set_collection_render(room_labels, False)
        for obj in house_collection.all_objects:
            obj.hide_render = bool(obj.get("preview_hide", False))
        render_preview(house_camera, PREVIEW_DIR / "house_overview.png", (960, 760))

    # Material catalog preview.
    if catalog_target in {"all", "material"}:
        set_collection_render(house_collection, True)
        set_collection_render(room_labels, True)
        set_collection_render(material_catalog, False)
        set_collection_render(paint_catalog, True)
        set_collection_render(ceiling_catalog, True)
        render_preview(material_camera, PREVIEW_DIR / "material_catalog.png", (1100, 650))

    # Complete wall-paint catalog and parameter anchors.
    if catalog_target in {"all", "paint"}:
        set_collection_render(house_collection, True)
        set_collection_render(material_catalog, True)
        set_collection_render(paint_catalog, False)
        set_collection_render(ceiling_catalog, True)
        render_preview(paint_camera, PREVIEW_DIR / "paint_catalog.png", (1500, 1500))

    # Ceiling geometry preview.
    if catalog_target in {"all", "ceiling"}:
        set_collection_render(house_collection, True)
        set_collection_render(material_catalog, True)
        set_collection_render(paint_catalog, True)
        set_collection_render(room_labels, True)
        set_collection_render(ceiling_catalog, False)
        render_preview(ceiling_camera, PREVIEW_DIR / "ceiling_catalog.png", (1100, 650))

    if catalog_only:
        print("ASSET_CATALOG_PREVIEWS_COMPLETE")
        return

    # Restore everything before saving. Preview-only hidden states are not persisted.
    set_collection_render(house_collection, False)
    set_collection_render(material_catalog, False)
    set_collection_render(paint_catalog, False)
    set_collection_render(ceiling_catalog, False)
    set_collection_render(room_labels, False)
    export_house_glb(house_collection)
    write_manifests()
    bpy.ops.wm.save_as_mainfile(filepath=str(BLEND_PATH), compress=True)

    print("GENERATION_COMPLETE")
    print(f"BLEND={BLEND_PATH}")
    print(f"GLB={GLB_PATH}")
    print(f"ASSETS={len(ASSETS)}")
    print(f"ROOMS={len(ROOMS)}")


if __name__ == "__main__":
    main()
