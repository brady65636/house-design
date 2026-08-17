"""The Critic is an independent read-only Agent and delivery gate."""

import json
import unittest
from unittest.mock import patch

from langchain_core.messages import AIMessage

from backend.agent_api.agent.critic import (
    CRITIC_SYSTEM_PROMPT,
    critic_verdict_from_result,
    normalize_critic_review,
    run_critic_review,
)
from backend.agent_api.tools.tools import VisualToolOutput, critic_tools, tools
from backend.tests._responses_mock import responses_side_effect


def _tool_call(name: str, args: dict, call_id: str) -> dict:
    return {"name": name, "args": args, "id": call_id, "type": "tool_call"}


class CriticAgentTests(unittest.TestCase):
    def test_critic_prompt_contains_plain_language_rubrics(self) -> None:
        self.assertIn("这 12 条大白话标准", CRITIC_SYSTEM_PROMPT)
        self.assertIn("两边地板颜色不能明显打架", CRITIC_SYSTEM_PROMPT)
        self.assertIn("不能像三个互不相关的样板间", CRITIC_SYSTEM_PROMPT)
        self.assertIn("墙面和地面的颜色放在一起不能互相显脏", CRITIC_SYSTEM_PROMPT)
        self.assertIn("只能给出“通过”“不通过”或“无法判断”", CRITIC_SYSTEM_PROMPT)
        self.assertIn("status=ready", CRITIC_SYSTEM_PROMPT)
        self.assertIn("pixel_verified_coverage", CRITIC_SYSTEM_PROMPT)
        self.assertIn("诊断元数据不构成视觉证明", CRITIC_SYSTEM_PROMPT)
        self.assertIn("CRITIC_VERDICT: PASS", CRITIC_SYSTEM_PROMPT)
        self.assertIn("阻止主 Agent 交付", CRITIC_SYSTEM_PROMPT)

    def test_critic_toolset_is_read_only_and_not_recursive(self) -> None:
        names = {tool["function"]["name"] for tool in critic_tools}
        self.assertIn("load_scheme", names)
        self.assertIn("observe_room", names)
        self.assertNotIn("update_scheme", names)
        self.assertNotIn("set_design_work_type", names)
        self.assertNotIn("ask_design_critic", names)
        self.assertIn(
            "ask_design_critic",
            {tool["function"]["name"] for tool in tools},
        )
        critic_description = next(
            tool["function"]["description"]
            for tool in tools
            if tool["function"]["name"] == "ask_design_critic"
        )
        self.assertIn("完整设计", critic_description)
        self.assertIn("轻度修改不使用", critic_description)
        self.assertIn("只有 PASS 才能交付", critic_description)
        self.assertIn("PASS 失效", critic_description)

    def test_critic_can_observe_images_then_return_advice(self) -> None:
        fake = [
            AIMessage(
                content="",
                tool_calls=[
                    _tool_call(
                        "observe_room",
                        {"room_id": "living_room", "focus_target_ids": []},
                        "critic-observe-1",
                    )
                ],
            ),
            AIMessage(
                content=(
                    "CRITIC_VERDICT: REVISE\n"
                    "总体判断：建议降低墙地之间的黄色叠加。"
                )
            ),
        ]
        side_effect = responses_side_effect(fake)

        evidence = VisualToolOutput(
            summary='{"room_id":"living_room"}',
            images=[("客厅主视图", "data:image/jpeg;base64,ZmFrZQ==")],
        )

        def execute(name, args, call_id=None):
            self.assertEqual(name, "observe_room")
            self.assertEqual(args["room_id"], "living_room")
            return evidence

        def build_visual(outputs):
            self.assertEqual(outputs, [evidence])
            return {
                "content": [
                    {"type": "text", "text": "真实渲染"},
                    {
                        "type": "image_url",
                        "image_url": {"url": evidence.images[0][1]},
                    },
                ]
            }

        with patch(
            "backend.agent_api.agent.critic.call_responses",
            side_effect=side_effect,
        ):
            result = run_critic_review(
                "检查客厅是否符合明亮柔和且不偏黄",
                design_context="设计知识",
                house_context="活动住宅",
                tool_definitions=critic_tools,
                execute_readonly_tool=execute,
                build_visual_message=build_visual,
            )

        self.assertIn("降低墙地之间的黄色叠加", result)
        self.assertEqual(critic_verdict_from_result(result), "REVISE")
        self.assertEqual(len(side_effect.calls), 2)
        second_input = side_effect.calls[1]["input_items"]
        self.assertTrue(
            any(
                item.get("role") == "user"
                and isinstance(item.get("content"), list)
                and any(block.get("type") == "input_image" for block in item.get("content", []))
                for item in second_input
            )
        )

    def test_critic_does_not_receive_visual_message_when_gate_blocks_images(self) -> None:
        fake = [
            AIMessage(
                content="",
                tool_calls=[_tool_call("observe_room", {"room_id": "kitchen"}, "blocked")],
            ),
            AIMessage(
                content=(
                    "CRITIC_VERDICT: UNABLE_TO_JUDGE\n"
                    "无法判断：观察不完整，需要重新渲染。"
                )
            ),
        ]
        side_effect = responses_side_effect(fake)
        evidence = VisualToolOutput(
            summary='{"status":"incomplete_observation","modelEvidenceReady":false}',
            images=[],
        )

        with patch("backend.agent_api.agent.critic.call_responses", side_effect=side_effect):
            result = run_critic_review(
                "检查厨房",
                design_context="设计知识",
                house_context="活动住宅",
                tool_definitions=critic_tools,
                execute_readonly_tool=lambda _name, _args, _call_id=None: evidence,
                build_visual_message=lambda _outputs: self.fail("blocked images must not be injected"),
            )

        self.assertIn("无法判断", result)
        self.assertEqual(critic_verdict_from_result(result), "UNABLE_TO_JUDGE")
        second_input = side_effect.calls[1]["input_items"]
        self.assertFalse(
            any(
                item.get("role") == "user" and isinstance(item.get("content"), list)
                for item in second_input
            )
        )

    def test_missing_or_malformed_verdict_fails_closed(self) -> None:
        missing = normalize_critic_review("总体看起来不错，但没有给门禁结论。")
        malformed = json.dumps({"verdict": "MAYBE", "review": "不确定"}, ensure_ascii=False)

        self.assertEqual(critic_verdict_from_result(missing), "UNABLE_TO_JUDGE")
        self.assertEqual(critic_verdict_from_result(malformed), "UNABLE_TO_JUDGE")
        self.assertEqual(critic_verdict_from_result("not-json"), "UNABLE_TO_JUDGE")


if __name__ == "__main__":
    unittest.main()
