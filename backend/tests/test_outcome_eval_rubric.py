"""Offline checks for the shared Critic and outcome-evaluation rubric."""

from __future__ import annotations

import json
from pathlib import Path
import unittest

from backend.agent_api.agent.critic import CRITIC_SYSTEM_PROMPT
from backend.agent_api.agent.visual_criteria import VISUAL_CRITERIA
from evals.outcome_dimension.rubric import CONSISTENCY_GATES, finalize_outcome_grade


PROJECT_ROOT = Path(__file__).resolve().parents[2]
EVAL_ROOT = PROJECT_ROOT / "evals" / "outcome_dimension"


class OutcomeEvalRubricTests(unittest.TestCase):
    def test_snapshot_matches_shared_visual_and_consistency_sources(self) -> None:
        snapshot = json.loads((EVAL_ROOT / "rubric_v1.json").read_text(encoding="utf-8"))
        self.assertEqual(snapshot["visual_criteria"], list(VISUAL_CRITERIA))
        self.assertEqual(snapshot["consistency_gates"], list(CONSISTENCY_GATES))
        self.assertEqual(len(snapshot["visual_criteria"]), 12)

    def test_production_critic_contains_every_shared_criterion(self) -> None:
        for index, criterion in enumerate(VISUAL_CRITERIA, start=1):
            self.assertIn(f"{index}. {criterion['text']}", CRITIC_SYSTEM_PROMPT)

    def test_evidence_and_output_schemas_are_valid_json_objects(self) -> None:
        for name in ("evidence_packet_schema_v1.json", "grader_output_schema_v1.json"):
            schema = json.loads((EVAL_ROOT / name).read_text(encoding="utf-8"))
            self.assertEqual(schema["type"], "object")
            self.assertFalse(schema["additionalProperties"])

    def test_all_required_visual_and_consistency_items_must_pass(self) -> None:
        required = ["intent_matches_image", "wall_floor_color_relation"]
        packet = {"required_visual_criteria": required}
        judgment = {
            "visual_results": [
                {
                    "criterion_id": criterion_id,
                    "verdict": "PASS",
                    "reason": "最终版本图片支持通过。",
                    "evidence_ids": ["view-1"],
                }
                for criterion_id in required
            ],
            "consistency_gates": {
                gate["gate_id"]: {
                    "verdict": "PASS",
                    "reason": "证据一致。",
                    "evidence_refs": ["trace-1"],
                }
                for gate in CONSISTENCY_GATES
            },
            "prioritized_findings": [],
            "unverified_items": [],
            "summary": "通过",
        }
        result = finalize_outcome_grade(packet, judgment)
        self.assertTrue(result["overall_pass"])

        judgment["visual_results"][0]["verdict"] = "UNABLE_TO_JUDGE"
        result = finalize_outcome_grade(packet, judgment)
        self.assertFalse(result["required_visual_pass"])
        self.assertFalse(result["overall_pass"])

        judgment["visual_results"][0]["verdict"] = "PASS"
        judgment["consistency_gates"]["scope_integrity"]["verdict"] = "FAIL"
        result = finalize_outcome_grade(packet, judgment)
        self.assertFalse(result["consistency_pass"])
        self.assertFalse(result["overall_pass"])


if __name__ == "__main__":
    unittest.main()
