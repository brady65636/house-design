import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

import agent_tools
from schema import Scheme


PROJECT_ROOT = Path(__file__).resolve().parents[1]


class AgentToolTests(unittest.TestCase):
    def test_runtime_prompt_and_room_tool_use_active_manifest(self) -> None:
        self.assertIn("house_spacious_yunkuo_135_v4", agent_tools.SYSTEM_PROMPT)
        self.assertNotIn("house_2b2l_90_v1", agent_tools.SYSTEM_PROMPT)
        self.assertIn("固定注入的住宅审美设计 Skill", agent_tools.SYSTEM_PROMPT)
        self.assertIn("人类批准闸门", agent_tools.SYSTEM_PROMPT)

        room = json.loads(agent_tools.get_room_by_id("open_public"))
        self.assertEqual(room["name_zh"], "完整横厅客厅")
        self.assertEqual(len(room["wall_face_ids"]), 6)
        self.assertEqual(
            room["surface_ids"]["floor"],
            "surface_real4_floor_open_public",
        )

    def test_update_scheme_changes_only_one_canonical_target(self) -> None:
        from backend.agent_api.scheme.store import SchemeStore

        source_scheme = PROJECT_ROOT / "viewer" / "public" / "current_scheme.json"
        with tempfile.TemporaryDirectory() as temp_dir:
            temp_scheme_path = Path(temp_dir) / "current_scheme.json"
            temp_scheme_path.write_text(
                source_scheme.read_text(encoding="utf-8"),
                encoding="utf-8",
            )

            store = SchemeStore(
                temp_scheme_path,
                json.loads(
                    (PROJECT_ROOT / "scene_manifest.json").read_text(encoding="utf-8")
                ),
                json.loads(
                    (PROJECT_ROOT / "asset_manifest.json").read_text(encoding="utf-8")
                ),
            )
            # 模拟 run_cli 启动：把当前 Scheme 读入内存
            store.load()
            original_store = agent_tools.set_scheme_store(store)
            try:
                before = Scheme.model_validate_json(
                    temp_scheme_path.read_text(encoding="utf-8")
                )
                before_assets = {
                    assignment.target.id: assignment.asset_id
                    for assignment in before.assignments
                }

                result = agent_tools.update_scheme(
                    "wall_face_real4_010",
                    "paint_light_greige_eggshell_01",
                )
                self.assertIn("修改scheme成功", result)

                after = Scheme.model_validate_json(
                    temp_scheme_path.read_text(encoding="utf-8")
                )
                after_assets = {
                    assignment.target.id: assignment.asset_id
                    for assignment in after.assignments
                }
                changed_targets = {
                    target_id
                    for target_id, asset_id in before_assets.items()
                    if after_assets[target_id] != asset_id
                }
                self.assertEqual(changed_targets, {"wall_face_real4_010"})

                # 验证 SchemeStore 内存中的当前方案也已更新
                mem_scheme = Scheme.model_validate(store.get())
                mem_assets = {
                    a.target.id: a.asset_id for a in mem_scheme.assignments
                }
                self.assertEqual(
                    mem_assets["wall_face_real4_010"],
                    "paint_light_greige_eggshell_01",
                )
            finally:
                agent_tools.set_scheme_store(original_store)

    def test_asset_category_lookup_returns_every_compact_brief(self) -> None:
        result = json.loads(agent_tools.get_asset_by_category("wall_paint"))
        self.assertEqual(len(result), 60)
        self.assertEqual(
            set(result[0]),
            {"id", "category", "brief"},
        )
        self.assertTrue(all(asset["category"] == "wall_paint" for asset in result))

    def test_asset_card_lookup_returns_one_detailed_card(self) -> None:
        card = json.loads(
            agent_tools.get_asset_card_by_id("floor_light_oak_matte_01")
        )
        self.assertEqual(card["id"], "floor_light_oak_matte_01")
        self.assertEqual(card["category"], "wood_floor")
        self.assertIn("objective_facts", card)
        self.assertIn("visual_description", card)
        self.assertIn("avoid_when", card)

    def test_asset_category_tool_rejects_legacy_limit_argument(self) -> None:
        error = agent_tools.tool_execute(
            type(
                "ToolCall",
                (),
                {
                    "function": type(
                        "Function",
                        (),
                        {
                            "name": "get_asset_by_category",
                            "arguments": '{"category": "tile", "limit": 5}',
                        },
                    )()
                },
            )()
        )
        self.assertIn("extra_forbidden", error)

    def test_visual_tools_are_registered_in_the_backend_agent(self) -> None:
        self.assertIn("observe_room", agent_tools.tool_map)
        self.assertIn("observe_home_harmony", agent_tools.tool_map)
        tool_names = {tool["function"]["name"] for tool in agent_tools.tools}
        self.assertTrue({"observe_room", "observe_home_harmony"}.issubset(tool_names))

    def test_visual_tool_result_passes_jpeg_as_image_input_not_tool_text(self) -> None:
        class Response:
            status_code = 200
            text = ""

            @staticmethod
            def json():
                return {
                    "result": {
                        "tool": "observe_room",
                        "room": {"label": "客厅"},
                        "views": [{"label": "主视角", "imageDataUrl": "data:image/jpeg;base64,abc"}],
                    }
                }

        with patch("agent_tools.httpx.post", return_value=Response()):
            output = agent_tools.observe_room("open_public")
        self.assertIsInstance(output, agent_tools.VisualToolOutput)
        self.assertNotIn("data:image", output.summary)
        message = agent_tools.visual_evidence_message([output])
        self.assertEqual(message["content"][2]["type"], "image_url")
        self.assertEqual(message["content"][2]["image_url"]["url"], "data:image/jpeg;base64,abc")


if __name__ == "__main__":
    unittest.main()
