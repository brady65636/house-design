"""Render observations fail closed before either Agent receives image blocks."""

import json
import unittest

from backend.agent_api.tools.visual_evidence import compact_render_evidence


def _view(view_id: str, *, valid: bool = True) -> dict:
    return {
        "viewId": view_id,
        "label": view_id,
        "imageDataUrl": f"data:image/jpeg;base64,{view_id}",
        "quality": {"valid": valid, "reasons": [] if valid else ["too_dark"]},
        "targetVisibility": [],
        "maskQuality": {"occluderPixelRatio": 0.1, "backgroundPixelRatio": 0.0},
    }


def _room_payload(*views: dict, status: str = "ready") -> dict:
    return {
        "tool": "observe_room",
        "status": status,
        "evidenceLevel": "pixel_verified_coverage",
        "room": {"id": "living_room", "label": "客厅"},
        "views": list(views),
        "plannedCoverage": {"wall-1": [view["viewId"] for view in views]},
        "verifiedCoverage": {"wall-1": [view["viewId"] for view in views if view["quality"]["valid"]]},
        "uncoveredTargetIds": [],
        "invalidViewIds": [view["viewId"] for view in views if not view["quality"]["valid"]],
    }


def _hero(room_id: str = "living_room") -> dict:
    return {
        "roomId": room_id,
        "selectedViewId": "hero",
        "score": 1234,
        "quality": {"valid": True},
        "targetVisibility": [],
        "maskQuality": {"occluderPixelRatio": 0.1, "backgroundPixelRatio": 0.0},
    }


class VisualToolEvidenceTests(unittest.TestCase):
    def test_incomplete_room_keeps_diagnostics_but_blocks_all_images(self) -> None:
        payload = _room_payload(_view("overview"), status="incomplete_observation")
        payload["room"] = {"id": "kitchen", "label": "厨房"}
        payload["uncoveredTargetIds"] = ["wall-1"]

        summary, images = compact_render_evidence("observe_room", payload)

        self.assertEqual(images, [])
        self.assertFalse(summary["modelEvidenceReady"])
        self.assertEqual(summary["modelEvidenceImageCount"], 0)
        self.assertIn("未作为模型视觉证据回注", summary["modelEvidenceBlockReason"])
        self.assertNotIn("imageDataUrl", summary["views"][0])
        self.assertIn("imageDataUrl", payload["views"][0], "compaction must not mutate bridge payload")

    def test_ready_room_injects_all_contract_valid_images(self) -> None:
        payload = _room_payload(_view("overview"), _view("wall"))

        summary, images = compact_render_evidence("observe_room", payload)

        self.assertTrue(summary["modelEvidenceReady"])
        self.assertEqual(summary["modelEvidenceImageCount"], 2)
        self.assertEqual([label for label, _ in images], ["客厅 · overview", "客厅 · wall"])
        self.assertTrue(all("imageDataUrl" not in view for view in summary["views"]))

    def test_stale_ready_room_with_one_invalid_view_fails_closed(self) -> None:
        payload = _room_payload(_view("valid"), _view("invalid", valid=False))

        summary, images = compact_render_evidence("observe_room", payload)

        self.assertFalse(summary["modelEvidenceReady"])
        self.assertEqual(images, [])

    def test_incomplete_home_blocks_contact_sheet_and_transition_images(self) -> None:
        payload = {
            "tool": "observe_home_harmony",
            "status": "incomplete_observation",
            "evidenceLevel": "pixel_verified_coverage",
            "roomContactSheet": "data:image/jpeg;base64,sheet",
            "transitionPairs": [{
                "id": "kitchen-open-public",
                "status": "ready",
                "from": _view("from"),
                "to": _view("to"),
            }],
            "invalidHeroRoomIds": ["kitchen"],
            "incompleteRooms": [{"roomId": "kitchen"}],
            "roomHeroDiagnostics": [_hero("kitchen")],
        }

        summary, images = compact_render_evidence("observe_home_harmony", payload)

        self.assertEqual(images, [])
        self.assertFalse(summary["modelEvidenceReady"])
        self.assertNotIn("roomContactSheet", summary)
        self.assertNotIn("imageDataUrl", summary["transitionPairs"][0]["from"])
        self.assertNotIn("imageDataUrl", summary["transitionPairs"][0]["to"])

    def test_stale_ready_home_with_invalid_side_fails_closed(self) -> None:
        payload = {
            "tool": "observe_home_harmony",
            "status": "ready",
            "evidenceLevel": "pixel_verified_coverage",
            "roomContactSheet": "data:image/jpeg;base64,sheet",
            "transitionPairs": [
                {
                    "id": "ready-pair",
                    "status": "ready",
                    "from": _view("from"),
                    "to": _view("to", valid=False),
                },
            ],
            "incompleteRooms": [],
            "invalidHeroRoomIds": [],
            "roomHeroDiagnostics": [_hero()],
        }

        summary, images = compact_render_evidence("observe_home_harmony", payload)

        self.assertFalse(summary["modelEvidenceReady"])
        self.assertEqual(images, [])

    def test_ready_home_injects_contact_sheet_and_both_transition_sides(self) -> None:
        payload = {
            "tool": "observe_home_harmony",
            "status": "ready",
            "evidenceLevel": "pixel_verified_coverage",
            "roomContactSheet": "data:image/jpeg;base64,sheet",
            "transitionPairs": [{
                "id": "ready-pair",
                "status": "ready",
                "from": _view("from"),
                "to": _view("to"),
            }],
            "incompleteRooms": [],
            "invalidHeroRoomIds": [],
            "roomHeroDiagnostics": [_hero()],
        }

        summary, images = compact_render_evidence("observe_home_harmony", payload)

        self.assertTrue(summary["modelEvidenceReady"])
        self.assertEqual(summary["modelEvidenceImageCount"], 3)
        self.assertEqual(
            [label for label, _ in images],
            ["全屋代表视图总览", "过渡 ready-pair · from", "过渡 ready-pair · to"],
        )
        self.assertNotIn("modelEvidenceBlockReason", summary)

    def test_summary_is_json_serializable_after_compaction(self) -> None:
        payload = _room_payload(_view("hero"))
        payload["room"] = {"label": "卧室"}
        summary, _ = compact_render_evidence("observe_room", payload)
        self.assertEqual(json.loads(json.dumps(summary, ensure_ascii=False))["status"], "ready")


if __name__ == "__main__":
    unittest.main()
