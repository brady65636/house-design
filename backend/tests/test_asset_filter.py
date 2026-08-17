"""Conservative Asset filter unit and regression tests."""

import json
import unittest
from pathlib import Path

from backend.agent_api.retrieval.asset_filter import (
    AssetFilterError,
    filter_assets,
    load_filter_profiles,
)


PROJECT_ROOT = Path(__file__).resolve().parents[2]


class AssetFilterTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.scene = json.loads((PROJECT_ROOT / "scene_manifest.json").read_text(encoding="utf-8"))
        cls.manifest = json.loads((PROJECT_ROOT / "asset_manifest.json").read_text(encoding="utf-8"))
        cls.cards = json.loads((PROJECT_ROOT / "asset_cards.json").read_text(encoding="utf-8"))
        cls.profiles = load_filter_profiles(PROJECT_ROOT / "asset_filter_profiles.json")

    def run_filter(self, **overrides):
        query = {
            "target_id": "wall_face_real4_010",
            "category": "wall_paint",
            "role": "quiet",
            "anchor_asset_id": None,
            "color_intent": "open",
        }
        query.update(overrides)
        return filter_assets(
            scene_manifest=self.scene,
            asset_manifest=self.manifest,
            asset_cards=self.cards,
            profile_data=self.profiles,
            **query,
        )

    def test_all_five_categories_reduce_candidates_by_at_least_70_percent(self) -> None:
        cases = [
            ("wall_face_real4_010", "wall_paint", "quiet", None),
            ("wall_face_real4_010", "wallpaper", "anchor", None),
            ("surface_real4_floor_open_public", "wood_floor", "support", "wallpaper_midcentury_blocks_01"),
            ("wall_face_real4_006", "tile", "quiet", "tile_green_breccia_01"),
            ("surface_real4_ceiling_open_public", "ceiling", "support", "wallpaper_midcentury_blocks_01"),
        ]
        for target_id, category, role, anchor in cases:
            with self.subTest(category=category):
                result = self.run_filter(
                    target_id=target_id,
                    category=category,
                    role=role,
                    anchor_asset_id=anchor,
                )
                self.assertTrue(result["metrics"]["target_met"])
                self.assertGreaterEqual(result["metrics"]["reduction_rate"], 0.70)
                self.assertGreaterEqual(len(result["eligible"]), 2)

    def test_every_active_target_category_and_role_meets_reduction_contract(self) -> None:
        anchors = {"anchor": None, "support": "wallpaper_midcentury_blocks_01", "quiet": "wallpaper_midcentury_blocks_01"}
        for target in self.scene["design_targets"]:
            for category in target["allowed_asset_categories"]:
                for role, anchor in anchors.items():
                    with self.subTest(target=target["id"], category=category, role=role):
                        result = self.run_filter(
                            target_id=target["id"],
                            category=category,
                            role=role,
                            anchor_asset_id=anchor,
                        )
                        metrics = result["metrics"]
                        self.assertTrue(metrics["target_met"])
                        self.assertGreaterEqual(metrics["reduction_rate"], 0.70)
                        partition = (
                            len(result["eligible"])
                            + len(result["rejected"])
                            + len(result["deferred"])
                        )
                        self.assertEqual(partition, metrics["input_count"])

    def test_high_activity_anchor_vetoes_high_activity_support(self) -> None:
        result = self.run_filter(
            target_id="surface_real4_floor_open_public",
            category="wood_floor",
            role="support",
            anchor_asset_id="wallpaper_midcentury_blocks_01",
        )
        rejected = {item["asset_id"]: item["reasons"] for item in result["rejected"]}
        self.assertIn("DUAL_HIGH_ACTIVITY", rejected["floor_character_oak_wideplank_matte_01"])
        self.assertIn("DUAL_HIGH_ACTIVITY", rejected["floor_greywashed_variation_matte_01"])
        self.assertNotIn("floor_ash_maple_light_matte_01", rejected)
        self.assertNotIn("floor_bleached_ash_wideplank_matte_01", rejected)

    def test_quiet_role_vetoes_high_activity_tile(self) -> None:
        result = self.run_filter(
            target_id="wall_face_real4_006",
            category="tile",
            role="quiet",
            anchor_asset_id="tile_green_breccia_01",
        )
        rejected = {item["asset_id"]: item["reasons"] for item in result["rejected"]}
        self.assertIn("HIGH_ACTIVITY_FOR_QUIET_ROLE", rejected["tile_checker_black_ivory_01"])
        self.assertIn("HIGH_ACTIVITY_FOR_QUIET_ROLE", rejected["tile_ivory_fluted_relief_01"])
        self.assertNotIn("tile_deep_matte_monochrome_01", rejected)

    def test_quiet_role_vetoes_visually_active_mineral_wash(self) -> None:
        result = self.run_filter(
            target_id="wall_face_real4_013",
            category="wallpaper",
            role="quiet",
        )
        rejected = {item["asset_id"]: item["reasons"] for item in result["rejected"]}
        self.assertIn("HIGH_ACTIVITY_FOR_QUIET_ROLE", rejected["wallpaper_mineral_wash_01"])

    def test_continuous_mural_is_vetoed_on_fragmented_wall(self) -> None:
        result = self.run_filter(
            target_id="wall_face_real4_002",
            category="wallpaper",
            role="anchor",
        )
        self.assertTrue(result["query"]["target_is_fragmented"])
        rejected = {item["asset_id"]: item["reasons"] for item in result["rejected"]}
        self.assertIn("CONTINUOUS_PATTERN_ON_FRAGMENTED_TARGET", rejected["wallpaper_mist_landscape_mural_01"])
        self.assertIn("CONTINUOUS_PATTERN_ON_FRAGMENTED_TARGET", rejected["wallpaper_oxide_colourfield_mural_01"])

    def test_budget_deferred_is_distinct_from_hard_rejection(self) -> None:
        result = self.run_filter()
        self.assertEqual(result["rejected"], [])
        self.assertTrue(result["deferred"])
        self.assertTrue(all(item["reasons"] == ["DIVERSITY_BUDGET"] for item in result["deferred"]))

    def test_room_moisture_rule_can_remove_all_wood_floors(self) -> None:
        result = self.run_filter(
            target_id="surface_real4_floor_guest_bath",
            category="wood_floor",
            role="quiet",
        )
        self.assertEqual(result["eligible"], [])
        self.assertEqual(result["metrics"]["vetoed_count"], 13)
        self.assertTrue(
            all("ROOM_MOISTURE_INCOMPATIBLE" in item["reasons"] for item in result["rejected"])
        )

    def test_invalid_target_category_pair_fails_explicitly(self) -> None:
        with self.assertRaises(AssetFilterError):
            self.run_filter(
                target_id="surface_real4_ceiling_open_public",
                category="wallpaper",
            )

    def test_agent_tool_is_registered_and_returns_structured_metrics(self) -> None:
        from backend.agent_api.tools.tools import execute_tool, tools

        names = [item["function"]["name"] for item in tools]
        self.assertIn("filter_assets", names)
        self.assertNotIn("get_asset_by_category", names)
        result = json.loads(
            execute_tool(
                "filter_assets",
                {
                    "target_id": "surface_real4_floor_open_public",
                    "category": "wood_floor",
                    "role": "support",
                    "anchor_asset_id": "wallpaper_midcentury_blocks_01",
                    "color_intent": "open",
                },
            )
        )
        self.assertTrue(result["metrics"]["target_met"])
        self.assertIn("eligible", result)
        self.assertIn("rejected", result)
        self.assertIn("deferred", result)

    def test_agent_tool_reports_invalid_query_without_throwing(self) -> None:
        from backend.agent_api.tools.tools import execute_tool

        result = json.loads(
            execute_tool(
                "filter_assets",
                {
                    "target_id": "surface_real4_ceiling_open_public",
                    "category": "wallpaper",
                    "role": "quiet",
                },
            )
        )
        self.assertEqual(result["error"], "INVALID_FILTER_QUERY")


if __name__ == "__main__":
    unittest.main()
