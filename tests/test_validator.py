import json
import unittest
from pathlib import Path

from schema import Scheme
from validator import validate_scheme


PROJECT_ROOT = Path(__file__).resolve().parents[1]


class SchemeValidatorTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.scene_manifest = json.loads(
            (PROJECT_ROOT / "scene_manifest.json").read_text(
                encoding="utf-8"
            )
        )
        cls.asset_manifest = json.loads(
            (PROJECT_ROOT / "asset_manifest.json").read_text(
                encoding="utf-8"
            )
        )

    def make_scheme(self, assignments: list[dict[str, object]]) -> Scheme:
        return Scheme.model_validate(
            {
                "schema_version": "1.0.0",
                "scheme_id": "scheme_validator_test",
                "title": "Validator test",
                "assignments": assignments,
            }
        )

    def validate(self, assignments: list[dict[str, object]]) -> list[str]:
        return validate_scheme(
            self.make_scheme(assignments),
            self.scene_manifest,
            self.asset_manifest,
        )

    def test_accepts_valid_wall_floor_and_ceiling_assignments(self) -> None:
        errors = self.validate(
            [
                {
                    "target": {"kind": "wall_face", "id": "wall_face_real4_010"},
                    "asset_id": "wallpaper_linen_natural_01",
                },
                {
                    "target": {
                        "kind": "surface",
                        "id": "surface_real4_floor_open_public",
                    },
                    "asset_id": "floor_light_oak_matte_01",
                },
                {
                    "target": {
                        "kind": "surface",
                        "id": "surface_real4_ceiling_open_public",
                    },
                    "asset_id": "ceiling_perimeter_step_01",
                },
            ]
        )

        self.assertEqual(errors, [])

    def test_rejects_unknown_target(self) -> None:
        errors = self.validate(
            [
                {
                    "target": {"kind": "wall_face", "id": "wall_face_999"},
                    "asset_id": "wallpaper_linen_natural_01",
                }
            ]
        )

        self.assertTrue(any("目标不存在" in error for error in errors))

    def test_rejects_unknown_asset(self) -> None:
        errors = self.validate(
            [
                {
                    "target": {"kind": "wall_face", "id": "wall_face_real4_010"},
                    "asset_id": "fake_asset_001",
                }
            ]
        )

        self.assertTrue(any("资产不存在" in error for error in errors))

    def test_rejects_incompatible_asset_categories(self) -> None:
        cases = [
            (
                {"kind": "wall_face", "id": "wall_face_real4_010"},
                "floor_light_oak_matte_01",
            ),
            (
                {"kind": "surface", "id": "surface_real4_floor_open_public"},
                "ceiling_perimeter_step_01",
            ),
            (
                {"kind": "surface", "id": "surface_real4_ceiling_open_public"},
                "paint_warm_cream_matte_01",
            ),
        ]

        for target, asset_id in cases:
            with self.subTest(target=target, asset_id=asset_id):
                errors = self.validate(
                    [{"target": target, "asset_id": asset_id}]
                )
                self.assertTrue(
                    any("资产类别不兼容" in error for error in errors)
                )

    def test_wet_wall_accepts_tile_and_rejects_wallpaper(self) -> None:
        wet_target = next(
            target
            for target in self.scene_manifest["design_targets"]
            if target.get("surface_zone") == "wet_wall"
        )
        valid_errors = self.validate(
            [{"target": {"kind": wet_target["kind"], "id": wet_target["id"]}, "asset_id": "tile_light_microcement_01"}]
        )
        invalid_errors = self.validate(
            [{"target": {"kind": wet_target["kind"], "id": wet_target["id"]}, "asset_id": "wallpaper_linen_natural_01"}]
        )

        self.assertEqual(valid_errors, [])
        self.assertTrue(any("资产类别不兼容" in error for error in invalid_errors))

    def test_current_scheme_covers_every_v4_design_target(self) -> None:
        current_scheme = Scheme.model_validate_json(
            (PROJECT_ROOT / "viewer" / "public" / "current_scheme.json").read_text(
                encoding="utf-8"
            )
        )
        errors = validate_scheme(
            current_scheme,
            self.scene_manifest,
            self.asset_manifest,
        )
        expected_targets = {
            (target["kind"], target["id"])
            for target in self.scene_manifest["design_targets"]
        }
        actual_targets = {
            (assignment.target.kind, assignment.target.id)
            for assignment in current_scheme.assignments
        }

        self.assertEqual(errors, [])
        self.assertEqual(actual_targets, expected_targets)
        self.assertEqual(len(actual_targets), 55)


if __name__ == "__main__":
    unittest.main()
