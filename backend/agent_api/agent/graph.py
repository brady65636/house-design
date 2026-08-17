"""Open agent loop with graph-owned Scheme-write and delivery gates."""

from __future__ import annotations

import json
import logging
from typing import Annotated, Literal, TypedDict

from langchain_core.messages import AIMessage, HumanMessage, ToolMessage
from langgraph.channels import UntrackedValue
from langgraph.checkpoint.memory import MemorySaver
from langgraph.config import get_stream_writer
from langgraph.graph import END, START, StateGraph
from langgraph.graph.message import add_messages

from ..tools.tools import (
    ACTIVE_SCENE_MANIFEST,
    VisualToolOutput,
    execute_tool,
    tools,
    visual_evidence_message,
)
from .critic import critic_verdict_from_result
from .prompt import build_initial_messages  # noqa: F401 (public re-export used by API)
from .responses_client import (
    call_responses,
    messages_to_input_items,
    tool_calls_to_ai_message,
)
from .visual_message_lifecycle import (
    build_ephemeral_visual_message,
    remove_ephemeral_visual_messages,
)

logger = logging.getLogger("uvicorn.error")


WorkType = Literal["NOT_STARTED", "LIGHT", "HEAVY"]
CriticVerdict = Literal[
    "NOT_REVIEWED", "PASS", "REVISE", "UNABLE_TO_JUDGE", "STALE"
]


class AgentState(TypedDict, total=False):
    # Only messages are checkpointed across invocations sharing a thread_id.
    messages: Annotated[list, add_messages]

    # Responses API 会话接力状态：与 messages 同生命周期，跨轮持久化。
    responses_prev_id: str | None
    responses_last_ai_id: str | None

    # All orchestration fields live only for the current graph invocation.
    design_run_id: Annotated[str, UntrackedValue]
    design_mode: Annotated[str, UntrackedValue]
    work_type: Annotated[WorkType, UntrackedValue]
    critic_verdict: Annotated[CriticVerdict, UntrackedValue]
    critic_reviewed_scheme_version: Annotated[str | None, UntrackedValue]
    critic_attempt_count: Annotated[int, UntrackedValue]
    critic_budget_exhausted: Annotated[bool, UntrackedValue]
    current_scheme_version: Annotated[str | None, UntrackedValue]
    modified_target_ids: Annotated[list[str], UntrackedValue]
    modified_room_ids: Annotated[list[str], UntrackedValue]
    evidence_room_ids: Annotated[list[str], UntrackedValue]
    home_evidence_ready: Annotated[bool, UntrackedValue]
    delivery_guard_attempts: Annotated[int, UntrackedValue]
    delivery_gate_locked: Annotated[bool, UntrackedValue]
    # 可靠性护栏：工具调用总数上限与渲染器离线连续失败次数（仅本次 invocation 有效）
    tool_attempt_count: Annotated[int, UntrackedValue]
    renderer_offline_strikes: Annotated[int, UntrackedValue]


LIGHT_MAX_DISTINCT_TARGETS = 2
LIGHT_MAX_ROOMS = 1
MAX_DELIVERY_GUARD_ATTEMPTS = 3
MAX_CRITIC_ATTEMPTS = 3
# 单次 graph invocation 的工具调用总数硬上限（防任何死循环烧 token）。
# 依据维度二 eval 20260814 权威批次：成功全屋设计最多 41 次调用，留 1.5 倍余量。
MAX_TOOL_ATTEMPTS = 60
# 渲染器离线（observe_room/observe_home_harmony 返回"渲染器未在线/不可达"）连续失败
# 达到该次数后停止自动重试，如实告知用户，而不是无限循环。
MAX_RENDERER_OFFLINE_STRIKES = 2
DELIVERY_BLOCKED_MESSAGE = (
    "当前设计尚未满足代码级交付条件，本轮不能作为完成结果交付。"
    "系统已阻止成功声明；需要继续完成实施、取得当前版本的有效视觉证据，"
    "并在完整设计或已进入 Critic 审查时取得新的 Critic PASS。"
)
CRITIC_BUDGET_EXHAUSTED_MESSAGE = (
    "Critic 已达到本次执行的 3 次审查上限，最新结果仍未通过。"
    "本次自动修订已停止，当前方案不能声明完成。"
    "请根据最后一次审查意见决定保留当前版本、调整设计方向，或在下一轮继续处理。"
)
RENDERER_OFFLINE_STOPPED_MESSAGE = (
    "渲染器（3D 视图会话）当前不在线，无法取得像素级视觉证据，"
    "本轮无法完成视觉验收。系统已停止自动重试。"
    "请打开或刷新 3D 视图页面等待渲染会话重新注册，然后让我继续，"
    "我会重新观察并完成剩余验证。"
)
TOOL_ATTEMPT_EXHAUSTED_MESSAGE = (
    "本轮执行已达到工具调用次数上限（60 次），系统已安全停止，"
    "避免因未知故障无限循环。当前已完成的 Scheme 修改会保留。"
    "请让我在新的一轮继续，或检查渲染会话/环境后重试。"
)
# Public compatibility alias retained for API/tests that imported the old name.
CRITIC_BLOCKED_MESSAGE = DELIVERY_BLOCKED_MESSAGE


def _target_room_index() -> dict[str, str]:
    index: dict[str, str] = {}
    spaces = [
        *ACTIVE_SCENE_MANIFEST.get("rooms", []),
        *ACTIVE_SCENE_MANIFEST.get("balconies", []),
    ]
    for space in spaces:
        room_id = space.get("id")
        if not isinstance(room_id, str):
            continue
        target_ids = [
            *space.get("wall_face_ids", []),
            *space.get("surface_ids", {}).values(),
        ]
        for target_id in target_ids:
            if isinstance(target_id, str):
                index[target_id] = room_id
    return index


TARGET_TO_ROOM = _target_room_index()


def agent_node(state: AgentState) -> dict:
    """让模型决定回答、提问或调用工具；通过 Responses API 接力 + 会话缓存。

    模型必须先看到工具注入的真实图片；只有调用成功返回后，才在同一
    state update 中删除这些已消费的临时视觉消息。调用抛异常时不删除，
    允许同一线程重试。普通用户消息不受影响。
    """

    messages = state["messages"]
    last_ai_id = state.get("responses_last_ai_id")
    prev_id = state.get("responses_prev_id")

    # 定位「本轮新增、需发送给模型」的消息增量：上一条 AI 消息之后的部分。
    if last_ai_id is None:
        delta = list(messages)
    else:
        delta = []
        seen = False
        for message in messages:
            if seen:
                delta.append(message)
            elif getattr(message, "id", None) == last_ai_id:
                seen = True
        if not seen:
            # checkpoint 恢复异常时退化为：只靠 prev_id 接力历史，发送当前可见的非 AI 增量。
            delta = [m for m in messages if not isinstance(m, AIMessage)]

    input_items = messages_to_input_items(
        delta, include_system=(prev_id is None)
    )

    if not input_items and prev_id is not None:
        # 极端情况：delta 只剩 AIMessage/SystemMessage（本轮无新的 user/tool 消息），
        # 但 Responses API 不接受空 input。发一个空文本 user 消息占位，保证请求合法。
        logger.warning(
            "[agent_node] empty input fallback: last_ai_id=%s prev_id=%s delta=%s",
            last_ai_id,
            prev_id,
            [type(m).__name__ for m in delta],
        )
        input_items = [{"role": "user", "content": [{"type": "input_text", "text": ""}]}]

    # 流式输出：把模型文本增量通过 LangGraph custom stream 实时推送，
    # SSE 层消费后转发为 message_delta，前端即可逐字渲染。
    writer = get_stream_writer()

    def _on_text_delta(delta: str) -> None:
        if writer is not None:
            writer({"event": "text_delta", "delta": delta})

    result = call_responses(
        input_items=input_items,
        previous_response_id=prev_id,
        tools=tools,
        on_text_delta=_on_text_delta,
    )
    ai_message = tool_calls_to_ai_message(
        result.text, result.tool_calls, result.response_id
    )

    removals = remove_ephemeral_visual_messages(messages)

    return {
        "messages": [*removals, ai_message],
        "responses_prev_id": result.response_id,
        "responses_last_ai_id": result.response_id,
    }


def _has_current_evidence(state: AgentState) -> bool:
    modified_rooms = set(state.get("modified_room_ids", []))
    evidence_rooms = set(state.get("evidence_room_ids", []))
    if not modified_rooms or not modified_rooms <= evidence_rooms:
        return False
    return len(modified_rooms) == 1 or state.get("home_evidence_ready", False)


def _critic_pass_matches_current_scheme(state: AgentState) -> bool:
    version = state.get("current_scheme_version")
    return (
        bool(version)
        and state.get("critic_verdict") == "PASS"
        and state.get("critic_reviewed_scheme_version") == version
    )


def delivery_block_reason(state: AgentState) -> str | None:
    work_type = state.get("work_type", "NOT_STARTED")
    if work_type == "NOT_STARTED":
        return None
    if not state.get("modified_target_ids"):
        return "IMPLEMENTATION_REQUIRED"
    if not _has_current_evidence(state):
        return "CURRENT_RENDER_EVIDENCE_REQUIRED"

    verdict = state.get("critic_verdict", "NOT_REVIEWED")
    if work_type == "LIGHT" and verdict == "NOT_REVIEWED":
        return None
    if _critic_pass_matches_current_scheme(state):
        return None
    return f"CRITIC_{verdict}"


def route_after_agent(state: AgentState) -> str:
    last = state["messages"][-1]
    if getattr(last, "tool_calls", None):
        return "tools"
    reason = delivery_block_reason(state)
    if reason is None:
        return "end"
    if state.get("delivery_guard_attempts", 0) >= MAX_DELIVERY_GUARD_ATTEMPTS:
        return "delivery_blocked"
    return "delivery_guard"


def delivery_guard_node(state: AgentState) -> dict:
    reason = delivery_block_reason(state) or "UNKNOWN"
    work_type = state.get("work_type", "NOT_STARTED")
    return {
        "messages": [
            HumanMessage(
                content=(
                    f"DELIVERY_GATE_BLOCKED: work_type={work_type}; reason={reason}. "
                    "Do not deliver or claim completion. Continue autonomously with the "
                    "required Scheme implementation, current-version render evidence, and "
                    "Critic re-review. LIGHT work may finish without Critic only when no "
                    "Critic review has been entered; HEAVY work always requires a current PASS."
                )
            )
        ],
        "delivery_guard_attempts": state.get("delivery_guard_attempts", 0) + 1,
        "delivery_gate_locked": True,
    }


def delivery_blocked_node(_state: AgentState) -> dict:
    return {
        "messages": [AIMessage(content=DELIVERY_BLOCKED_MESSAGE)],
        "delivery_gate_locked": True,
    }


def route_after_tools(state: AgentState) -> str:
    """After each tool batch, route to the appropriate next node.

    停止优先级（从硬到软）：
    1. 工具调用总数超过硬上限 -> tool_attempt_exhausted（防任何死循环烧 token）
    2. 渲染器离线连续失败达上限 -> renderer_offline_stopped（取证失败不无限重试）
    3. Critic 预算耗尽且未 PASS -> critic_budget_exhausted
    否则回 agent 继续。
    """
    if state.get("tool_attempt_count", 0) > MAX_TOOL_ATTEMPTS:
        return "tool_attempt_exhausted"
    if state.get("renderer_offline_strikes", 0) >= MAX_RENDERER_OFFLINE_STRIKES:
        return "renderer_offline_stopped"
    if (
        state.get("critic_attempt_count", 0) >= MAX_CRITIC_ATTEMPTS
        and state.get("critic_verdict") != "PASS"
    ):
        return "critic_budget_exhausted"
    return "agent"


def critic_budget_exhausted_node(_state: AgentState) -> dict:
    return {
        "messages": [AIMessage(content=CRITIC_BUDGET_EXHAUSTED_MESSAGE)],
        "critic_budget_exhausted": True,
        "delivery_gate_locked": True,
    }


def renderer_offline_stopped_node(_state: AgentState) -> dict:
    """渲染器离线达到上限：如实告知用户，停止自动重试，不做虚假成功。"""
    return {
        "messages": [AIMessage(content=RENDERER_OFFLINE_STOPPED_MESSAGE)],
        "delivery_gate_locked": True,
    }


def tool_attempt_exhausted_node(_state: AgentState) -> dict:
    """工具调用总数超过硬上限：安全终止本轮，保留已完成的修改。"""
    return {
        "messages": [AIMessage(content=TOOL_ATTEMPT_EXHAUSTED_MESSAGE)],
        "delivery_gate_locked": True,
    }


def _successful_scheme_update(result: object) -> bool:
    return isinstance(result, str) and result.startswith("修改scheme成功")


def _scheme_version_from_update(result: str) -> str | None:
    if "：" not in result:
        return None
    version = result.rsplit("：", 1)[-1].strip()
    return version or None


def _valid_work_type_request(result: object) -> bool:
    if not isinstance(result, str):
        return False
    try:
        payload = json.loads(result)
    except json.JSONDecodeError:
        return False
    return payload.get("status") == "WORK_TYPE_REQUEST_VALID"


def _apply_work_type_transition(current: WorkType, requested: WorkType) -> tuple[WorkType, str]:
    if current == requested:
        return current, "WORK_TYPE_ALREADY_SET"
    if current == "NOT_STARTED" and requested in {"LIGHT", "HEAVY"}:
        return requested, "WORK_TYPE_APPLIED"
    if current == "LIGHT" and requested == "HEAVY":
        return "HEAVY", "WORK_TYPE_PROMOTED"
    return current, "WORK_TYPE_DOWNGRADE_BLOCKED"


def _visual_receipt(result: VisualToolOutput) -> tuple[bool, str | None, str | None]:
    try:
        payload = json.loads(result.summary)
    except json.JSONDecodeError:
        return False, None, None
    if payload.get("modelEvidenceReady") is not True or not result.images:
        return False, None, None
    version = (payload.get("scheme") or {}).get("schemeId")
    room_id = (payload.get("room") or {}).get("id")
    return (
        True,
        version if isinstance(version, str) else None,
        room_id if isinstance(room_id, str) else None,
    )


def tools_node(state: AgentState) -> dict:
    """Execute tools while enforcing graph-owned write and delivery permissions."""

    last = state["messages"][-1]
    tool_messages: list[ToolMessage] = []
    visual_outputs: list[VisualToolOutput] = []

    work_type: WorkType = state.get("work_type", "NOT_STARTED")
    critic_verdict: CriticVerdict = state.get("critic_verdict", "NOT_REVIEWED")
    critic_attempt_count = state.get("critic_attempt_count", 0)
    critic_budget_exhausted = state.get("critic_budget_exhausted", False)
    reviewed_version = state.get("critic_reviewed_scheme_version")
    current_version = state.get("current_scheme_version")
    modified_targets = list(state.get("modified_target_ids", []))
    modified_rooms = list(state.get("modified_room_ids", []))
    evidence_rooms = list(state.get("evidence_room_ids", []))
    home_evidence_ready = state.get("home_evidence_ready", False)
    tool_attempt_count = state.get("tool_attempt_count", 0)
    renderer_offline_strikes = state.get("renderer_offline_strikes", 0)
    batch_names = [call.get("name") for call in last.tool_calls]
    starts_and_writes = (
        "set_design_work_type" in batch_names and "update_scheme" in batch_names
    )
    made_progress = False

    for call in last.tool_calls:
        name = call["name"]
        args = call.get("args", {})
        critic_call_blocked = False

        # 可靠性护栏 1：工具调用总数硬上限。达到后不再执行任何工具，
        # 直接为剩余调用生成安全停止说明（route_after_tools 会进入终止节点）。
        tool_attempt_count += 1
        if tool_attempt_count > MAX_TOOL_ATTEMPTS:
            result = (
                f"TOOL_ATTEMPT_LIMIT_REACHED：本轮工具调用已超过 {MAX_TOOL_ATTEMPTS} 次，"
                "系统已停止执行以避免死循环。请停止继续调用工具并结束本轮。"
            )
            content = result if not isinstance(result, VisualToolOutput) else result.summary
            tool_messages.append(ToolMessage(content=content, tool_call_id=call["id"]))
            continue

        try:
            if name == "ask_design_critic":
                if critic_attempt_count >= MAX_CRITIC_ATTEMPTS:
                    critic_call_blocked = True
                    critic_budget_exhausted = True
                    result = json.dumps(
                        {
                            "status": "blocked",
                            "error": "CRITIC_BUDGET_EXHAUSTED",
                            "max_attempts": MAX_CRITIC_ATTEMPTS,
                            "attempts": critic_attempt_count,
                            "last_verdict": critic_verdict,
                        },
                        ensure_ascii=False,
                    )
                else:
                    # 调用前递增：PASS/REVISE/UNABLE_TO_JUDGE、429、模型失败都消耗一次。
                    critic_attempt_count += 1
                    result = execute_tool(name, args, call.get("id"))
            elif name == "set_design_work_type":
                raw_result = execute_tool(name, args, call.get("id"))
                if _valid_work_type_request(raw_result):
                    requested = args.get("work_type")
                    if requested in {"LIGHT", "HEAVY"}:
                        next_type, status = _apply_work_type_transition(work_type, requested)
                        made_progress = made_progress or next_type != work_type
                        work_type = next_type
                        result: object = json.dumps(
                            {
                                "status": status,
                                "work_type": work_type,
                                "write_permission": work_type in {"LIGHT", "HEAVY"},
                            },
                            ensure_ascii=False,
                        )
                    else:
                        result = raw_result
                else:
                    result = raw_result
            elif name == "update_scheme" and starts_and_writes:
                result = (
                    "SCHEME_WRITE_BLOCKED：set_design_work_type 与 update_scheme "
                    "必须位于不同 Agent 工具轮次。当前写入未执行。"
                )
            elif name == "update_scheme" and work_type == "NOT_STARTED":
                result = (
                    "SCHEME_WRITE_BLOCKED：当前 work_type=NOT_STARTED。规划、询问和等待审批"
                    "阶段禁止修改 Scheme；请在用户批准后先单独设置 LIGHT 或 HEAVY。"
                )
            else:
                result = execute_tool(name, args, call.get("id"))
        except Exception as error:  # noqa: BLE001 - 闭合 tool-call：为失败工具生成 ToolMessage，绝不留下只有 AI tool-call、没有 ToolMessage 的 checkpoint
            result = json.dumps(
                {
                    "error": "TOOL_EXECUTION_FAILED",
                    "tool": name,
                    "message": str(error),
                },
                ensure_ascii=False,
            )

        content = result.summary if isinstance(result, VisualToolOutput) else result
        if not isinstance(content, str):
            content = json.dumps(content, ensure_ascii=False)
        tool_messages.append(ToolMessage(content=content, tool_call_id=call["id"]))

        if isinstance(result, VisualToolOutput) and result.images:
            visual_outputs.append(result)

        if name == "update_scheme" and _successful_scheme_update(result):
            target_id = args.get("target_id")
            if isinstance(target_id, str):
                modified_targets = list(dict.fromkeys([*modified_targets, target_id]))
                room_id = TARGET_TO_ROOM.get(target_id)
                if room_id:
                    modified_rooms = list(dict.fromkeys([*modified_rooms, room_id]))
            current_version = _scheme_version_from_update(result)
            evidence_rooms = []
            home_evidence_ready = False
            if critic_verdict != "NOT_REVIEWED":
                critic_verdict = "STALE"
                reviewed_version = None
            if (
                work_type == "LIGHT"
                and (
                    len(modified_targets) > LIGHT_MAX_DISTINCT_TARGETS
                    or len(modified_rooms) > LIGHT_MAX_ROOMS
                )
            ):
                work_type = "HEAVY"
            made_progress = True

        if name in {"observe_room", "observe_home_harmony"} and isinstance(
            result, VisualToolOutput
        ):
            ready, observed_version, observed_room = _visual_receipt(result)
            if ready and observed_version == current_version:
                if name == "observe_room" and observed_room:
                    evidence_rooms = list(
                        dict.fromkeys([*evidence_rooms, observed_room])
                    )
                elif name == "observe_home_harmony":
                    home_evidence_ready = True
                made_progress = True
                # 一次成功的像素级取证代表渲染器在线，清零离线连续失败计数。
                renderer_offline_strikes = 0
        elif name in {"observe_room", "observe_home_harmony"}:
            # 渲染器离线/不可达：观察返回的是字符串错误。连续失败达到上限后，
            # route_after_tools 会进入 renderer_offline_stopped 停止节点，
            # 而不是让 Agent 无限重试取证。
            content = result.summary if isinstance(result, VisualToolOutput) else result
            if isinstance(content, str) and (
                "渲染器未在线" in content or "渲染会话不可达" in content
            ):
                renderer_offline_strikes += 1

        if name == "ask_design_critic" and not critic_call_blocked:
            critic_verdict = critic_verdict_from_result(result)
            reviewed_version = current_version if critic_verdict == "PASS" else None
            made_progress = True

    messages: list = tool_messages
    if visual_outputs:
        messages.append(
            build_ephemeral_visual_message(
                visual_evidence_message(visual_outputs)["content"]
            )
        )

    next_state: AgentState = {
        "work_type": work_type,
        "critic_verdict": critic_verdict,
        "critic_reviewed_scheme_version": reviewed_version,
        "current_scheme_version": current_version,
        "modified_target_ids": modified_targets,
        "modified_room_ids": modified_rooms,
        "evidence_room_ids": evidence_rooms,
        "home_evidence_ready": home_evidence_ready,
        "critic_attempt_count": critic_attempt_count,
        "critic_budget_exhausted": critic_budget_exhausted,
        "tool_attempt_count": tool_attempt_count,
        "renderer_offline_strikes": renderer_offline_strikes,
    }
    next_state["delivery_gate_locked"] = delivery_block_reason(next_state) is not None
    next_state["delivery_guard_attempts"] = (
        0 if made_progress else state.get("delivery_guard_attempts", 0)
    )
    return {"messages": messages, **next_state}


def build_graph(checkpointer=None):
    builder = StateGraph(AgentState)
    builder.add_node("agent", agent_node)
    builder.add_node("tools", tools_node)
    builder.add_node("delivery_guard", delivery_guard_node)
    builder.add_node("delivery_blocked", delivery_blocked_node)
    builder.add_node("critic_budget_exhausted", critic_budget_exhausted_node)
    builder.add_node("renderer_offline_stopped", renderer_offline_stopped_node)
    builder.add_node("tool_attempt_exhausted", tool_attempt_exhausted_node)
    builder.add_edge(START, "agent")
    builder.add_conditional_edges(
        "agent",
        route_after_agent,
        {
            "tools": "tools",
            "delivery_guard": "delivery_guard",
            "delivery_blocked": "delivery_blocked",
            "end": END,
        },
    )
    builder.add_conditional_edges(
        "tools",
        route_after_tools,
        {
            "agent": "agent",
            "critic_budget_exhausted": "critic_budget_exhausted",
            "renderer_offline_stopped": "renderer_offline_stopped",
            "tool_attempt_exhausted": "tool_attempt_exhausted",
        },
    )
    builder.add_edge("delivery_guard", "agent")
    builder.add_edge("delivery_blocked", END)
    builder.add_edge("critic_budget_exhausted", END)
    builder.add_edge("renderer_offline_stopped", END)
    builder.add_edge("tool_attempt_exhausted", END)
    return builder.compile(checkpointer=checkpointer or MemorySaver())
