"""Graph-owned work-type, Scheme-write, evidence, and Critic gates."""

from __future__ import annotations

import json
import unittest
from unittest.mock import patch

from langchain_core.messages import AIMessage, HumanMessage

from backend.agent_api.agent.graph import (
    CRITIC_BUDGET_EXHAUSTED_MESSAGE,
    DELIVERY_BLOCKED_MESSAGE,
    build_graph,
)
from backend.agent_api.tools.tools import VisualToolOutput
from backend.tests._responses_mock import responses_side_effect


def tool_call(name: str, call_id: str, args: dict | None = None) -> dict:
    return {
        "name": name,
        "args": args or {},
        "id": call_id,
        "type": "tool_call",
    }


def start_call(work_type: str, call_id: str = "start") -> dict:
    return tool_call(
        "set_design_work_type",
        call_id,
        {"work_type": work_type, "reason": "用户已经批准当前设计开始实施"},
    )


def start_result(work_type: str) -> str:
    return json.dumps(
        {
            "status": "WORK_TYPE_REQUEST_VALID",
            "requested_work_type": work_type,
            "reason": "用户已经批准当前设计开始实施",
        },
        ensure_ascii=False,
    )


def critic_result(verdict: str, review: str = "审查结论") -> str:
    return json.dumps({"verdict": verdict, "review": review}, ensure_ascii=False)


def ready_room(version: str, room_id: str) -> VisualToolOutput:
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
        images=[("房间证据", "data:image/jpeg;base64,ZmFrZQ==")],
    )


def review_turn(write_id: str, observe_id: str, critic_id: str, target: str) -> list[AIMessage]:
    """One HEAVY revision loop: modify Scheme, re-observe, re-review."""
    return [
        AIMessage(
            content="",
            tool_calls=[
                tool_call(
                    "update_scheme",
                    write_id,
                    {"target_id": target, "asset_id": "paint_greige_01"},
                )
            ],
        ),
        AIMessage(
            content="",
            tool_calls=[
                tool_call("observe_room", observe_id, {"room_id": "open_public"})
            ],
        ),
        AIMessage(
            content="",
            tool_calls=[tool_call("ask_design_critic", critic_id)],
        ),
    ]


class CriticDeliveryGateTests(unittest.TestCase):
    @staticmethod
    def invoke_graph(graph, messages: list, thread_id: str = "critic-gate-test") -> dict:
        return graph.invoke(
            {"messages": messages},
            config={"configurable": {"thread_id": thread_id}},
        )

    def test_not_started_blocks_scheme_write(self) -> None:
        fake = [
                AIMessage(
                    content="",
                    tool_calls=[
                        tool_call(
                            "update_scheme",
                            "write-1",
                            {"target_id": "wall_face_real4_010", "asset_id": "paint_greige_01"},
                        )
                    ],
                ),
                AIMessage(content="先继续规划，不宣称已经修改"),
        ]
        with patch("backend.agent_api.agent.graph.call_responses", side_effect=responses_side_effect(fake)), patch(
            "backend.agent_api.agent.graph.execute_tool"
        ) as execute:
            result = self.invoke_graph(build_graph(), [HumanMessage(content="先给我方案")])

        execute.assert_not_called()
        tool_message = next(
            message for message in result["messages"] if getattr(message, "tool_call_id", None)
        )
        self.assertIn("SCHEME_WRITE_BLOCKED", tool_message.content)
        self.assertEqual(result["messages"][-1].content, "先继续规划，不宣称已经修改")

    def test_start_and_update_in_same_batch_never_write(self) -> None:
        fake = [
                AIMessage(
                    content="",
                    tool_calls=[
                        start_call("LIGHT", "start-1"),
                        tool_call(
                            "update_scheme",
                            "write-1",
                            {"target_id": "wall_face_real4_010", "asset_id": "paint_greige_01"},
                        ),
                    ],
                ),
                AIMessage(
                    content="",
                    tool_calls=[
                        tool_call(
                            "update_scheme",
                            "write-2",
                            {"target_id": "wall_face_real4_010", "asset_id": "paint_greige_01"},
                        )
                    ],
                ),
                AIMessage(
                    content="",
                    tool_calls=[
                        tool_call(
                            "observe_room",
                            "observe-1",
                            {"room_id": "open_public", "focus_target_ids": ["wall_face_real4_010"]},
                        )
                    ],
                ),
                AIMessage(content="轻度修改交付"),
        ]

        def execute(name, args, call_id=None):
            if name == "set_design_work_type":
                return start_result(args["work_type"])
            if name == "update_scheme":
                return "修改scheme成功，新方案ID：version-light"
            if name == "observe_room":
                return ready_room("version-light", "open_public")
            raise AssertionError(name)

        with patch("backend.agent_api.agent.graph.call_responses", side_effect=responses_side_effect(fake)), patch(
            "backend.agent_api.agent.graph.execute_tool", side_effect=execute
        ) as mocked:
            result = self.invoke_graph(build_graph(), [HumanMessage(content="批准轻度修改")])

        update_calls = [
            call for call in mocked.call_args_list if call.args and call.args[0] == "update_scheme"
        ]
        self.assertEqual(len(update_calls), 1)
        blocked = [
            message.content
            for message in result["messages"]
            if getattr(message, "tool_call_id", None) == "write-1"
        ]
        self.assertTrue(blocked and "必须位于不同" in blocked[0])
        self.assertEqual(result["messages"][-1].content, "轻度修改交付")

    def test_light_work_can_finish_after_write_and_current_room_evidence(self) -> None:
        fake = [
                AIMessage(content="", tool_calls=[start_call("LIGHT")]),
                AIMessage(
                    content="",
                    tool_calls=[
                        tool_call(
                            "update_scheme",
                            "write",
                            {"target_id": "wall_face_real4_010", "asset_id": "paint_greige_01"},
                        )
                    ],
                ),
                AIMessage(
                    content="",
                    tool_calls=[
                        tool_call(
                            "observe_room",
                            "observe",
                            {"room_id": "open_public", "focus_target_ids": ["wall_face_real4_010"]},
                        )
                    ],
                ),
                AIMessage(content="LIGHT 完成交付"),
        ]

        def execute(name, args, call_id=None):
            if name == "set_design_work_type":
                return start_result(args["work_type"])
            if name == "update_scheme":
                return "修改scheme成功，新方案ID：version-light"
            return ready_room("version-light", "open_public")

        with patch("backend.agent_api.agent.graph.call_responses", side_effect=responses_side_effect(fake)), patch(
            "backend.agent_api.agent.graph.execute_tool", side_effect=execute
        ):
            result = self.invoke_graph(build_graph(), [HumanMessage(content="批准修改")])

        self.assertEqual(result["work_type"], "LIGHT")
        self.assertEqual(result["critic_verdict"], "NOT_REVIEWED")
        self.assertEqual(result["messages"][-1].content, "LIGHT 完成交付")

    def test_light_quota_overrun_promotes_to_heavy_and_requires_pass(self) -> None:
        fake = [
                AIMessage(content="", tool_calls=[start_call("LIGHT")]),
                AIMessage(
                    content="",
                    tool_calls=[
                        tool_call("update_scheme", "w1", {"target_id": "wall_face_real4_002", "asset_id": "paint_greige_01"}),
                        tool_call("update_scheme", "w2", {"target_id": "wall_face_real4_010", "asset_id": "paint_greige_01"}),
                        tool_call("update_scheme", "w3", {"target_id": "wall_face_real4_013", "asset_id": "wallpaper_linen_natural_01"}),
                    ],
                ),
                AIMessage(content="", tool_calls=[tool_call("observe_room", "o1", {"room_id": "open_public"})]),
                AIMessage(content="不能直接交付"),
                AIMessage(content="", tool_calls=[tool_call("ask_design_critic", "c1")]),
                AIMessage(content="升级后通过交付"),
        ]
        update_versions = iter(["v1", "v2", "v3"])

        def execute(name, args, call_id=None):
            if name == "set_design_work_type":
                return start_result(args["work_type"])
            if name == "update_scheme":
                return f"修改scheme成功，新方案ID：{next(update_versions)}"
            if name == "observe_room":
                return ready_room("v3", "open_public")
            return critic_result("PASS")

        with patch("backend.agent_api.agent.graph.call_responses", side_effect=responses_side_effect(fake)), patch(
            "backend.agent_api.agent.graph.execute_tool", side_effect=execute
        ):
            result = self.invoke_graph(build_graph(), [HumanMessage(content="开始")])

        self.assertEqual(result["work_type"], "HEAVY")
        self.assertEqual(result["critic_verdict"], "PASS")
        self.assertEqual(result["critic_reviewed_scheme_version"], "v3")
        self.assertEqual(result["messages"][-1].content, "升级后通过交付")
        self.assertTrue(
            any(
                isinstance(message, HumanMessage)
                and "DELIVERY_GATE_BLOCKED" in str(message.content)
                for message in result["messages"]
            )
        )

    def test_heavy_revise_requires_new_write_evidence_and_pass(self) -> None:
        fake = [
                AIMessage(content="", tool_calls=[start_call("HEAVY")]),
                AIMessage(content="", tool_calls=[tool_call("update_scheme", "w1", {"target_id": "wall_face_real4_010", "asset_id": "paint_greige_01"})]),
                AIMessage(content="", tool_calls=[tool_call("observe_room", "o1", {"room_id": "open_public"})]),
                AIMessage(content="", tool_calls=[tool_call("ask_design_critic", "c1")]),
                AIMessage(content="错误的完成声明"),
                AIMessage(content="", tool_calls=[tool_call("update_scheme", "w2", {"target_id": "wall_face_real4_013", "asset_id": "wallpaper_linen_natural_01"})]),
                AIMessage(content="", tool_calls=[tool_call("observe_room", "o2", {"room_id": "open_public"})]),
                AIMessage(content="", tool_calls=[tool_call("ask_design_critic", "c2")]),
                AIMessage(content="通过后最终交付"),
        ]
        reviews = iter([critic_result("REVISE"), critic_result("PASS")])
        versions = iter(["v1", "v2"])

        def execute(name, args, call_id=None):
            if name == "set_design_work_type":
                return start_result(args["work_type"])
            if name == "update_scheme":
                return f"修改scheme成功，新方案ID：{next(versions)}"
            if name == "observe_room":
                expected = "v1" if args.get("focus_target_ids") == ["first"] else None
                del expected
                return ready_room("v1" if args == {"room_id": "open_public"} and False else "v2", "open_public")
            return next(reviews)

        # Distinguish the two observation versions without complicating model args.
        observation_versions = iter(["v1", "v2"])

        def execute_ordered(name, args, call_id=None):
            if name == "observe_room":
                return ready_room(next(observation_versions), "open_public")
            return execute(name, args)

        with patch("backend.agent_api.agent.graph.call_responses", side_effect=responses_side_effect(fake)), patch(
            "backend.agent_api.agent.graph.execute_tool", side_effect=execute_ordered
        ):
            result = self.invoke_graph(build_graph(), [HumanMessage(content="批准完整设计")])

        self.assertEqual(result["messages"][-1].content, "通过后最终交付")
        self.assertEqual(result["critic_verdict"], "PASS")
        self.assertEqual(result["critic_reviewed_scheme_version"], "v2")

    def test_repeated_refusal_ends_with_safe_non_delivery_message(self) -> None:
        fake = [
                AIMessage(content="", tool_calls=[start_call("HEAVY")]),
                AIMessage(content="", tool_calls=[tool_call("update_scheme", "w1", {"target_id": "wall_face_real4_010", "asset_id": "paint_greige_01"})]),
                AIMessage(content="", tool_calls=[tool_call("observe_room", "o1", {"room_id": "open_public"})]),
                AIMessage(content="", tool_calls=[tool_call("ask_design_critic", "c1")]),
                AIMessage(content="错误交付一"),
                AIMessage(content="错误交付二"),
                AIMessage(content="错误交付三"),
                AIMessage(content="错误交付四"),
        ]

        def execute(name, args, call_id=None):
            if name == "set_design_work_type":
                return start_result(args["work_type"])
            if name == "update_scheme":
                return "修改scheme成功，新方案ID：v1"
            if name == "observe_room":
                return ready_room("v1", "open_public")
            return critic_result("UNABLE_TO_JUDGE")

        with patch("backend.agent_api.agent.graph.call_responses", side_effect=responses_side_effect(fake)), patch(
            "backend.agent_api.agent.graph.execute_tool", side_effect=execute
        ):
            result = self.invoke_graph(build_graph(), [HumanMessage(content="交付")])

        self.assertEqual(result["messages"][-1].content, DELIVERY_BLOCKED_MESSAGE)
        self.assertTrue(result["delivery_gate_locked"])

    def test_revise_revise_pass_delivers_within_budget(self) -> None:
        fake = [
                AIMessage(content="", tool_calls=[start_call("HEAVY")]),
                *review_turn("w1", "o1", "c1", "wall_face_real4_010"),
                *review_turn("w2", "o2", "c2", "wall_face_real4_013"),
                *review_turn("w3", "o3", "c3", "wall_face_real4_010"),
                AIMessage(content="三次后正常交付"),
        ]
        reviews = iter(
            [critic_result("REVISE"), critic_result("REVISE"), critic_result("PASS")]
        )
        versions = iter(["v1", "v2", "v3"])

        def execute(name, args, call_id=None):
            if name == "set_design_work_type":
                return start_result(args["work_type"])
            if name == "update_scheme":
                return f"修改scheme成功，新方案ID：{next(versions)}"
            return next(reviews)

        observation_versions = iter(["v1", "v2", "v3"])

        def execute_ordered(name, args, call_id=None):
            if name == "observe_room":
                return ready_room(next(observation_versions), "open_public")
            return execute(name, args)

        with patch("backend.agent_api.agent.graph.call_responses", side_effect=responses_side_effect(fake)), patch(
            "backend.agent_api.agent.graph.execute_tool", side_effect=execute_ordered
        ):
            result = self.invoke_graph(build_graph(), [HumanMessage(content="批准完整设计")])

        self.assertEqual(result["critic_attempt_count"], 3)
        self.assertEqual(result["critic_verdict"], "PASS")
        self.assertIs(result["critic_budget_exhausted"], False)
        self.assertEqual(result["messages"][-1].content, "三次后正常交付")

    def test_three_revises_stop_at_budget_without_delivery(self) -> None:
        fake = [
                AIMessage(content="", tool_calls=[start_call("HEAVY")]),
                AIMessage(content="", tool_calls=[tool_call("ask_design_critic", "c1")]),
                AIMessage(content="", tool_calls=[tool_call("ask_design_critic", "c2")]),
                AIMessage(content="", tool_calls=[tool_call("ask_design_critic", "c3")]),
        ]

        def execute(name, args, call_id=None):
            if name == "set_design_work_type":
                return start_result(args["work_type"])
            return critic_result("REVISE")

        with patch("backend.agent_api.agent.graph.call_responses", side_effect=responses_side_effect(fake)), patch(
            "backend.agent_api.agent.graph.execute_tool", side_effect=execute
        ):
            result = self.invoke_graph(build_graph(), [HumanMessage(content="交付")])

        self.assertEqual(result["critic_attempt_count"], 3)
        self.assertEqual(result["critic_verdict"], "REVISE")
        self.assertIs(result["critic_budget_exhausted"], True)
        self.assertIs(result["delivery_gate_locked"], True)
        self.assertEqual(result["messages"][-1].content, CRITIC_BUDGET_EXHAUSTED_MESSAGE)

    def test_unable_rate_limit_revise_exhaust_budget_and_stop(self) -> None:
        rate_limit_failure = json.dumps(
            {
                "status": "failed",
                "error_type": "rate_limit",
                "retryable": True,
                "message": "Critic model call failed; no verdict was produced.",
            },
            ensure_ascii=False,
        )
        fake = [
                AIMessage(content="", tool_calls=[start_call("HEAVY")]),
                AIMessage(content="", tool_calls=[tool_call("ask_design_critic", "c1")]),
                AIMessage(content="", tool_calls=[tool_call("ask_design_critic", "c2")]),
                AIMessage(content="", tool_calls=[tool_call("ask_design_critic", "c3")]),
        ]
        reviews = iter(
            [critic_result("UNABLE_TO_JUDGE"), rate_limit_failure, critic_result("REVISE")]
        )

        def execute(name, args, call_id=None):
            if name == "set_design_work_type":
                return start_result(args["work_type"])
            return next(reviews)

        with patch("backend.agent_api.agent.graph.call_responses", side_effect=responses_side_effect(fake)), patch(
            "backend.agent_api.agent.graph.execute_tool", side_effect=execute
        ):
            result = self.invoke_graph(build_graph(), [HumanMessage(content="完整设计交付")])

        self.assertEqual(result["critic_attempt_count"], 3)
        self.assertEqual(result["critic_verdict"], "REVISE")
        self.assertIs(result["critic_budget_exhausted"], True)
        self.assertEqual(result["messages"][-1].content, CRITIC_BUDGET_EXHAUSTED_MESSAGE)

    def test_critic_budget_not_reset_by_scheme_or_evidence_progress(self) -> None:
        fake = [
                AIMessage(content="", tool_calls=[start_call("HEAVY")]),
                *review_turn("w1", "o1", "c1", "wall_face_real4_010"),
                *review_turn("w2", "o2", "c2", "wall_face_real4_013"),
                *review_turn("w3", "o3", "c3", "wall_face_real4_010"),
        ]
        reviews = iter(
            [critic_result("REVISE"), critic_result("REVISE"), critic_result("REVISE")]
        )
        versions = iter(["v1", "v2", "v3"])

        def execute(name, args, call_id=None):
            if name == "set_design_work_type":
                return start_result(args["work_type"])
            if name == "update_scheme":
                return f"修改scheme成功，新方案ID：{next(versions)}"
            return next(reviews)

        observation_versions = iter(["v1", "v2", "v3"])

        def execute_ordered(name, args, call_id=None):
            if name == "observe_room":
                return ready_room(next(observation_versions), "open_public")
            return execute(name, args)

        graph = build_graph()
        config = {"configurable": {"thread_id": "budget-monotonic"}}
        with patch("backend.agent_api.agent.graph.call_responses", side_effect=responses_side_effect(fake)), patch(
            "backend.agent_api.agent.graph.execute_tool", side_effect=execute_ordered
        ):
            result = graph.invoke(
                {"messages": [HumanMessage(content="开始")]}, config=config
            )
            checkpoint = graph.get_state(config)

        self.assertEqual(result["critic_attempt_count"], 3)
        self.assertIs(result["critic_budget_exhausted"], True)
        self.assertEqual(result["messages"][-1].content, CRITIC_BUDGET_EXHAUSTED_MESSAGE)
        self.assertNotIn("critic_attempt_count", checkpoint.values)
        self.assertNotIn("critic_budget_exhausted", checkpoint.values)

    def test_blocked_fourth_call_keeps_existing_pass_and_delivers(self) -> None:
        fake = [
                AIMessage(content="", tool_calls=[start_call("HEAVY")]),
                *review_turn("w1", "o1", "c1", "wall_face_real4_010"),
                *review_turn("w2", "o2", "c2", "wall_face_real4_013"),
                *review_turn("w3", "o3", "c3", "wall_face_real4_010"),
                AIMessage(content="", tool_calls=[tool_call("ask_design_critic", "c4")]),
                AIMessage(content="拦截后仍按最后一次 PASS 交付"),
        ]
        reviews = iter(
            [critic_result("REVISE"), critic_result("REVISE"), critic_result("PASS")]
        )
        versions = iter(["v1", "v2", "v3"])

        def execute(name, args, call_id=None):
            if name == "set_design_work_type":
                return start_result(args["work_type"])
            if name == "update_scheme":
                return f"修改scheme成功，新方案ID：{next(versions)}"
            return next(reviews)

        observation_versions = iter(["v1", "v2", "v3"])

        def execute_ordered(name, args, call_id=None):
            if name == "observe_room":
                return ready_room(next(observation_versions), "open_public")
            return execute(name, args)

        with patch("backend.agent_api.agent.graph.call_responses", side_effect=responses_side_effect(fake)), patch(
            "backend.agent_api.agent.graph.execute_tool", side_effect=execute_ordered
        ):
            result = self.invoke_graph(build_graph(), [HumanMessage(content="批准完整设计")])

        blocked = [
            message.content
            for message in result["messages"]
            if getattr(message, "tool_call_id", None) == "c4"
        ]
        self.assertTrue(blocked and "CRITIC_BUDGET_EXHAUSTED" in blocked[0])
        self.assertEqual(result["critic_attempt_count"], 3)
        self.assertEqual(result["critic_verdict"], "PASS")
        self.assertEqual(result["critic_reviewed_scheme_version"], "v3")
        self.assertEqual(result["messages"][-1].content, "拦截后仍按最后一次 PASS 交付")

    def test_same_thread_next_invoke_restores_only_messages(self) -> None:
        fake = [
                AIMessage(content="", tool_calls=[start_call("LIGHT")]),
                AIMessage(content="", tool_calls=[tool_call("update_scheme", "w1", {"target_id": "wall_face_real4_010", "asset_id": "paint_greige_01"})]),
                AIMessage(content="", tool_calls=[tool_call("observe_room", "o1", {"room_id": "open_public"})]),
                AIMessage(content="第一项轻度修改完成"),
                AIMessage(content="下一项仍处于规划，可以直接回复"),
        ]

        def execute(name, args, call_id=None):
            if name == "set_design_work_type":
                return start_result(args["work_type"])
            if name == "update_scheme":
                return "修改scheme成功，新方案ID：v1"
            return ready_room("v1", "open_public")

        graph = build_graph()
        config = {"configurable": {"thread_id": "same-thread"}}
        with patch("backend.agent_api.agent.graph.call_responses", side_effect=responses_side_effect(fake)), patch(
            "backend.agent_api.agent.graph.execute_tool", side_effect=execute
        ):
            first = graph.invoke({"messages": [HumanMessage(content="第一项")]} , config=config)
            checkpoint = graph.get_state(config)
            second = graph.invoke({"messages": [HumanMessage(content="第二项")]} , config=config)

        self.assertEqual(first["work_type"], "LIGHT")
        self.assertNotIn("work_type", checkpoint.values)
        self.assertNotIn("critic_verdict", checkpoint.values)
        self.assertEqual(second["messages"][-1].content, "下一项仍处于规划，可以直接回复")
        self.assertNotIn("work_type", second)

    def test_renderer_offline_stops_after_two_strikes(self) -> None:
        """渲染器离线连续失败 2 次后，图进入 renderer_offline_stopped 停止节点。

        回归：生产环境渲染器（用户浏览器 local-demo 会话）掉线时，Agent 之前会
        无限重试 observe_room / ask_design_critic 死循环烧 token（实测 25 分钟）；
        现在第 2 次离线失败后必须停止并如实告知，不再调用任何工具。
        """
        from backend.agent_api.agent.graph import RENDERER_OFFLINE_STOPPED_MESSAGE

        fake = [
            AIMessage(content="", tool_calls=[start_call("HEAVY")]),
            AIMessage(
                content="",
                tool_calls=[
                    tool_call("update_scheme", "w1", {"target_id": "wall_face_real4_010", "asset_id": "paint_greige_01"})
                ],
            ),
            # 第一次观察：渲染器离线
            AIMessage(content="", tool_calls=[tool_call("observe_room", "o1", {"room_id": "open_public"})]),
            # Agent 又尝试一次观察：第二次离线 -> 触发停止
            AIMessage(content="", tool_calls=[tool_call("observe_room", "o2", {"room_id": "open_public"})]),
            AIMessage(content="不应到达：Agent 已停止"),
        ]

        def execute(name, args, call_id=None):
            if name == "set_design_work_type":
                return start_result(args["work_type"])
            if name == "update_scheme":
                return "修改scheme成功，新方案ID：v-offline"
            return "渲染器未在线：不能把文本当作视觉证据。请先打开实时场景并等待它注册当前 render session。"

        with patch("backend.agent_api.agent.graph.call_responses", side_effect=responses_side_effect(fake)), patch(
            "backend.agent_api.agent.graph.execute_tool", side_effect=execute
        ) as mocked:
            result = self.invoke_graph(
                build_graph(), [HumanMessage(content="开始完整设计")], thread_id="offline-test"
            )

        # 第二次离线失败后停止：最后一条消息必须是停止说明，而不是 Agent 继续
        self.assertEqual(result["messages"][-1].content, RENDERER_OFFLINE_STOPPED_MESSAGE)
        # 观察工具最多被调用 2 次（第 3 次及之后的 AIMessage 不应执行）
        observe_calls = [
            call for call in mocked.call_args_list if call.args and call.args[0] == "observe_room"
        ]
        self.assertLessEqual(len(observe_calls), 2)
        self.assertEqual(result["renderer_offline_strikes"], 2)

    def test_tool_attempt_hard_cap_stops_runaway_loop(self) -> None:
        """工具调用总数超过 MAX_TOOL_ATTEMPTS 后强制安全终止。

        回归：任何未知原因导致 Agent 无休止调用工具（死循环）时，
        必须在硬上限处停下，而不是无限烧 token。
        使用只读 load_scheme（不触发渲染器离线/写入门禁等其它停止条件），
        单独验证工具总数上限本身。
        """
        from backend.agent_api.agent.graph import (
            MAX_TOOL_ATTEMPTS,
            TOOL_ATTEMPT_EXHAUSTED_MESSAGE,
        )

        # 构造一个比上限多几轮的序列：每轮一个 load_scheme（成功返回，无副作用）
        fake = []
        for i in range(MAX_TOOL_ATTEMPTS + 3):
            fake.append(
                AIMessage(
                    content="",
                    tool_calls=[tool_call("load_scheme", f"l{i}")],
                )
            )
        # 收尾（不应到达）
        fake.append(AIMessage(content="不应到达：已在硬上限处停止"))

        def execute(name, args, call_id=None):
            if name == "load_scheme":
                return json.dumps({"scheme_id": "v1", "assignments": []}, ensure_ascii=False)
            raise AssertionError(f"unexpected tool: {name}")

        with patch("backend.agent_api.agent.graph.call_responses", side_effect=responses_side_effect(fake)), patch(
            "backend.agent_api.agent.graph.execute_tool", side_effect=execute
        ) as mocked:
            result = self.invoke_graph(
                build_graph(), [HumanMessage(content="开始")], thread_id="cap-test"
            )

        # 在硬上限处停止，而不是跑完整个序列
        self.assertEqual(result["messages"][-1].content, TOOL_ATTEMPT_EXHAUSTED_MESSAGE)
        self.assertGreaterEqual(result["tool_attempt_count"], MAX_TOOL_ATTEMPTS)
        # 实际执行的工具数不超过上限（第 61 次起被拦截为 TOOL_ATTEMPT_LIMIT_REACHED）
        executed = [
            call for call in mocked.call_args_list if call.args and call.args[0] == "load_scheme"
        ]
        self.assertLessEqual(len(executed), MAX_TOOL_ATTEMPTS)


if __name__ == "__main__":
    unittest.main()
