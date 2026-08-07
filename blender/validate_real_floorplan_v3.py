"""Validate the real-floorplan v3 Blend/GLB handoff."""

from __future__ import annotations

import json
import math
from datetime import datetime, timezone
from pathlib import Path

import bpy


ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "output"
BLEND = OUT / "house_real_guanggu_12799_v3.blend"
GLB = OUT / "house_real_guanggu_12799_v3.glb"
MANIFEST = OUT / "scene_manifest_real_v3.json"
PREVIEW = OUT / "previews" / "house_real_guanggu_12799_v3.png"
REFERENCE = OUT / "research" / "real_floorplans" / "wuhan_guanggu_127.jpg"
REPORT = OUT / "validation_report_real_v3.json"

checks = []


def check(name, passed, details):
    checks.append({"name": name, "passed": bool(passed), "details": details})


def main():
    for name, path in [("blend", BLEND), ("glb", GLB), ("manifest", MANIFEST), ("preview", PREVIEW), ("reference", REFERENCE)]:
        check(name + "_exists", path.exists(), {"path": str(path), "bytes": path.stat().st_size if path.exists() else 0})
    if not MANIFEST.exists():
        finish(); return
    data = json.loads(MANIFEST.read_text(encoding="utf-8"))
    scene = bpy.context.scene
    check("house_identity", scene.get("house_id") == data.get("house_id") == "house_real_guanggu_12799_v3", {"scene": scene.get("house_id"), "manifest": data.get("house_id")})
    check("metric_units", scene.unit_settings.system == "METRIC" and math.isclose(scene.unit_settings.scale_length, 1.0), {"system": scene.unit_settings.system, "scale": scene.unit_settings.scale_length})
    dims = data["dimension_calibration_m"]
    check("published_axis_calibration", dims == {"overall_width": 10.2, "overall_depth": 10.8, "south_body_width": 7.6, "north_east_wing_depth": 6.1, "wall_height": 3.0}, dims)
    check("published_area", data["area_basis"]["published_building_area_m2"] == 127.99, data["area_basis"])
    check("reference_provenance", data["reference"]["use"] == "geometry_and_dimension_reference_only" and "guanggu_127.jpg" in data["reference"]["local_file"], data["reference"])

    rooms = data["rooms"]
    check("three_bedrooms", len([room for room in rooms if room["type"] == "bedroom"]) == 3, [room["id"] for room in rooms if room["type"] == "bedroom"])
    check("two_bathrooms", len([room for room in rooms if room["type"] == "bathroom"]) == 2, [room["id"] for room in rooms if room["type"] == "bathroom"])
    check("living_dining_kitchen", {"living_room", "dining_room", "kitchen", "foyer"}.issubset({room["id"] for room in rooms}), [room["id"] for room in rooms])
    master = next(room for room in rooms if room["id"] == "master_bedroom")
    master_width = master["rect"][2] - master["rect"][0]
    check("master_bedroom_width", master_width >= 3.15, {"width_m": master_width, "area_m2": master["area_m2"]})
    living = next(room for room in rooms if room["id"] == "living_room")
    check("living_room_not_compact", living["area_m2"] >= 18.0, {"area_m2": living["area_m2"], "rect": living["rect"]})
    check("two_balconies", len(data["balconies"]) == 2 and {item["orientation"] for item in data["balconies"]} == {"south", "north"}, data["balconies"])

    opening_ids = {item["id"] for item in data["openings"]}
    required = {"opening_entry_door", "opening_living_balcony_slider", "opening_master_south_window", "opening_bed2_north_window", "opening_bed3_balcony_door", "opening_kitchen_north_window"}
    check("key_openings", required.issubset(opening_ids), {"missing": sorted(required - opening_ids)})

    objects = list(bpy.data.objects)
    check("reference_layer_packed", any(obj.name == "REFERENCE_RealFloorplan_12799" and obj.type == "EMPTY" for obj in objects) and any(image.packed_file for image in bpy.data.images if image.name == REFERENCE.name), {"reference_object": any(obj.name == "REFERENCE_RealFloorplan_12799" for obj in objects), "packed_images": [image.name for image in bpy.data.images if image.packed_file]})
    check("no_second_home_context", not any(obj.get("context_only") for obj in objects), {"context_objects": [obj.name for obj in objects if obj.get("context_only")]})

    surface_ids = [obj.get("surface_id") for obj in objects if obj.get("surface_id")]
    expected_surfaces = [surface for room in rooms for surface in room["surface_ids"].values()]
    check("surface_ids", len(surface_ids) == len(set(surface_ids)) and set(expected_surfaces).issubset(surface_ids), {"count": len(surface_ids), "unique": len(set(surface_ids))})
    face_ids = [item["id"] for item in data["wall_faces"]]
    object_face_ids = {obj.get("wall_face_id") for obj in objects if obj.get("wall_face_id")}
    check("wall_faces", len(face_ids) == 34 and len(face_ids) == len(set(face_ids)) and set(face_ids).issubset(object_face_ids), {"manifest": len(face_ids), "objects": len(object_face_ids)})
    furniture = [obj for obj in objects if obj.get("reference_only")]
    check("airy_furniture_components", len(furniture) >= 50 and len([obj for obj in furniture if "leg" in str(obj.get("asset_role", ""))]) >= 18, {"components": len(furniture), "leg_components": len([obj for obj in furniture if "leg" in str(obj.get("asset_role", ""))])})
    check("positive_scales", not [obj.name for obj in objects if min(obj.scale) <= 0], {"bad": [obj.name for obj in objects if min(obj.scale) <= 0]})

    if PREVIEW.exists():
        image = bpy.data.images.load(str(PREVIEW), check_existing=True)
        check("preview_resolution", image.size[0] >= 1300 and image.size[1] >= 950, {"size": list(image.size)})

    if GLB.exists():
        original_scene = bpy.context.window.scene
        temp = bpy.data.scenes.new("REAL_V3_GLB_VALIDATION")
        bpy.context.window.scene = temp
        bpy.ops.import_scene.gltf(filepath=str(GLB))
        imported = list(temp.objects)
        imported_surfaces = {obj.get("surface_id") for obj in imported if obj.get("surface_id")}
        imported_faces = {obj.get("wall_face_id") for obj in imported if obj.get("wall_face_id")}
        check("glb_extras_roundtrip", set(expected_surfaces).issubset(imported_surfaces) and set(face_ids).issubset(imported_faces), {"objects": len(imported), "surfaces": len(imported_surfaces), "faces": len(imported_faces)})
        bpy.context.window.scene = original_scene
    finish()


def finish():
    failed = [item for item in checks if not item["passed"]]
    report = {"schema_version": "1.0.0", "generated_at": datetime.now(timezone.utc).isoformat(), "validator": "blender/validate_real_floorplan_v3.py", "blender_version": bpy.app.version_string, "status": "pass" if not failed else "fail", "checks_total": len(checks), "checks_passed": len(checks)-len(failed), "checks_failed": len(failed), "checks": checks}
    REPORT.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    print("REAL_V3_VALIDATION_" + report["status"].upper()); print(f"CHECKS={report['checks_passed']}/{report['checks_total']}")
    for item in failed: print(f"FAILED={item['name']}: {item['details']}")
    if failed: raise SystemExit(1)


if __name__ == "__main__": main()
