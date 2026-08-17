"""Offline checks for pixel-verified outcome evidence gates."""

from __future__ import annotations

from pathlib import Path
from tempfile import TemporaryDirectory
import unittest

from evals.outcome_dimension.run_eval import (
    collect_render_evidence,
    deterministic_gate_overrides,
    save_render_result,
)


IMAGE = "data:image/jpeg;base64,/9j/2Q=="


def room_result(status: str) -> dict:
    return {
        "status": status,
        "scheme": {"schemeId": "version-1"},
        "room": {"id": "kitchen"},
        "views": [
            {
                "viewId": "view-1",
                "label": "厨房证据",
                "imageDataUrl": IMAGE,
                "quality": {"valid": True},
                "targetVisibility": [{"targetId": "floor", "readable": True}],
                "maskQuality": {"occluderPixelRatio": 0.1},
            }
        ],
    }


class _Bridge:
    def __init__(self, result: dict) -> None:
        self.result = result

    def capture(self, _tool: str, _args: dict) -> dict:
        return self.result


class OutcomeRenderEvidenceTests(unittest.TestCase):
    def test_incomplete_observation_is_saved_but_never_counted_as_valid(self) -> None:
        with TemporaryDirectory() as temporary:
            evidence = save_render_result(
                result=room_result("incomplete_observation"),
                capture={"capture_id": "capture-1", "tool": "observe_room", "room_id": "kitchen"},
                case_dir=Path(temporary),
                design_run_id="run-1",
                fallback_version_id="unused",
            )
        self.assertEqual(len(evidence), 1)
        self.assertFalse(evidence[0]["evidence_valid"])
        self.assertEqual(evidence[0]["observation_status"], "incomplete_observation")
        self.assertEqual(evidence[0]["mask_quality"]["occluderPixelRatio"], 0.1)

    def test_capture_record_and_gate_use_only_valid_evidence(self) -> None:
        scenario = {
            "capture_plan": [
                {
                    "capture_id": "capture-1",
                    "tool": "observe_room",
                    "room_id": "kitchen",
                    "minimum_image_count": 1,
                }
            ]
        }
        with TemporaryDirectory() as temporary:
            evidence, records = collect_render_evidence(
                bridge=_Bridge(room_result("incomplete_observation")),
                scenario=scenario,
                design_run_id="run-1",
                final_version_id="version-1",
                case_dir=Path(temporary),
            )
        self.assertEqual(records[0]["status"], "incomplete_observation")
        self.assertEqual(records[0]["image_count"], 0)
        gates = deterministic_gate_overrides(
            {
                "final_state": {"design_run_id": "run-1", "scheme_version_id": "version-1"},
                "render_evidence": evidence,
                "scheme_diff": [],
                "allowed_target_ids": [],
                "capture_plan": scenario["capture_plan"],
            }
        )
        self.assertEqual(gates["visual_claim_has_evidence"]["verdict"], "FAIL")
        self.assertEqual(gates["scheme_render_version_alignment"]["verdict"], "FAIL")


if __name__ == "__main__":
    unittest.main()
