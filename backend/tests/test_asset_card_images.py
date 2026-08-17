"""Asset cards are multimodal references, not text-only retrieval records."""

import base64
import importlib.util
import json
import unittest
from pathlib import Path

from backend.agent_api.tools.tools import VisualToolOutput, get_asset_card_by_id


PROJECT_ROOT = Path(__file__).resolve().parents[2]


class AssetCardImageTests(unittest.TestCase):
    def test_every_asset_card_has_one_lightweight_webp_preview(self) -> None:
        library = json.loads((PROJECT_ROOT / "asset_cards.json").read_text(encoding="utf-8"))
        cards = library["cards"]
        self.assertEqual(library["schema_version"], "1.2.0")
        self.assertEqual(len(cards), library["card_count"])
        self.assertEqual(len(cards), 72)
        preview_paths = []
        for asset_id, card in cards.items():
            preview = card["preview_image"]
            image_path = PROJECT_ROOT / preview["path"]
            self.assertEqual(preview["media_type"], "image/webp")
            self.assertTrue(preview["alt"])
            self.assertTrue(image_path.is_file(), asset_id)
            payload = image_path.read_bytes()
            self.assertLessEqual(len(payload), 4 * 1024 * 1024)
            self.assertEqual(payload[:4], b"RIFF")
            self.assertEqual(payload[8:12], b"WEBP")
            preview_paths.append(preview["path"])
        self.assertEqual(len(preview_paths), len(set(preview_paths)))

    def test_asset_card_tool_returns_json_and_image_in_one_result(self) -> None:
        result = get_asset_card_by_id("paint_greige_01")
        self.assertIsInstance(result, VisualToolOutput)
        self.assertEqual(result.kind, "asset_reference")
        self.assertEqual(json.loads(result.summary)["id"], "paint_greige_01")
        self.assertEqual(len(result.images), 1)
        image_url = result.images[0][1]
        prefix, encoded = image_url.split(",", 1)
        self.assertEqual(prefix, "data:image/webp;base64")
        self.assertEqual(base64.b64decode(encoded)[:4], b"RIFF")

    @unittest.skipUnless(
        importlib.util.find_spec("langchain_core") and importlib.util.find_spec("langgraph"),
        "requires optional LangChain/LangGraph runtime",
    )
    def test_asset_reference_image_is_returned_to_the_agent_loop(self) -> None:
        from langchain_core.messages import AIMessage, HumanMessage
        from backend.agent_api.agent.graph import tools_node

        state = {
            "messages": [AIMessage(content="", tool_calls=[{
                "name": "get_asset_card_by_id",
                "args": {"asset_id": "paint_greige_01"},
                "id": "asset-card-1",
                "type": "tool_call",
            }])]
        }
        result = tools_node(state)
        self.assertNotIn("render_receipts", result)
        self.assertIsInstance(result["messages"][-1], HumanMessage)
        image_blocks = [block for block in result["messages"][-1].content if block.get("type") == "image_url"]
        self.assertEqual(len(image_blocks), 1)

    @unittest.skipUnless(
        importlib.util.find_spec("langchain_core") and importlib.util.find_spec("langgraph"),
        "requires optional LangChain/LangGraph runtime",
    )
    def test_blocked_render_observation_is_not_returned_as_visual_message(self) -> None:
        from unittest.mock import patch

        from langchain_core.messages import AIMessage, HumanMessage
        from backend.agent_api.agent.graph import tools_node

        state = {
            "messages": [AIMessage(content="", tool_calls=[{
                "name": "observe_room",
                "args": {"room_id": "kitchen"},
                "id": "blocked-observation",
                "type": "tool_call",
            }])]
        }
        blocked = VisualToolOutput(
            summary='{"status":"incomplete_observation","modelEvidenceReady":false}',
            images=[],
        )
        with patch("backend.agent_api.agent.graph.execute_tool", return_value=blocked):
            result = tools_node(state)

        self.assertFalse(any(isinstance(message, HumanMessage) for message in result["messages"]))


if __name__ == "__main__":
    unittest.main()
