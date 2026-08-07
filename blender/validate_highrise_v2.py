"""Validate the generated highrise v2 Blend, GLB, manifest and previews.

Run after loading the Blend file:
    blender --background output/house_3b2l_127_v2.blend \
      --python blender/validate_highrise_v2.py
"""

from __future__ import annotations

import json
import math
from datetime import datetime, timezone
from pathlib import Path

import bpy


ROOT_DIR = Path(__file__).resolve().parents[1]
OUTPUT_DIR = ROOT_DIR / "output"
MANIFEST_PATH = OUTPUT_DIR / "scene_manifest_highrise_v2.json"
GLB_PATH = OUTPUT_DIR / "house_3b2l_127_v2.glb"
BLEND_PATH = OUTPUT_DIR / "house_3b2l_127_v2.blend"
REPORT_PATH = OUTPUT_DIR / "validation_report_highrise_v2.json"
PREVIEW_PATHS = [
    OUTPUT_DIR / "previews" / "highrise_standard_floor_overview.png",
    OUTPUT_DIR / "previews" / "highrise_east_unit_overview.png",
]


checks: list[dict] = []


def check(name: str, passed: bool, details) -> None:
    checks.append({"name": name, "passed": bool(passed), "details": details})


def main() -> None:
    check("blend_exists", BLEND_PATH.exists(), {"path": str(BLEND_PATH), "bytes": BLEND_PATH.stat().st_size if BLEND_PATH.exists() else 0})
    check("glb_exists", GLB_PATH.exists(), {"path": str(GLB_PATH), "bytes": GLB_PATH.stat().st_size if GLB_PATH.exists() else 0})
    check("manifest_exists", MANIFEST_PATH.exists(), str(MANIFEST_PATH))
    if not MANIFEST_PATH.exists():
        finish()
        return

    manifest = json.loads(MANIFEST_PATH.read_text(encoding="utf-8"))
    scene = bpy.context.scene
    check("house_identity", scene.get("house_id") == "house_3b2l_127_v2" == manifest.get("house_id"), {"scene": scene.get("house_id"), "manifest": manifest.get("house_id")})
    check("metric_units", scene.unit_settings.system == "METRIC" and math.isclose(scene.unit_settings.scale_length, 1.0), {"system": scene.unit_settings.system, "scale_length": scene.unit_settings.scale_length})

    dimensions = manifest["dimensions_m"]
    check("unit_envelope", dimensions["east_unit_width"] >= 10.0 and dimensions["east_unit_depth"] >= 10.0 and math.isclose(dimensions["wall_height"], 3.0), dimensions)
    area = manifest["area_basis"]
    check("area_basis_explicit", area["marketed_gross_area_m2"] == 127.0 and 95.0 <= area["modeled_net_usable_area_m2"] <= 96.0 and area["estimated_in_suite_building_area_m2"] > area["modeled_net_usable_area_m2"], area)

    rooms = manifest["rooms"]
    room_ids = [room["id"] for room in rooms]
    types = [room["type"] for room in rooms]
    check("three_bedrooms", types.count("bedroom") == 3, {"bedroom_ids": [room["id"] for room in rooms if room["type"] == "bedroom"]})
    check("two_bathrooms", types.count("bathroom") == 2, {"bathroom_ids": [room["id"] for room in rooms if room["type"] == "bathroom"]})
    check("complete_daily_program", all(required in room_ids for required in ["living_room", "dining_room", "kitchen", "foyer", "hall_storage"]), room_ids)
    hall = next(room for room in rooms if room["id"] == "hall_storage")
    hall_width = hall["rect"][2] - hall["rect"][0]
    check("corridor_width", hall_width >= 1.10 - 1e-6, {"width_m": round(hall_width, 3)})

    rules = manifest["planning_rules"]
    check("south_three_bays", rules["south_facing_bays"] == ["bedroom_2", "living_room", "master_bedroom"], rules["south_facing_bays"])
    check("north_service_and_bedroom", set(rules["north_service_rooms"]) == {"kitchen", "guest_bath"} and rules["north_secondary_bedroom"] == "bedroom_3", {"service": rules["north_service_rooms"], "bedroom": rules["north_secondary_bedroom"]})
    check("shared_lobby_entry", rules["public_entry_relation"] == "entry_door_opens_to_shared_elevator_lobby", rules["public_entry_relation"])
    check("two_balconies", len(manifest["balconies"]) == 2 and {item["orientation"] for item in manifest["balconies"]} == {"south", "north"}, manifest["balconies"])

    openings = manifest["openings"]
    opening_ids = {opening["id"] for opening in openings}
    required_openings = {
        "opening_entry_door", "opening_living_balcony_slider", "opening_bed2_south_window",
        "opening_master_east_window", "opening_kitchen_utility_door", "opening_bed3_north_window",
        "opening_guest_bath_window", "opening_master_bath_window",
    }
    check("facade_openings", required_openings.issubset(opening_ids), {"required": sorted(required_openings), "present": sorted(opening_ids)})

    objects = list(bpy.data.objects)
    surface_ids = [obj.get("surface_id") for obj in objects if obj.get("surface_id")]
    expected_surface_ids = [surface for room in rooms for surface in room["surface_ids"].values()]
    check("surface_ids_unique", len(surface_ids) == len(set(surface_ids)), {"count": len(surface_ids), "unique": len(set(surface_ids))})
    check("room_surfaces_present", set(expected_surface_ids).issubset(surface_ids), {"expected": len(expected_surface_ids), "present": len(surface_ids)})

    face_ids = [face["id"] for face in manifest["wall_faces"]]
    object_face_ids = {obj.get("wall_face_id") for obj in objects if obj.get("wall_face_id")}
    check("wall_face_ids_unique", len(face_ids) == len(set(face_ids)) and len(face_ids) >= 30, {"manifest_count": len(face_ids), "object_count": len(object_face_ids)})
    check("wall_face_geometry_present", set(face_ids).issubset(object_face_ids), {"missing": sorted(set(face_ids) - object_face_ids)})

    context_zones = {obj.get("zone") for obj in objects if obj.get("context_only")}
    check("standard_floor_context", {"public_lobby", "public_core", "mirrored_west_unit"}.issubset(context_zones), {"zones": sorted(zone for zone in context_zones if zone)})
    check("layout_references", len([obj for obj in objects if obj.get("reference_only")]) >= 20, {"count": len([obj for obj in objects if obj.get("reference_only")])})
    bad_scale = [obj.name for obj in objects if min(obj.scale) <= 0.0]
    check("positive_object_scales", not bad_scale, {"bad_objects": bad_scale})

    preview_details = []
    previews_ok = True
    for path in PREVIEW_PATHS:
        if not path.exists():
            previews_ok = False
            preview_details.append({"path": str(path), "exists": False})
            continue
        image = bpy.data.images.load(str(path), check_existing=True)
        size = list(image.size)
        previews_ok = previews_ok and size[0] >= 1200 and size[1] >= 900
        preview_details.append({"path": str(path), "exists": True, "size": size, "bytes": path.stat().st_size})
    check("preview_outputs", previews_ok, preview_details)

    # Import the GLB into a fresh temporary scene to verify that extras survive
    # the exact handoff consumed by Three.js.
    if GLB_PATH.exists():
        original_scene = bpy.context.window.scene
        import_scene = bpy.data.scenes.new("GLB_VALIDATION_TEMP")
        bpy.context.window.scene = import_scene
        bpy.ops.import_scene.gltf(filepath=str(GLB_PATH))
        imported = list(import_scene.objects)
        imported_surface_ids = {obj.get("surface_id") for obj in imported if obj.get("surface_id")}
        imported_face_ids = {obj.get("wall_face_id") for obj in imported if obj.get("wall_face_id")}
        check("glb_extras_preserved", set(expected_surface_ids).issubset(imported_surface_ids) and set(face_ids).issubset(imported_face_ids), {"imported_objects": len(imported), "surface_ids": len(imported_surface_ids), "wall_face_ids": len(imported_face_ids)})
        bpy.context.window.scene = original_scene

    finish()


def finish() -> None:
    failed = [item for item in checks if not item["passed"]]
    report = {
        "schema_version": "1.0.0", "generated_at": datetime.now(timezone.utc).isoformat(),
        "validator": "blender/validate_highrise_v2.py", "blender_version": bpy.app.version_string,
        "status": "pass" if not failed else "fail", "checks_total": len(checks),
        "checks_passed": len(checks) - len(failed), "checks_failed": len(failed), "checks": checks,
    }
    REPORT_PATH.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    print("HIGHRISE_V2_VALIDATION_" + report["status"].upper())
    print(f"CHECKS={report['checks_passed']}/{report['checks_total']}")
    for item in failed:
        print(f"FAILED={item['name']}: {item['details']}")
    if failed:
        raise SystemExit(1)


if __name__ == "__main__":
    main()
