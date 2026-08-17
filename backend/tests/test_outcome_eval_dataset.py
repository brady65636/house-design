"""Offline integrity checks for the dimension-two scenario dataset."""

from __future__ import annotations

import json
from pathlib import Path
import unittest

from backend.agent_api.agent.visual_criteria import VISUAL_CRITERIA
from evals.outcome_dimension.run_eval import DEFAULT_DATASET, load_dataset


PROJECT_ROOT = Path(__file__).resolve().parents[2]
EVAL_ROOT = PROJECT_ROOT / "evals" / "outcome_dimension"


class OutcomeEvalDatasetTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.dataset = load_dataset(DEFAULT_DATASET)
        cls.schema = json.loads((EVAL_ROOT / "dataset_schema_v2.json").read_text(encoding="utf-8"))
        cls.seed_scheme = json.loads(
            (PROJECT_ROOT / "viewer" / "public" / "current_scheme.json").read_text(encoding="utf-8")
        )
        cls.camera_catalog = json.loads(
            (PROJECT_ROOT / "viewer" / "app" / "data" / "roomCameraTracksV4.json").read_text(encoding="utf-8")
        )

    def test_dataset_shape_and_subsets(self) -> None:
        scenarios = self.dataset["scenarios"]
        scenario_ids = [scenario["scenario_id"] for scenario in scenarios]
        self.assertEqual(self.dataset["dataset_version"], "outcome_dataset_v2")
        self.assertEqual(self.dataset["rubric_version"], "outcome_dimension_v1")
        self.assertEqual(
            self.dataset["entry_contract"]["mode"], "interactive_final_baseline"
        )
        self.assertEqual(self.schema["type"], "object")
        self.assertEqual(len(scenarios), 12)
        self.assertEqual(len(scenario_ids), len(set(scenario_ids)))
        self.assertEqual(len(self.dataset["subsets"]["smoke_6"]), 6)
        self.assertEqual(set(self.dataset["subsets"]["full_12"]), set(scenario_ids))
        self.assertLessEqual(set(self.dataset["subsets"]["smoke_6"]), set(scenario_ids))

    def test_interactive_scenarios_have_sparse_entry_and_grounded_requirements(self) -> None:
        for scenario in self.dataset["scenarios"]:
            self.assertIn(scenario["title"], scenario["initial_message"])
            self.assertNotIn(scenario["reference_plan"], scenario["initial_message"])
            requirement_ids = [
                item["requirement_id"] for item in scenario["requirement_facts"]
            ]
            self.assertEqual(len(requirement_ids), len(set(requirement_ids)))
            self.assertGreaterEqual(len(requirement_ids), 1)
            self.assertEqual(scenario["max_user_turns"], 10)

    def test_visual_criteria_are_valid_and_smoke_covers_all(self) -> None:
        valid_criteria = {criterion["criterion_id"] for criterion in VISUAL_CRITERIA}
        by_id = {scenario["scenario_id"]: scenario for scenario in self.dataset["scenarios"]}
        smoke_criteria: set[str] = set()

        for scenario in self.dataset["scenarios"]:
            required = set(scenario["required_visual_criteria"])
            covered = {
                criterion_id
                for capture in scenario["capture_plan"]
                for criterion_id in capture["covers_criteria"]
            }
            self.assertTrue(required)
            self.assertLessEqual(required, valid_criteria)
            self.assertEqual(covered, required, scenario["scenario_id"])

        for scenario_id in self.dataset["subsets"]["smoke_6"]:
            smoke_criteria.update(by_id[scenario_id]["required_visual_criteria"])
        self.assertEqual(smoke_criteria, valid_criteria)

    def test_rooms_and_targets_exist_in_current_scene(self) -> None:
        valid_targets = {
            assignment["target"]["id"] for assignment in self.seed_scheme["assignments"]
        }
        valid_rooms = {track["roomId"] for track in self.camera_catalog["tracks"]}

        for scenario in self.dataset["scenarios"]:
            allowed_targets = set(scenario["allowed_target_ids"])
            allowed_rooms = set(scenario["allowed_room_ids"])
            self.assertLessEqual(allowed_targets, valid_targets, scenario["scenario_id"])
            self.assertLessEqual(allowed_rooms, valid_rooms, scenario["scenario_id"])

            for capture in scenario["capture_plan"]:
                if capture["tool"] == "observe_room":
                    self.assertIn(capture.get("room_id"), allowed_rooms)
                    self.assertLessEqual(
                        set(capture.get("focus_target_ids", [])),
                        allowed_targets,
                        capture["capture_id"],
                    )
                else:
                    self.assertNotIn("room_id", capture)
                self.assertGreaterEqual(capture["minimum_image_count"], 1)


if __name__ == "__main__":
    unittest.main()
