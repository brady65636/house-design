"""工具产生的临时视觉消息生命周期：模型消费后必须真正删除，不残留 Base64。

覆盖：
1. 模型能看到刚注入的图片（标记为 ephemeral_visual_evidence）。
2. 模型成功返回后图片从 checkpoint 中真正删除（无 image_url、无 data:image）。
3. 模型调用失败时不删除，允许同线程重试。
4. 删除后新的 AI tool-call 与 ToolMessage 仍正确配对，无 invalid chat history。
5. 连续 12 轮 observe -> model -> delete 压力测试，历史体积不随图片线性增长。
6. Critic 本地多轮观察：每轮看到新图、下一轮不携带上一轮图片；调用失败 fail-closed。
"""

from __future__ import annotations

import asyncio
import base64
import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from langchain_core.messages import AIMessage, HumanMessage

from backend.agent_api.agent.critic import (
    critic_verdict_from_result,
    run_critic_review,
)
from backend.agent_api.agent.graph import build_graph
from backend.agent_api.store.checkpoints import open_async_checkpointer
from backend.agent_api.tools.tools import (
    VisualToolOutput,
    critic_tools,
    visual_evidence_message,
)
from backend.tests._responses_mock import responses_side_effect


def _marker(index: int) -> str:
    return base64.b64encode(f"round-{index}".encode("ascii")).decode("ascii")


def tool_call(name: str, call_id: str, args: dict | None = None) -> dict:
    return {
        "name": name,
        "args": args or {},
        "id": call_id,
        "type": "tool_call",
    }


def ready_room(version: str, room_id: str, marker: str) -> VisualToolOutput:
    return VisualToolOutput(
        summary=json.dumps(
            {
                "status": "ready",
                "modelEvidenceReady": True,
                "scheme": {"schemeId": version},
                "room": {"id": room_id},
            },
            ensure_ascii=False,
        ),
        images=[("房间证据", f"data:image/jpeg;base64,{marker}")],
    )


def _image_blocks(messages: list) -> list:
    blocks = []
    for message in messages:
        if isinstance(message, HumanMessage) and isinstance(message.content, list):
            for block in message.content:
                if isinstance(block, dict) and block.get("type") == "image_url":
                    blocks.append(block)
    return blocks


def _content_text(message) -> str:
    content = message.content
    if isinstance(content, str):
        return content
    return json.dumps(content, ensure_ascii=False)


def _input_image_blocks(input_items: list) -> list:
    """检查 Responses API input_items 里模型实际收到的图片块（input_image）。"""
    blocks = []
    for item in input_items or []:
        content = item.get("content")
        if isinstance(content, list):
            for block in content:
                if isinstance(block, dict) and block.get("type") == "input_image":
                    blocks.append(block)
    return blocks


def _input_text(input_items: list) -> str:
    return json.dumps(input_items, ensure_ascii=False)


class VisualMessageLifecycleTests(unittest.TestCase):
    @staticmethod
    def assert_no_visuals(messages: list) -> None:
        for message in messages:
            assert message.additional_kwargs.get("ephemeral_visual_evidence") is not True, (
                "ephemeral visual evidence message survived in checkpoint"
            )
            text = _content_text(message)
            assert "image_url" not in text, "image_url block survived in checkpoint"
            assert "data:image" not in text, "base64 image payload survived in checkpoint"

    @staticmethod
    def assert_tool_call_pairing(messages: list) -> None:
        tool_call_ids = {
            call["id"]
            for message in messages
            if getattr(message, "tool_calls", None)
            for call in message.tool_calls
        }
        tool_message_ids = {
            message.tool_call_id
            for message in messages
            if getattr(message, "tool_call_id", None)
        }
        assert tool_call_ids == tool_message_ids, (
            f"orphaned tool-calls: {tool_call_ids ^ tool_message_ids}"
        )

    # ---- 1. 模型能看到图片 ----

    def test_model_sees_image_before_deletion(self) -> None:
        fake = [
            AIMessage(
                content="",
                tool_calls=[tool_call("observe_room", "o1", {"room_id": "open_public"})],
            ),
            AIMessage(content="看到了房间渲染"),
        ]
        side_effect = responses_side_effect(fake)
        with patch("backend.agent_api.agent.graph.call_responses", side_effect=side_effect), patch(
            "backend.agent_api.agent.graph.execute_tool",
            return_value=ready_room("v1", "open_public", _marker(1)),
        ):
            graph = build_graph()
            config = {"configurable": {"thread_id": "see-image"}}
            graph.invoke({"messages": [HumanMessage(content="请观察房间")]}, config=config)

        self.assertEqual(len(side_effect.calls), 2)
        second_input = side_effect.calls[1]["input_items"]
        blocks = _input_image_blocks(second_input)
        self.assertEqual(len(blocks), 1)
        self.assertEqual(blocks[0]["image_url"], f"data:image/jpeg;base64,{_marker(1)}")

    # ---- 2. 成功后真正删除 ----

    def test_visuals_deleted_from_checkpoint_after_success(self) -> None:
        fake = [
                AIMessage(
                    content="",
                    tool_calls=[tool_call("observe_room", "o1", {"room_id": "open_public"})],
                ),
                AIMessage(content="完成"),
        ]
        with patch("backend.agent_api.agent.graph.call_responses", side_effect=responses_side_effect(fake)), patch(
            "backend.agent_api.agent.graph.execute_tool",
            return_value=ready_room("v1", "open_public", _marker(1)),
        ):
            graph = build_graph()
            config = {"configurable": {"thread_id": "deleted"}}
            result = graph.invoke({"messages": [HumanMessage(content="观察")]}, config=config)
            state = graph.get_state(config)

        self.assertEqual(result["messages"][-1].content, "完成")
        self.assert_no_visuals(result["messages"])
        self.assert_no_visuals(state.values["messages"])

    # ---- 3. 模型失败时不删除 ----

    def test_visuals_survive_model_failure_for_retry(self) -> None:
        fake = [
            AIMessage(
                content="",
                tool_calls=[tool_call("observe_room", "o1", {"room_id": "open_public"})],
            ),
            RuntimeError("simulated model failure after seeing image"),
        ]
        side_effect = responses_side_effect(fake)
        with patch("backend.agent_api.agent.graph.call_responses", side_effect=side_effect), patch(
            "backend.agent_api.agent.graph.execute_tool",
            return_value=ready_room("v1", "open_public", _marker(1)),
        ):
            graph = build_graph()
            config = {"configurable": {"thread_id": "failure-keeps-visuals"}}
            with self.assertRaises(RuntimeError):
                graph.invoke({"messages": [HumanMessage(content="观察")]}, config=config)
            state = graph.get_state(config)

        # 失败后临时视觉消息仍在 checkpoint，允许同一次调用重试
        blocks = _image_blocks(state.values["messages"])
        self.assertEqual(len(blocks), 1)
        self.assertEqual(blocks[0]["image_url"]["url"], f"data:image/jpeg;base64,{_marker(1)}")

    # ---- 4. 删除后工具调用仍然有效 ----

    def test_tool_calls_still_pair_after_visual_deletion(self) -> None:
        fake = [
            AIMessage(content="", tool_calls=[tool_call("observe_room", "o1", {"room_id": "open_public"})]),
            AIMessage(content="", tool_calls=[tool_call("observe_room", "o2", {"room_id": "open_public"})]),
            AIMessage(content="交付完成"),
        ]
        side_effect = responses_side_effect(fake)
        markers = iter([_marker(1), _marker(2)])

        def execute(name, args, call_id=None):
            return ready_room("v1", "open_public", next(markers))

        with patch("backend.agent_api.agent.graph.call_responses", side_effect=side_effect), patch(
            "backend.agent_api.agent.graph.execute_tool", side_effect=execute
        ):
            graph = build_graph()
            config = {"configurable": {"thread_id": "tool-pairing"}}
            result = graph.invoke({"messages": [HumanMessage(content="开始观察")]}, config=config)

        self.assertEqual(result["messages"][-1].content, "交付完成")
        self.assert_no_visuals(result["messages"])
        # 模型在第 2 次调用看到 V1 后返回了新的 tool-call
        self.assertEqual(len(_input_image_blocks(side_effect.calls[1]["input_items"])), 1)
        # 第 3 次调用看到的是 V2，上一轮 V1 已被删除，视觉消息不会累积
        self.assertEqual(len(_input_image_blocks(side_effect.calls[2]["input_items"])), 1)
        self.assertNotIn(
            _marker(1),
            _input_text(side_effect.calls[2]["input_items"]),
        )
        # 每个 AI tool-call 都有对应 ToolMessage，没有孤儿
        self.assert_tool_call_pairing(result["messages"])

    # ---- 4b. 工具批次异常闭合 ----

    def test_failing_tool_in_batch_still_closes_each_tool_call(self) -> None:
        fake = [
                AIMessage(
                    content="",
                    tool_calls=[
                        tool_call("get_room_by_id", "boom-1", {"room_id": "open_public"}),
                        tool_call("load_scheme", "ok-1", {}),
                    ],
                ),
                AIMessage(content="继续"),
        ]

        def execute(name, args, call_id=None):
            if name == "get_room_by_id":
                raise RuntimeError("simulated tool crash")
            return '{"scheme": {}}'

        with patch("backend.agent_api.agent.graph.call_responses", side_effect=responses_side_effect(fake)), patch(
            "backend.agent_api.agent.graph.execute_tool", side_effect=execute
        ):
            graph = build_graph()
            config = {"configurable": {"thread_id": "tool-exception"}}
            result = graph.invoke({"messages": [HumanMessage(content="查询")]}, config=config)

        self.assert_tool_call_pairing(result["messages"])
        tool_by_id = {
            message.tool_call_id: message
            for message in result["messages"]
            if getattr(message, "tool_call_id", None)
        }
        self.assertIn("TOOL_EXECUTION_FAILED", tool_by_id["boom-1"].content)
        self.assertIn('"scheme"', tool_by_id["ok-1"].content)
        self.assertEqual(result["messages"][-1].content, "继续")

    # ---- 5. 多轮压力测试 ----

    def test_stress_observe_model_delete_12_rounds(self) -> None:
        rounds = 12
        responses: list[AIMessage] = [
            AIMessage(
                content="",
                tool_calls=[
                    tool_call("observe_room", f"o{i + 1}", {"room_id": "open_public"})
                ],
            )
            for i in range(rounds)
        ] + [AIMessage(content="十二轮观察完成")]
        markers = [_marker(i) for i in range(1, rounds + 1)]
        marker_iter = iter(markers)

        def execute(name, args, call_id=None):
            return ready_room("v1", "open_public", next(marker_iter))

        side_effect = responses_side_effect(responses)
        with patch("backend.agent_api.agent.graph.call_responses", side_effect=side_effect), patch(
            "backend.agent_api.agent.graph.execute_tool", side_effect=execute
        ):
            graph = build_graph()
            config = {"configurable": {"thread_id": "stress"}}
            result = graph.invoke({"messages": [HumanMessage(content="连续观察")]}, config=config)
            state = graph.get_state(config)

        # 共 rounds 次 observe + 1 次收尾 = rounds + 1 次模型调用
        self.assertEqual(len(side_effect.calls), rounds + 1)
        for i in range(1, rounds + 1):
            invocation_input = side_effect.calls[i]["input_items"]
            text = _input_text(invocation_input)
            # 本轮图片可见
            self.assertIn(markers[i - 1], text)
            # 本轮只有 1 张图，上一轮及更早的图片都被删除了
            self.assertEqual(len(_input_image_blocks(invocation_input)), 1)
            for previous in range(i - 1):
                self.assertNotIn(markers[previous], text)
        # 结束后 checkpoint 中没有任何 Base64 图片残留
        self.assert_no_visuals(result["messages"])
        self.assert_no_visuals(state.values["messages"])
        # 历史体积不随 Base64 图片线性增长：messages 只含文字与 JSON
        self.assert_tool_call_pairing(result["messages"])

    # ---- 6. Critic 本地循环 ----

    def test_critic_sees_fresh_image_each_round_and_drops_old(self) -> None:
        rounds = 3
        responses: list[AIMessage] = [
            AIMessage(
                content="",
                tool_calls=[
                    tool_call("observe_room", f"critic-o{i + 1}", {"room_id": "living_room"})
                ],
            )
            for i in range(rounds)
        ] + [AIMessage(content="CRITIC_VERDICT: REVISE\n降低墙地黄色叠加")]
        markers = [_marker(i) for i in range(1, rounds + 1)]
        marker_iter = iter(markers)

        def execute(name, args, call_id=None):
            return VisualToolOutput(
                summary='{"room_id":"living_room"}',
                images=[("客厅主视图", f"data:image/jpeg;base64,{next(marker_iter)}")],
            )

        side_effect = responses_side_effect(responses)
        with patch("backend.agent_api.agent.critic.call_responses", side_effect=side_effect):
            result = run_critic_review(
                "检查客厅是否明亮柔和",
                design_context="设计知识",
                house_context="活动住宅",
                tool_definitions=critic_tools,
                execute_readonly_tool=execute,
                build_visual_message=visual_evidence_message,
            )

        self.assertIn("降低墙地黄色叠加", result)
        self.assertEqual(critic_verdict_from_result(result), "REVISE")
        self.assertEqual(len(side_effect.calls), rounds + 1)
        for i in range(1, rounds + 1):
            invocation_input = side_effect.calls[i]["input_items"]
            text = _input_text(invocation_input)
            # 本轮刚获得的图片可见
            self.assertIn(markers[i - 1], text)
            # 下一轮请求不再包含上一轮图片
            for previous in range(i - 1):
                self.assertNotIn(markers[previous], text)

    def test_sqlite_checkpoint_keeps_no_base64_after_consumption(self) -> None:
        async def run_round(db_path: Path, responses: list[AIMessage]) -> list:
            checkpointer = await open_async_checkpointer(db_path)
            try:
                graph = build_graph(checkpointer=checkpointer)
                config = {"configurable": {"thread_id": "sqlite-lifecycle"}}
                side_effect = responses_side_effect(responses)
                with patch(
                    "backend.agent_api.agent.graph.call_responses", side_effect=side_effect
                ), patch(
                    "backend.agent_api.agent.graph.execute_tool",
                    side_effect=lambda _name, _args, _call_id=None: ready_room(
                        "v1", "open_public", _marker(1)
                    ),
                ):
                    await graph.ainvoke(
                        {"messages": [HumanMessage(content="观察")]}, config=config
                    )
                state = await graph.aget_state(config)
                return list(state.values["messages"])
            finally:
                await checkpointer.conn.close()

        with tempfile.TemporaryDirectory() as tmp:
            db_path = Path(tmp) / "lifecycle.sqlite"
            first = asyncio.run(
                run_round(
                    db_path,
                    [
                        AIMessage(content="", tool_calls=[tool_call("observe_room", "o1", {"room_id": "open_public"})]),
                        AIMessage(content="第一轮完成"),
                    ],
                )
            )
            # 第二轮模拟进程重启后的同 thread 新调用；历史消息也必须无图片残留
            second = asyncio.run(
                run_round(
                    db_path,
                    [
                        AIMessage(content="", tool_calls=[tool_call("observe_room", "o2", {"room_id": "open_public"})]),
                        AIMessage(content="第二轮完成"),
                    ],
                )
            )

        self.assert_no_visuals(first)
        self.assert_no_visuals(second)
        self.assertEqual(second[-1].content, "第二轮完成")

    def test_critic_model_failure_returns_fail_closed_result(self) -> None:
        side_effect = responses_side_effect([RuntimeError("Rate limit exceeded for model")])
        with patch("backend.agent_api.agent.critic.call_responses", side_effect=side_effect):
            result = run_critic_review(
                "检查客厅",
                design_context="设计知识",
                house_context="活动住宅",
                tool_definitions=critic_tools,
                execute_readonly_tool=lambda _name, _args, _call_id=None: "{}",
                build_visual_message=lambda _outputs: {"content": []},
            )

        payload = json.loads(result)
        self.assertEqual(payload["status"], "failed")
        self.assertEqual(payload["error_type"], "rate_limit")
        self.assertTrue(payload["retryable"])
        # fail-closed：没有 verdict，门禁保持阻断
        self.assertEqual(critic_verdict_from_result(result), "UNABLE_TO_JUDGE")


if __name__ == "__main__":
    unittest.main()
