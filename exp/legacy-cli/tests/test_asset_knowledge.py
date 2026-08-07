import json
import unittest
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[1]


class AssetKnowledgeTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.index = json.loads(
            (PROJECT_ROOT / "asset_manifest.json").read_text(encoding="utf-8")
        )
        cls.cards = json.loads(
            (PROJECT_ROOT / "asset_cards.json").read_text(encoding="utf-8")
        )

    def test_index_is_compact_and_complete(self) -> None:
        self.assertEqual(self.index["schema_version"], "2.0.0")
        self.assertEqual(self.index["asset_count"], 87)
        self.assertEqual(len(self.index["assets"]), 87)
        self.assertTrue(
            all(
                set(asset) == {"id", "category", "brief"}
                for asset in self.index["assets"]
            )
        )

    def test_every_index_asset_has_one_detailed_card(self) -> None:
        self.assertEqual(self.cards["card_count"], 87)
        index_ids = {asset["id"] for asset in self.index["assets"]}
        self.assertEqual(index_ids, set(self.cards["cards"]))
        for asset_id in index_ids:
            card = self.cards["cards"][asset_id]
            self.assertEqual(card["id"], asset_id)
            self.assertIn("objective_facts", card)
            self.assertIn("visual_description", card)
            self.assertIn("spatial_effect", card)
            self.assertIn("works_well_with", card)
            self.assertIn("avoid_when", card)

    def test_active_viewer_receives_the_same_compact_index(self) -> None:
        viewer_index = json.loads(
            (
                PROJECT_ROOT
                / "viewer"
                / "public"
                / "models"
                / "asset_manifest.json"
            ).read_text(encoding="utf-8")
        )
        self.assertEqual(viewer_index, self.index)


if __name__ == "__main__":
    unittest.main()
