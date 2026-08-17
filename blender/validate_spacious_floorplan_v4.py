"""Validate the spacious real-floorplan v4 Blend/GLB handoff."""

from __future__ import annotations

import json
import math
from datetime import datetime, timezone
from pathlib import Path

import bpy
import mathutils


ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "output"
BLEND = OUT / "house_spacious_yunkuo_135_v4.blend"
GLB = OUT / "house_spacious_yunkuo_135_v4.glb"
MANIFEST = OUT / "scene_manifest_spacious_v4.json"
PREVIEW = OUT / "previews" / "house_spacious_yunkuo_135_v4.png"
REFERENCE = OUT / "research" / "spacious_floorplans" / "heda_135_ldkg.jpg"
REPORT = OUT / "validation_report_spacious_v4.json"
ASSET_MANIFEST = OUT / "asset_manifest.json"

checks = []


def check(name, passed, details):
    checks.append({"name": name, "passed": bool(passed), "details": details})


def required_exterior_finish_coverage(faces):
    """Guard the exterior room sides that were omitted by the legacy two-room wall list."""
    required = {
        ("dining_room", "wall_ext_west"),
        ("master_bedroom", "wall_ext_south"),
        ("guest_bath", "wall_ext_north"),
    }
    actual = {(face["room_id"], face["host_wall_id"]) for face in faces}
    missing = sorted(required - actual)
    return not missing, {"required": sorted(required), "missing": missing}


def wall_finish_geometry(objects, faces):
    """Verify every finish sits outside its wall core in world space."""
    tolerance = 1e-5
    failures = []
    checked_objects = 0
    objects_by_face = {}
    for obj in objects:
        face_id = obj.get("wall_face_id")
        if face_id:
            objects_by_face.setdefault(face_id, []).append(obj)

    for face in faces:
        sign = 1 if face["orientation"] in {"north", "east"} else -1
        core_center = float(face["wall_core_center_coordinate"])
        core_thickness = float(face["wall_core_thickness_m"])
        finish_thickness = float(face["finish_thickness_m"])
        expected_center = core_center + sign * (core_thickness / 2 + finish_thickness / 2)
        core_outer = core_center + sign * core_thickness / 2
        declared_center = float(face["coordinate"])
        declared_outer = declared_center + sign * finish_thickness / 2
        declared_clearance = sign * (declared_outer - core_outer)
        if not (
            math.isclose(declared_center, expected_center, abs_tol=tolerance)
            and math.isclose(
                declared_clearance,
                float(face["finish_outer_clearance_m"]),
                abs_tol=tolerance,
            )
            and declared_clearance > tolerance
        ):
            failures.append({
                "face_id": face["id"],
                "reason": "manifest",
                "center": declared_center,
                "expected_center": expected_center,
                "clearance": declared_clearance,
            })

        thin_axis = 1 if face["axis"] == "X" else 0
        for obj in objects_by_face.get(face["id"], []):
            checked_objects += 1
            coordinates = [
                (obj.matrix_world @ mathutils.Vector(corner))[thin_axis]
                for corner in obj.bound_box
            ]
            actual_min = min(coordinates)
            actual_max = max(coordinates)
            actual_center = (actual_min + actual_max) / 2
            actual_thickness = actual_max - actual_min
            actual_outer = actual_max if sign > 0 else actual_min
            actual_clearance = sign * (actual_outer - core_outer)
            if not (
                math.isclose(actual_center, expected_center, abs_tol=tolerance)
                and math.isclose(actual_thickness, finish_thickness, abs_tol=tolerance)
                and actual_clearance > tolerance
            ):
                failures.append({
                    "face_id": face["id"],
                    "object": obj.name,
                    "reason": "object",
                    "center": actual_center,
                    "thickness": actual_thickness,
                    "clearance": actual_clearance,
                })

    return not failures and checked_objects > 0, {
        "faces": len(faces),
        "objects": checked_objects,
        "failures": failures[:12],
    }


def metric_floor_uvs(objects):
    failures = []
    checked = 0
    for obj in objects:
        if obj.get("surface_role") not in {"floor", "balcony_floor"}:
            continue
        checked += 1
        uv_layer = obj.data.uv_layers.active
        if uv_layer is None:
            failures.append({"object": obj.name, "reason": "missing_uv"})
            continue
        uvs = [loop.uv for loop in uv_layer.data]
        span_u = max(uv.x for uv in uvs) - min(uv.x for uv in uvs)
        span_v = max(uv.y for uv in uvs) - min(uv.y for uv in uvs)
        if not (
            math.isclose(span_u, obj.dimensions.x, abs_tol=1e-4)
            and math.isclose(span_v, obj.dimensions.y, abs_tol=1e-4)
        ):
            failures.append({"object": obj.name, "uv_span": [span_u, span_v], "dimensions": list(obj.dimensions)})
    return checked > 0 and not failures, {"checked": checked, "failures": failures[:12]}


def hard_finish_details(objects, manifest):
    room_surfaces = [
        obj for obj in objects
        if obj.get("surface_role") in {"floor", "ceiling"} and obj.get("room_id")
    ]
    underlaid = [
        obj for obj in room_surfaces
        if float(obj.get("surface_underlay_m", 0.0)) >= 0.08 and obj.get("design_rect_m")
    ]
    expected_thresholds = sum(
        float(opening.get("bottom", 0.0)) <= 0.001
        for opening in manifest.get("openings", [])
    )
    thresholds = [obj for obj in objects if obj.get("asset_role") == "architectural_threshold"]
    guardrail_frames = [obj for obj in objects if obj.get("asset_role") == "guardrail_frame"]
    guardrail_glass = [obj for obj in objects if obj.get("asset_role") == "guardrail_glass"]
    expected_room_surface_objects = sum(
        len(room.get("surface_ids", {}))
        * len(room.get("topology_rects", [room.get("rect")]))
        for room in manifest.get("rooms", [])
        if "ceiling" in room.get("surface_ids", {})
    )
    passed = (
        len(room_surfaces) == expected_room_surface_objects
        and len(underlaid) == len(room_surfaces)
        and len(thresholds) == expected_thresholds
        and bool(guardrail_frames)
        and bool(guardrail_glass)
        and all(obj.get("opening_type") == "window" for obj in guardrail_glass)
        and not any(obj.get("reference_only") for obj in [*thresholds, *guardrail_frames, *guardrail_glass])
    )
    return passed, {
        "room_surfaces": len(room_surfaces),
        "expected_room_surfaces": expected_room_surface_objects,
        "underlaid": len(underlaid),
        "thresholds": len(thresholds),
        "expected_thresholds": expected_thresholds,
        "guardrail_frames": len(guardrail_frames),
        "guardrail_glass": len(guardrail_glass),
    }


def room_facing_wall_sides(faces, rooms):
    room_by_id = {room["id"]: room for room in rooms}
    failures = []
    for face in faces:
        room = room_by_id.get(face["room_id"])
        if not room:
            failures.append({"face_id": face["id"], "reason": "unknown_room"})
            continue
        x1, y1, x2, y2 = room["rect"]
        core_coordinate = float(face["wall_core_center_coordinate"])
        if face["axis"] == "X":
            expected = "north" if (y1 + y2) / 2 > core_coordinate else "south"
        else:
            expected = "east" if (x1 + x2) / 2 > core_coordinate else "west"
        if face["orientation"] != expected:
            failures.append({"face_id": face["id"], "actual": face["orientation"], "expected": expected})
    return not failures, {"checked": len(faces), "failures": failures[:12]}


def finish():
    failed = [item for item in checks if not item["passed"]]
    report = {
        "schema_version": "1.0.0",
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "validator": "blender/validate_spacious_floorplan_v4.py",
        "blender_version": bpy.app.version_string,
        "status": "pass" if not failed else "fail",
        "checks_total": len(checks),
        "checks_passed": len(checks)-len(failed),
        "checks_failed": len(failed),
        "checks": checks,
    }
    REPORT.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    print("SPACIOUS_V4_VALIDATION_" + report["status"].upper())
    print(f"CHECKS={report['checks_passed']}/{report['checks_total']}")
    for item in failed:
        print(f"FAILED={item['name']}: {item['details']}")
    if failed:
        raise SystemExit(1)


def main():
    for name, path in [("blend",BLEND),("glb",GLB),("manifest",MANIFEST),("preview",PREVIEW),("reference",REFERENCE)]:
        check(name+"_exists", path.exists(), {"path":str(path),"bytes":path.stat().st_size if path.exists() else 0})
    if not MANIFEST.exists():
        finish()
        return

    data = json.loads(MANIFEST.read_text(encoding="utf-8"))
    scene = bpy.context.scene
    check("house_identity", scene.get("house_id") == data.get("house_id") == "house_spacious_yunkuo_135_v4", {"scene":scene.get("house_id"),"manifest":data.get("house_id")})
    check(
        "geometry_revision",
        scene.get("geometry_revision")
        == data.get("geometry_revision")
        == "hard-finish-realism-pass-v5-wall-coverage",
        {"scene": scene.get("geometry_revision"), "manifest": data.get("geometry_revision")},
    )
    check("metric_units", scene.unit_settings.system == "METRIC" and math.isclose(scene.unit_settings.scale_length,1.0), {"system":scene.unit_settings.system,"scale":scene.unit_settings.scale_length})
    dims = data["dimension_calibration_m"]
    check("published_dimension_anchors", math.isclose(dims["public_frontage"],7.6) and math.isclose(dims["balcony_depth"],1.9) and math.isclose(dims["wall_height"],3.1), dims)
    area = data["area_basis"]
    check("published_area_anchors", area["published_building_area_m2"] == 135.0 and area["published_internal_area_m2"] == 96.53 and area["advertised_public_zone_m2"] == 39.0, area)
    check("open_public_zone", area["modeled_open_public_m2"] >= 39.0, {"modeled_open_public_m2":area["modeled_open_public_m2"]})
    check("panorama_balcony", len(data["balconies"]) == 1 and math.isclose(data["balconies"][0]["area_m2"],14.44,abs_tol=.01), data["balconies"])

    rooms = data["rooms"]
    room_ids = {room["id"] for room in rooms}
    check("three_bedrooms", len([r for r in rooms if r["type"]=="bedroom"]) == 3, [r["id"] for r in rooms if r["type"]=="bedroom"])
    check("two_bathrooms", len([r for r in rooms if r["type"]=="bathroom"]) == 2, [r["id"] for r in rooms if r["type"]=="bathroom"])
    south_bedrooms = [next(r for r in rooms if r["id"]=="bedroom_3"), next(r for r in rooms if r["id"]=="master_bedroom")]
    check("expanded_south_bedrooms", all(r["area_m2"]>=11.5 for r in south_bedrooms), [{"id":r["id"],"area_m2":r["area_m2"],"rect":r["rect"]} for r in south_bedrooms])
    check("complete_family_program", {"open_public","dining_room","kitchen","foyer","master_dressing"}.issubset(room_ids), sorted(room_ids))
    strategy = data["space_strategy"]
    check("realistic_living_strategy", strategy["formal_bedroom_walls_complete"] is True and strategy["convertible_room_program"] == "living_room" and strategy["open_study_integrated"] is False and strategy["kitchen_boundary"] == "full_height_glass_slider", strategy)

    opening_ids = {item["id"] for item in data["openings"]}
    required = {"opening_entry_door","opening_public_panorama_slider","opening_kitchen_glass_slider","opening_master_south_window","opening_bed2_north_window","opening_bed3_south_window"}
    check("key_openings", required.issubset(opening_ids), {"missing":sorted(required-opening_ids)})
    bedroom_faces = [face for face in data["wall_faces"] if face["host_wall_id"] in {"wall_bed3_east","wall_master_west","wall_master_split"}]
    check("bedroom_walls_visible_in_cutaway", bedroom_faces and not any(face["preview_hide"] for face in bedroom_faces) and {"opening_bed3_door","opening_master_suite_door","opening_master_dressing"}.issubset(opening_ids), {"faces":bedroom_faces,"doors":sorted({"opening_bed3_door","opening_master_suite_door","opening_master_dressing"} & opening_ids)})

    objects = list(bpy.data.objects)
    asset_data = json.loads(ASSET_MANIFEST.read_text(encoding="utf-8"))
    expected_asset_ids = {asset["id"] for asset in asset_data["assets"]}
    material_asset_ids = {
        material.get("asset_id")
        for material in bpy.data.materials
        if material.get("asset_id") in expected_asset_ids
    }
    geometry_preset_ids = {
        obj.get("preset_id")
        for obj in objects
        if obj.get("preset_id")
    }
    library = bpy.data.collections.get("V4_ASSET_LIBRARY")
    check(
        "v4_contains_complete_asset_library",
        len(expected_asset_ids) == asset_data.get("asset_count")
        and expected_asset_ids == material_asset_ids | geometry_preset_ids
        and library is not None,
        {
            "expected": len(expected_asset_ids),
            "materials": len(material_asset_ids),
            "geometry_presets": len(geometry_preset_ids),
            "library_collection": library is not None,
        },
    )
    pbr_surface_ids = {
        asset["id"]
        for asset in asset_data["assets"]
        if asset["category"] in {"wood_floor", "tile"}
    }
    pbr_surface_materials = [
        material
        for material in bpy.data.materials
        if material.get("asset_id") in pbr_surface_ids
    ]
    check(
        "v4_contains_all_surface_pbr_materials",
        len(pbr_surface_materials) == len(pbr_surface_ids)
        and all(
            material.node_tree
            and any(node.type == "NORMAL_MAP" for node in material.node_tree.nodes)
            and sum(node.type == "TEX_IMAGE" for node in material.node_tree.nodes) >= 3
            for material in pbr_surface_materials
        ),
        {"expected": len(pbr_surface_ids), "actual": len(pbr_surface_materials)},
    )
    check(
        "v4_contains_all_9_ceiling_geometry_presets",
        geometry_preset_ids == {
            "ceiling_flat_01",
            "ceiling_perimeter_step_01",
            "ceiling_perimeter_cove_01",
            "ceiling_floating_shadow_gap_01",
            "ceiling_kitchen_bath_panel_01",
            "ceiling_timber_slatted_01",
            "ceiling_shallow_coffer_grid_01",
            "ceiling_exposed_concrete_shadow_track_01",
            "ceiling_curved_cove_01",
        },
        sorted(geometry_preset_ids),
    )
    check("reference_layer_packed", any(o.name=="REFERENCE_YunKuo_135" and o.type=="EMPTY" for o in objects) and any(i.name==REFERENCE.name and i.packed_file for i in bpy.data.images), {"reference_object":any(o.name=="REFERENCE_YunKuo_135" for o in objects),"packed_images":[i.name for i in bpy.data.images if i.packed_file]})
    check("single_apartment_only", not any(o.get("context_only") for o in objects), {"context_objects":[o.name for o in objects if o.get("context_only")]})

    surface_ids = [o.get("surface_id") for o in objects if o.get("surface_id")]
    expected_surfaces = [surface for room in rooms for surface in room["surface_ids"].values()]
    check(
        "surface_ids",
        len(set(surface_ids)) == len(expected_surfaces)
        and set(surface_ids) == set(expected_surfaces),
        {"count": len(surface_ids), "unique": len(set(surface_ids)), "expected_unique": len(expected_surfaces)},
    )
    face_ids = [item["id"] for item in data["wall_faces"]]
    object_face_ids = {o.get("wall_face_id") for o in objects if o.get("wall_face_id")}
    check("wall_faces", len(face_ids)>=30 and len(face_ids)==len(set(face_ids)) and set(face_ids).issubset(object_face_ids), {"manifest":len(face_ids),"objects":len(object_face_ids)})
    wall_finish_objects = [o for o in objects if o.get("wall_face_id")]
    wall_core_objects = [o for o in objects if o.get("surface_role") == "wall_core"]
    check("batched_wall_meshes", len(wall_finish_objects) == len(face_ids) and len(wall_core_objects) <= len(data["wall_faces"]), {"wall_finishes":len(wall_finish_objects),"wall_faces":len(face_ids),"wall_cores":len(wall_core_objects)})
    wet_targets = [target for target in data["design_targets"] if target.get("surface_zone") == "wet_wall"]
    check("wet_wall_material_semantics", wet_targets and all(target.get("allowed_asset_categories") == ["tile"] and str(target.get("default_asset_id", "")).startswith("tile_") for target in wet_targets), {"count":len(wet_targets),"targets":wet_targets})
    metric_uvs_passed, metric_uvs_details = metric_floor_uvs(objects)
    check("metric_floor_uvs", metric_uvs_passed, metric_uvs_details)
    hard_finish_passed, hard_finish_details_data = hard_finish_details(objects, data)
    check("hard_finish_construction_details", hard_finish_passed, hard_finish_details_data)
    room_sides_passed, room_sides_details = room_facing_wall_sides(data["wall_faces"], rooms)
    check("wall_finishes_face_their_rooms", room_sides_passed, room_sides_details)
    exterior_coverage_passed, exterior_coverage_details = required_exterior_finish_coverage(data["wall_faces"])
    check("exterior_room_wall_finishes_complete", exterior_coverage_passed, exterior_coverage_details)
    source_geometry_passed, source_geometry_details = wall_finish_geometry(objects, data["wall_faces"])
    check("wall_finishes_outside_cores", source_geometry_passed, source_geometry_details)
    furniture = [o for o in objects if o.get("reference_only")]
    door_leaves = [o for o in objects if o.get("asset_role") == "door_leaf_reference"]
    check("open_reference_doors", len(door_leaves) == 7 and all(o.get("door_pose") == "open_reference" and abs(float(o.get("open_angle_deg", 0))) >= 75 for o in door_leaves), {"count":len(door_leaves),"doors":[{"name":o.name,"angle":o.get("open_angle_deg")} for o in door_leaves]})
    sofa = next((o for o in furniture if o.name=="SofaSeat"), None)
    tv_console = next((o for o in furniture if o.name=="TVConsole"), None)
    master_headboard = next((o for o in furniture if o.name=="MasterBed_headboard"), None)
    bed3_headboard = next((o for o in furniture if o.name=="Bedroom3Bed_headboard"), None)
    bed3_wardrobe = next((o for o in furniture if o.name=="Bedroom3Wardrobe"), None)
    check("real_scale_furniture", len(furniture)>=55 and sofa is not None and max(sofa.dimensions.x,sofa.dimensions.y)>=2.95, {"components":len(furniture),"sofa_dimensions":list(sofa.dimensions) if sofa else []})
    south_beds_against_wall = (
        master_headboard is not None
        and bed3_headboard is not None
        and math.isclose(master_headboard.location.y + master_headboard.dimensions.y / 2, 4.15, abs_tol=.02)
        and math.isclose(bed3_headboard.location.y + bed3_headboard.dimensions.y / 2, 4.40, abs_tol=.02)
    )
    bed3_clear_of_wardrobe = (
        bed3_headboard is not None
        and bed3_wardrobe is not None
        and bed3_headboard.location.x - bed3_headboard.dimensions.x / 2
            > bed3_wardrobe.location.x + bed3_wardrobe.dimensions.x / 2 + .30
    )
    check("south_beds_headboards_against_wall", south_beds_against_wall and bed3_clear_of_wardrobe, {
        "master_headboard_north_edge": master_headboard.location.y + master_headboard.dimensions.y / 2 if master_headboard else None,
        "bed3_headboard_north_edge": bed3_headboard.location.y + bed3_headboard.dimensions.y / 2 if bed3_headboard else None,
        "bed3_wardrobe_clearance": bed3_headboard.location.x - bed3_headboard.dimensions.x / 2 - bed3_wardrobe.location.x - bed3_wardrobe.dimensions.x / 2 if bed3_headboard and bed3_wardrobe else None,
    })
    check("living_room_only_and_rearranged", not any(o.name.startswith("OpenStudy") for o in objects) and sofa is not None and tv_console is not None and sofa.location.x < tv_console.location.x and tv_console.dimensions.y>=2.25, {"study_objects":[o.name for o in objects if o.name.startswith("OpenStudy")],"sofa_location":list(sofa.location) if sofa else [],"tv_location":list(tv_console.location) if tv_console else [],"tv_dimensions":list(tv_console.dimensions) if tv_console else []})
    check("positive_scales", not [o.name for o in objects if min(o.scale)<=0], {"bad":[o.name for o in objects if min(o.scale)<=0]})

    if PREVIEW.exists():
        image = bpy.data.images.load(str(PREVIEW), check_existing=True)
        check("preview_resolution", image.size[0]>=1400 and image.size[1]>=1000, {"size":list(image.size)})

    if GLB.exists():
        original_scene = bpy.context.window.scene
        temp = bpy.data.scenes.new("REAL_V4_GLB_VALIDATION")
        bpy.context.window.scene = temp
        bpy.ops.import_scene.gltf(filepath=str(GLB))
        imported = list(temp.objects)
        imported_surfaces = {o.get("surface_id") for o in imported if o.get("surface_id")}
        imported_faces = {o.get("wall_face_id") for o in imported if o.get("wall_face_id")}
        check("glb_extras_roundtrip", set(expected_surfaces).issubset(imported_surfaces) and set(face_ids).issubset(imported_faces), {"objects":len(imported),"surfaces":len(imported_surfaces),"faces":len(imported_faces)})
        check("glb_mesh_budget", len([o for o in imported if o.type == "MESH"]) <= 285, {"meshes":len([o for o in imported if o.type == "MESH"])})
        glb_geometry_passed, glb_geometry_details = wall_finish_geometry(imported, data["wall_faces"])
        check("glb_wall_finishes_outside_cores", glb_geometry_passed, glb_geometry_details)
        bpy.context.window.scene = original_scene

    finish()


if __name__ == "__main__":
    main()
