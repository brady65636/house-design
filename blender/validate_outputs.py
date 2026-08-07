"""Validate generated Blender, GLB, manifest, and preview deliverables."""

from __future__ import annotations

import json
import sys
from pathlib import Path

import bpy
from mathutils import Vector


ROOT_DIR = Path(__file__).resolve().parents[1]
OUTPUT_DIR = ROOT_DIR / "output"
ASSET_MANIFEST = OUTPUT_DIR / "asset_manifest.json"
ASSET_CARDS = OUTPUT_DIR / "asset_cards.json"
SCENE_MANIFEST = OUTPUT_DIR / "scene_manifest_house_2b2l_90_v1.json"
GLB_PATH = OUTPUT_DIR / "house_2b2l_90_v1.glb"
REPORT_PATH = OUTPUT_DIR / "validation_report.json"

checks = []


def record(name: str, passed: bool, detail) -> None:
    checks.append({"name": name, "passed": bool(passed), "detail": detail})


asset_manifest = json.loads(ASSET_MANIFEST.read_text(encoding="utf-8"))
asset_cards = json.loads(ASSET_CARDS.read_text(encoding="utf-8"))
asset_card_map = asset_cards.get("cards", {})
if not isinstance(asset_card_map, dict):
    raise ValueError("asset_cards.json 缺少 cards 对象")
assets = [
    card["objective_facts"]
    for card in asset_card_map.values()
    if isinstance(card, dict) and isinstance(card.get("objective_facts"), dict)
]
if {asset["id"] for asset in asset_manifest.get("assets", [])} != {
    asset["id"] for asset in assets
}:
    raise ValueError("资产索引与资产卡的 ID 集合不一致")
scene_manifest = json.loads(SCENE_MANIFEST.read_text(encoding="utf-8"))
expected_assets = {asset["id"] for asset in assets}
expected_rooms = {room["id"] for room in scene_manifest["rooms"]}
expected_floor_surfaces = {f"surface_floor_{room_id}" for room_id in expected_rooms}
expected_ceiling_surfaces = {f"surface_ceiling_{room_id}" for room_id in expected_rooms}
expected_wall_face_ids = {face["id"] for face in scene_manifest["wall_faces"]}

house_collection = bpy.data.collections.get("HOUSE_EXPORT")
record("house_collection_exists", house_collection is not None, "HOUSE_EXPORT")
house_objects = list(house_collection.all_objects) if house_collection else []
record("house_has_substantial_geometry", len(house_objects) >= 100, len(house_objects))

material_asset_ids = {
    material.get("asset_id")
    for material in bpy.data.materials
    if material.get("asset_id") in expected_assets
}
geometry_asset_ids = {
    obj.get("preset_id")
    for obj in bpy.data.objects
    if obj.get("preset_id") in expected_assets
}
covered_assets = material_asset_ids | geometry_asset_ids
record("all_manifest_assets_exist_in_blend", covered_assets == expected_assets, sorted(covered_assets))

paint_assets = [asset for asset in assets if asset["category"] == "wall_paint"]
paint_families = {asset.get("family_id") for asset in paint_assets}
paint_combinations = {
    (asset.get("family_id"), asset.get("tone"), asset.get("finish"))
    for asset in paint_assets
}
record(
    "paint_catalog_has_10_families_and_60_unique_variants",
    len(paint_assets) == 60 and len(paint_families) == 10 and len(paint_combinations) == 60,
    {"variants": len(paint_assets), "families": sorted(paint_families)},
)
paint_materials = [
    material
    for material in bpy.data.materials
    if material.get("asset_id") in {asset["id"] for asset in paint_assets}
]
record(
    "all_paint_materials_use_parametric_pbr_nodes",
    len(paint_materials) == 60
    and all(
        material.get("source_type") == "project_owned_parametric_pbr"
        and material.node_tree
        and any(node.type == "NORMAL_MAP" for node in material.node_tree.nodes)
        and any(node.type == "TEX_IMAGE" and "roughness" in node.name.lower() for node in material.node_tree.nodes)
        for material in paint_materials
    ),
    len(paint_materials),
)
paint_texture_results = {}
for filename in (
    "paint_micro_basecolor_4k.jpg",
    "paint_micro_normal_gl_4k.jpg",
    "paint_micro_roughness_matte_4k.jpg",
    "paint_micro_roughness_eggshell_4k.jpg",
):
    path = ROOT_DIR / "viewer" / "public" / "assets" / "paints" / filename
    if not path.exists():
        paint_texture_results[filename] = "missing"
        continue
    image = bpy.data.images.load(str(path), check_existing=True)
    paint_texture_results[filename] = list(image.size)
record(
    "paint_pbr_textures_are_complete_4k",
    all(value == [4096, 4096] for value in paint_texture_results.values()),
    paint_texture_results,
)
paint_catalog_collection = bpy.data.collections.get("ASSET_CATALOG_PAINTS")
paint_panels = [
    obj
    for obj in paint_catalog_collection.all_objects
    if obj.get("category") == "wall_paint" and obj.get("preview_object")
] if paint_catalog_collection else []
record("paint_catalog_contains_all_60_panels", len(paint_panels) == 60, len(paint_panels))

wallpaper_assets = [asset for asset in assets if asset["category"] == "wallpaper"]
wallpaper_ids = {asset["id"] for asset in wallpaper_assets}
wallpaper_families = {asset.get("family") for asset in wallpaper_assets}
record(
    "wallpaper_catalog_has_8_original_families",
    len(wallpaper_assets) == 8
    and len(wallpaper_ids) == 8
    and len(wallpaper_families) == 8
    and all(asset.get("license") == "project_owned" for asset in wallpaper_assets),
    {"assets": len(wallpaper_assets), "families": sorted(wallpaper_families)},
)
wallpaper_materials = [
    material for material in bpy.data.materials if material.get("asset_id") in wallpaper_ids
]
record(
    "all_wallpaper_materials_use_imagegen_pbr_nodes",
    len(wallpaper_materials) == 8
    and all(
        material.get("source_type") == "project_original_imagegen_pbr"
        and material.node_tree
        and sum(node.type == "TEX_IMAGE" for node in material.node_tree.nodes) == 4
        and any(node.type == "NORMAL_MAP" for node in material.node_tree.nodes)
        and any(node.type == "BUMP" for node in material.node_tree.nodes)
        for material in wallpaper_materials
    ),
    len(wallpaper_materials),
)
wallpaper_texture_results = {}
for asset in wallpaper_assets:
    expected_size = asset["output_resolution"]
    map_results = {}
    for suffix, extension in (
        ("basecolor", ".jpg"),
        ("normal_gl", ".png"),
        ("roughness", ".png"),
        ("height", ".png"),
    ):
        path = OUTPUT_DIR / "wallpapers_pbr" / f"{asset['id']}_{suffix}_4k{extension}"
        if not path.exists():
            map_results[suffix] = "missing"
            continue
        image = bpy.data.images.load(str(path), check_existing=True)
        map_results[suffix] = list(image.size)
    wallpaper_texture_results[asset["id"]] = map_results
record(
    "wallpaper_pbr_textures_are_complete_at_declared_resolution",
    all(
        all(size == asset["output_resolution"] for size in wallpaper_texture_results[asset["id"]].values())
        for asset in wallpaper_assets
    ),
    wallpaper_texture_results,
)
material_catalog_collection = bpy.data.collections.get("ASSET_CATALOG_MATERIALS")
wallpaper_panels = [
    obj
    for obj in material_catalog_collection.all_objects
    if obj.get("asset_id") in wallpaper_ids and obj.get("preview_object")
] if material_catalog_collection else []
record("material_catalog_contains_all_8_wallpapers", len(wallpaper_panels) == 8, len(wallpaper_panels))

floor_assets = [asset for asset in assets if asset["category"] == "wood_floor"]
tile_assets = [asset for asset in assets if asset["category"] == "tile"]
surface_assets = [*floor_assets, *tile_assets]
surface_ids = {asset["id"] for asset in surface_assets}
record(
    "surface_catalog_has_6_floors_and_8_tiles",
    len(floor_assets) == 6 and len(tile_assets) == 8 and len(surface_ids) == 14,
    {"floors": len(floor_assets), "tiles": len(tile_assets)},
)
surface_materials = [material for material in bpy.data.materials if material.get("asset_id") in surface_ids]
record(
    "all_floor_and_tile_materials_use_pbr_image_nodes",
    len(surface_materials) == 14
    and all(
        material.node_tree
        and sum(node.type == "TEX_IMAGE" for node in material.node_tree.nodes) == 3
        and any(node.type == "NORMAL_MAP" for node in material.node_tree.nodes)
        and any(node.type == "TEX_IMAGE" and "roughness" in node.name.lower() for node in material.node_tree.nodes)
        for material in surface_materials
    ),
    len(surface_materials),
)
surface_texture_results = {}
for asset in surface_assets:
    map_results = {}
    for suffix, extension in (
        ("basecolor", ".jpg"),
        ("normal_gl", ".png"),
        ("roughness", ".png"),
        ("height", ".png"),
    ):
        path = OUTPUT_DIR / "surfaces_pbr" / f"{asset['id']}_{suffix}_4k{extension}"
        if not path.exists():
            map_results[suffix] = "missing"
            continue
        image = bpy.data.images.load(str(path), check_existing=True)
        map_results[suffix] = list(image.size)
    surface_texture_results[asset["id"]] = map_results
record(
    "floor_and_tile_pbr_masters_are_complete_4k",
    all(all(size == [4096, 4096] for size in maps.values()) for maps in surface_texture_results.values()),
    surface_texture_results,
)
surface_panels = [
    obj
    for obj in material_catalog_collection.all_objects
    if obj.get("asset_id") in surface_ids and obj.get("preview_object")
] if material_catalog_collection else []
record("material_catalog_contains_all_14_floor_and_tile_panels", len(surface_panels) == 14, len(surface_panels))

ceiling_assets = [asset for asset in assets if asset["category"] == "ceiling"]
ceiling_ids = {asset["id"] for asset in ceiling_assets}
ceiling_preset_objects = [obj for obj in bpy.data.objects if obj.get("preset_id") in ceiling_ids]
record(
    "ceiling_catalog_has_5_constructible_geometry_presets",
    len(ceiling_assets) == 5
    and len(ceiling_ids) == 5
    and all(any(obj.get("preset_id") == asset_id for obj in ceiling_preset_objects) for asset_id in ceiling_ids),
    {"presets": sorted(ceiling_ids), "geometry_objects": len(ceiling_preset_objects)},
)

house_floor_surfaces = {obj.get("surface_id") for obj in house_objects if obj.get("surface_role") == "floor"}
house_ceiling_surfaces = {obj.get("surface_id") for obj in house_objects if obj.get("surface_role") == "ceiling"}
house_wall_face_ids = {obj.get("wall_face_id") for obj in house_objects if obj.get("wall_face_id")}
record("all_room_floor_surfaces_exist", expected_floor_surfaces <= house_floor_surfaces, sorted(house_floor_surfaces))
record("all_room_ceiling_surfaces_exist", expected_ceiling_surfaces <= house_ceiling_surfaces, sorted(house_ceiling_surfaces))
record("all_30_numbered_wall_faces_exist", len(expected_wall_face_ids) == 30 and expected_wall_face_ids == house_wall_face_ids, sorted(house_wall_face_ids))
record(
    "wall_faces_have_one_room_and_valid_asset",
    all(
        obj.get("room_id") in expected_rooms
        and obj.get("host_wall_id")
        and obj.get("asset_id") in expected_assets
        for obj in house_objects
        if obj.get("wall_face_id")
    ),
    {"wall_face_meshes": sum(1 for obj in house_objects if obj.get("wall_face_id"))},
)
record(
    "legacy_wall_surface_ids_removed",
    not any(
        isinstance(obj.get("surface_id"), str) and obj.get("surface_id").startswith("surface_wall_")
        for obj in house_objects
    ),
    sorted({obj.get("surface_id") for obj in house_objects if obj.get("surface_id")}),
)

house_asset_refs = {obj.get("asset_id") for obj in house_objects if obj.get("asset_id")}
missing_house_assets = {
    asset_id
    for asset_id in expected_assets
    if asset_id.startswith(("paint_", "wallpaper_", "floor_", "tile_"))
    and asset_id not in house_asset_refs
    and asset_id not in material_asset_ids
}
record("house_assets_resolve_to_library", not missing_house_assets, sorted(missing_house_assets))

bad_scales = []
for obj in house_objects:
    if obj.type == "MESH" and any(abs(abs(value) - 1.0) > 1e-5 for value in obj.scale):
        bad_scales.append({"object": obj.name, "scale": list(obj.scale)})
record("house_mesh_transforms_applied", not bad_scales, bad_scales[:10])

living_west_parts = [obj for obj in house_objects if obj.get("wall_face_id") == "wall_face_002"]
living_west = living_west_parts[0] if len(living_west_parts) == 1 else None
living_west_expected = {
    "location": [0.1005, 2.35, 1.40],
    "dimensions": [0.001, 4.51, 2.80],
}
living_west_actual = None
if living_west:
    living_west_actual = {
        "location": list(living_west.location),
        "dimensions": list(living_west.dimensions),
    }
living_west_is_numbered_finish = bool(living_west) and all(
    abs(actual - expected) <= 1e-4
    for values, expected_values in (
        (living_west.location, living_west_expected["location"]),
        (living_west.dimensions, living_west_expected["dimensions"]),
    )
    for actual, expected in zip(values, expected_values)
)
record(
    "living_west_wall_face_is_flush_and_covers_corners",
    living_west_is_numbered_finish,
    {"expected": living_west_expected, "actual": living_west_actual},
)
living_west_uv_bounds = None
if living_west and living_west.data.uv_layers.active:
    coordinates = [tuple(item.uv) for item in living_west.data.uv_layers.active.data]
    living_west_uv_bounds = {
        "min": [min(item[index] for item in coordinates) for index in range(2)],
        "max": [max(item[index] for item in coordinates) for index in range(2)],
    }
record(
    "living_west_wall_uses_metric_upright_uv",
    bool(living_west_uv_bounds)
    and abs(living_west_uv_bounds["min"][0]) <= 1e-4
    and abs(living_west_uv_bounds["min"][1]) <= 1e-4
    and abs(living_west_uv_bounds["max"][0] - 4.51) <= 1e-4
    and abs(living_west_uv_bounds["max"][1] - 2.80) <= 1e-4,
    living_west_uv_bounds,
)

world_points = []
for obj in house_objects:
    if obj.type == "MESH":
        world_points.extend(obj.matrix_world @ Vector(corner) for corner in obj.bound_box)
if world_points:
    bounds = {
        "min": [min(point[i] for point in world_points) for i in range(3)],
        "max": [max(point[i] for point in world_points) for i in range(3)],
    }
else:
    bounds = {"min": [], "max": []}
within_expected_bounds = bool(world_points) and (
    bounds["min"][0] >= -0.2
    and bounds["min"][1] >= -0.2
    and bounds["min"][2] >= -0.1
    and bounds["max"][0] <= 11.0
    and bounds["max"][1] <= 8.6
    and bounds["max"][2] <= 2.9
)
record("house_geometry_within_expected_metric_bounds", within_expected_bounds, bounds)

record("glb_exists_and_nontrivial", GLB_PATH.exists() and GLB_PATH.stat().st_size > 100_000, GLB_PATH.stat().st_size if GLB_PATH.exists() else 0)

preview_expectations = {
    "house_overview.png": (960, 760),
    "material_catalog.png": (1100, 650),
    "paint_catalog.png": (1500, 1500),
    "ceiling_catalog.png": (1100, 650),
    "wallpaper_catalog.png": (2560, 940),
    "wallpaper_repeat_check.png": (2240, 1120),
    "surface_catalog.png": (2240, 1560),
    "surface_repeat_check.png": (2080, 2216),
}
preview_results = {}
for filename, expected_size in preview_expectations.items():
    path = OUTPUT_DIR / "previews" / filename
    if not path.exists():
        preview_results[filename] = "missing"
        continue
    image = bpy.data.images.load(str(path), check_existing=False)
    preview_results[filename] = list(image.size)
record(
    "preview_images_have_expected_dimensions",
    all(tuple(preview_results.get(name, [])) == expected for name, expected in preview_expectations.items()),
    preview_results,
)

# Import the GLB into a clean scene to verify that it is consumable and that
# custom IDs survived export as glTF extras.
validation_scene = bpy.data.scenes.new("GLB_Validation")
bpy.context.window.scene = validation_scene
bpy.ops.import_scene.gltf(filepath=str(GLB_PATH))
imported_objects = list(validation_scene.objects)
imported_surface_ids = {obj.get("surface_id") for obj in imported_objects if obj.get("surface_id")}
imported_wall_face_ids = {obj.get("wall_face_id") for obj in imported_objects if obj.get("wall_face_id")}
imported_asset_ids = {obj.get("asset_id") for obj in imported_objects if obj.get("asset_id")}
record("glb_imports_with_substantial_geometry", len(imported_objects) >= 100, len(imported_objects))
record("glb_preserves_floor_surface_ids", expected_floor_surfaces <= imported_surface_ids, sorted(imported_surface_ids))
record("glb_preserves_all_wall_face_ids", expected_wall_face_ids == imported_wall_face_ids, sorted(imported_wall_face_ids))
record(
    "glb_preserves_material_assignment_asset_ids",
    {"floor_light_oak_matte_01", "floor_honey_oak_matte_01", "tile_warm_travertine_01", "tile_light_microcement_01"} <= imported_asset_ids,
    sorted(imported_asset_ids),
)

passed = all(check["passed"] for check in checks)
report = {
    "passed": passed,
    "blender_version": bpy.app.version_string,
    "stats": {
        "expected_assets": len(expected_assets),
        "expected_rooms": len(expected_rooms),
        "expected_wall_faces": len(expected_wall_face_ids),
        "blend_house_objects": len(house_objects),
        "glb_imported_objects": len(imported_objects),
    },
    "checks": checks,
}
REPORT_PATH.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
print(json.dumps(report, ensure_ascii=False, indent=2))
if not passed:
    sys.exit(1)
