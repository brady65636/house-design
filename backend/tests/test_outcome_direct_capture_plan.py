"""Regression tests for post-dialogue dimension-two evidence targeting."""

from __future__ import annotations

import json
import unittest

from evals.outcome_dimension.run_direct_dialogue_eval import (
    derive_dynamic_capture_plan,
    validate_capture_room_alignment,
)


def assignment(target_id: str, asset_id: str, parameters=None) -> dict:
    return {
        "target": {
            "kind": "wall_face" if target_id.startswith("wall_face") else "surface",
            "id": target_id,
        },
        "asset_id": asset_id,
        "parameters": parameters,
    }


def update_call(target_id: str, asset_id: str, parameters=None) -> dict:
    args = {"target_id": target_id, "asset_id": asset_id}
    if parameters is not None:
        args["parameters"] = parameters
    return {
        "name": "update_scheme",
        "args": args,
        "result": "修改scheme成功，新方案ID：version-final",
    }


def scenario(room_id: str = "bedroom_2") -> dict:
    return {
        "required_visual_criteria": ["intent_matches_image", "small_room_complexity"],
        "capture_plan": [
            {
                "capture_id": "legacy",
                "tool": "observe_room",
                "room_id": room_id,
                "focus_target_ids": [],
                "minimum_image_count": 3,
                "covers_criteria": ["intent_matches_image"],
            }
        ],
    }


class DirectCapturePlanTests(unittest.TestCase):
    def test_noop_writes_retarget_legacy_bedroom_capture(self) -> None:
        targets = [
            "wall_face_real4_001",
            "wall_face_real4_003",
            "surface_real4_floor_bedroom_3",
        ]
        final_assignments = [
            assignment(targets[0], "paint_warm_white_01"),
            assignment(targets[1], "paint_warm_white_01"),
            assignment(targets[2], "floor_light_oak_matte_01"),
        ]
        base = {"assignments": final_assignments}
        final = {"assignments": final_assignments}
        calls = [
            update_call(targets[0], "paint_warm_white_01"),
            update_call(targets[1], "paint_warm_white_01"),
            update_call(targets[2], "floor_light_oak_matte_01"),
        ]

        plan, provenance = derive_dynamic_capture_plan(
            scenario=scenario(),
            tool_calls=calls,
            base_scheme=base,
            final_scheme=final,
            final_version_id="version-final",
        )

        self.assertEqual([item["room_id"] for item in plan], ["bedroom_3"])
        self.assertEqual(set(plan[0]["focus_target_ids"]), set(targets))
        self.assertEqual(provenance["net_changed_target_ids"], [])
        self.assertEqual(provenance["derived_room_ids"], ["bedroom_3"])

    def test_net_scheme_changes_cover_every_affected_room_and_harmony(self) -> None:
        base = {
            "assignments": [
                assignment("wall_face_real4_005", "paint_greige_01"),
                assignment("surface_real4_floor_kitchen", "tile_light_microcement_01"),
            ]
        }
        final = {
            "assignments": [
                assignment("wall_face_real4_005", "paint_warm_white_01"),
                assignment("surface_real4_floor_kitchen", "tile_terrazzo_warm_grey_01"),
            ]
        }

        plan, provenance = derive_dynamic_capture_plan(
            scenario=scenario("dining_room"),
            tool_calls=[],
            base_scheme=base,
            final_scheme=final,
            final_version_id="version-final",
        )

        room_captures = [item for item in plan if item["tool"] == "observe_room"]
        self.assertEqual(
            [item["room_id"] for item in room_captures], ["dining_room", "kitchen"]
        )
        self.assertEqual(plan[-1]["tool"], "observe_home_harmony")
        self.assertEqual(provenance["derived_room_ids"], ["dining_room", "kitchen"])

    def test_final_version_observation_is_safe_fallback(self) -> None:
        result = {
            "status": "ready",
            "scheme": {"schemeId": "version-final"},
            "room": {"id": "bedroom_3"},
        }
        calls = [
            {
                "name": "observe_room",
                "args": {
                    "room_id": "bedroom_3",
                    "focus_target_ids": ["wall_face_real4_001"],
                },
                "result": json.dumps(result),
            }
        ]

        plan, provenance = derive_dynamic_capture_plan(
            scenario=scenario(),
            tool_calls=calls,
            base_scheme={"assignments": []},
            final_scheme={"assignments": []},
            final_version_id="version-final",
        )

        self.assertEqual(plan[0]["room_id"], "bedroom_3")
        self.assertEqual(plan[0]["focus_target_ids"], ["wall_face_real4_001"])
        self.assertEqual(provenance["source"], "final_version_ready_observations")

    def test_unresolved_scope_fails_closed_instead_of_using_legacy_plan(self) -> None:
        with self.assertRaisesRegex(RuntimeError, "cannot derive final capture rooms"):
            derive_dynamic_capture_plan(
                scenario=scenario(),
                tool_calls=[],
                base_scheme={"assignments": []},
                final_scheme={"assignments": []},
                final_version_id="version-final",
            )

    def test_returned_room_must_match_requested_room(self) -> None:
        capture_plan = [
            {
                "capture_id": "final_room_bedroom_3",
                "tool": "observe_room",
                "room_id": "bedroom_3",
            }
        ]
        evidence = [
            {
                "capture_id": "final_room_bedroom_3",
                "room_id": "bedroom_2",
            }
        ]
        with self.assertRaisesRegex(RuntimeError, "requested bedroom_3"):
            validate_capture_room_alignment(capture_plan, evidence)


if __name__ == "__main__":
    unittest.main()
