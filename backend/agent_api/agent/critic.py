"""Independent, read-only design Critic with its own open tool loop."""

from __future__ import annotations

import json
import re
from collections.abc import Callable
from typing import Any

from langchain_core.messages import AIMessage, HumanMessage, SystemMessage, ToolMessage

from .responses_client import (
    call_responses,
    messages_to_input_items,
    tool_calls_to_ai_message,
)
from .visual_criteria import numbered_visual_criteria
from .visual_message_lifecycle import (
    build_ephemeral_visual_message,
    filter_ephemeral_visual_messages,
)


CRITIC_VERDICTS = {"PASS", "REVISE", "UNABLE_TO_JUDGE"}
CRITIC_VERDICT_PATTERN = re.compile(
    r"(?im)^\s*CRITIC_VERDICT\s*:\s*(PASS|REVISE|UNABLE_TO_JUDGE)\s*$"
)

CRITIC_DELIVERY_GATE_INSTRUCTION = """
你现在拥有完整设计交付前的阻断权。最终审查必须把第一行严格写成以下三者之一：
CRITIC_VERDICT: PASS
CRITIC_VERDICT: REVISE
CRITIC_VERDICT: UNABLE_TO_JUDGE

只有所有适用视觉标准都有有效证据并且全部通过时才允许 PASS。任何适用项不通过时必须
REVISE；缺少足以判断最终效果的有效视觉证据时必须 UNABLE_TO_JUDGE。REVISE 和
UNABLE_TO_JUDGE 都会阻止主 Agent 交付，主 Agent 必须修改或补证后再次请你审查。
""".strip()


CRITIC_SYSTEM_PROMPT = f"""
你是独立的住宅硬装设计 Critic。你的职责不是接管设计或修改 Scheme，
而是以第二视角审查当前方案是否真正回应用户意图，并对最终交付行使阻断式质量门禁。

你可以自主使用提供的只读工具读取当前 Scheme、房间、资产卡和真实渲染。
没有工具证据时不要假装看过当前场景；证据不足时明确指出还缺什么。
只有 observe_* 返回 status=ready、evidenceLevel=pixel_verified_coverage，且消息中实际附带图片块时，
才能把图片当作视觉证据。incomplete_observation 和诊断元数据不构成视觉证明；此时应重试或写“无法判断”。
你没有任何写入工具，不得修改 Scheme，也不得命令系统进入某个阶段。

审查时逐条使用下面这 12 条大白话标准。只检查当前任务和现有证据能够覆盖的条目；
看不清或没有相应视角时写明“无法判断”，不要猜测：

{numbered_visual_criteria()}

{CRITIC_DELIVERY_GATE_INSTRUCTION}

对每条适用标准，只能给出“通过”“不通过”或“无法判断”。不适用于当前房间或任务的条目可以省略。
判断“不通过”时必须指出具体房间、表面或渲染视角；不能只重复标准原文。

最终答复应包含：
1. 总体判断；
2. 按重要性排列的具体发现及其证据；
3. 可执行的修改建议；
4. 仍未验证的事项。
不要为了显得严格而编造问题，也不要用空泛的“更高级”“更协调”代替具体判断。
""".strip()


def _tool_name(tool_definition: dict[str, Any]) -> str | None:
    function = tool_definition.get("function")
    if not isinstance(function, dict):
        return None
    name = function.get("name")
    return name if isinstance(name, str) else None


def _content_to_text(content: Any) -> str:
    if isinstance(content, str):
        return content
    if isinstance(content, list):
        text_parts = []
        for block in content:
            if isinstance(block, dict) and isinstance(block.get("text"), str):
                text_parts.append(block["text"])
        if text_parts:
            return "\n".join(text_parts)
    return json.dumps(content, ensure_ascii=False)


def normalize_critic_review(review: str) -> str:
    """Wrap the model review in a deterministic fail-closed verdict envelope."""

    match = CRITIC_VERDICT_PATTERN.search(review)
    verdict = match.group(1) if match else "UNABLE_TO_JUDGE"
    return json.dumps(
        {
            "verdict": verdict,
            "review": review,
            "machine_verdict_source": "explicit_marker" if match else "missing_marker_fail_closed",
        },
        ensure_ascii=False,
    )


def critic_verdict_from_result(result: Any) -> str:
    """Read a Critic tool result; malformed or missing verdicts fail closed."""

    payload = result
    if isinstance(result, str):
        try:
            payload = json.loads(result)
        except json.JSONDecodeError:
            return "UNABLE_TO_JUDGE"
    if not isinstance(payload, dict):
        return "UNABLE_TO_JUDGE"
    verdict = payload.get("verdict")
    return verdict if verdict in CRITIC_VERDICTS else "UNABLE_TO_JUDGE"


def _critic_failure_result(error: Exception) -> str:
    """结构化失败结果：Critic 模型调用失败时不产生任何门禁结论，门禁保持阻断。

    返回的 JSON 不包含 verdict 字段，因此 critic_verdict_from_result 会按
    fail-closed 解析为 UNABLE_TO_JUDGE，主 Agent 不会被误判为成功。
    """
    text = str(error).lower()
    error_type = (
        "rate_limit"
        if "rate_limit" in text or "rate limit" in text
        else "model_call_failed"
    )
    return json.dumps(
        {
            "status": "failed",
            "error_type": error_type,
            "retryable": True,
            "message": f"Critic model call failed; no verdict was produced. {text}",
        },
        ensure_ascii=False,
    )


def run_critic_review(
    review_request: str,
    *,
    design_context: str,
    house_context: str,
    tool_definitions: list[dict[str, Any]],
    execute_readonly_tool: Callable[[str, dict, str | None], Any],
    build_visual_message: Callable[[list[Any]], dict],
    max_turns: int = 8,
) -> str:
    """Run an independent review and return a machine-readable delivery verdict."""

    allowed_names = {
        name for definition in tool_definitions if (name := _tool_name(definition))
    }
    messages: list[Any] = [
        SystemMessage(
            content=(
                f"{CRITIC_SYSTEM_PROMPT}\n\n"
                f"【活动住宅摘要】\n{house_context}\n\n"
                f"【住宅硬装审美知识】\n{design_context}"
            )
        ),
        HumanMessage(content=f"请独立审查以下事项：\n{review_request}"),
    ]

    prev_id: str | None = None
    last_ai_id: str | None = None

    for _ in range(max_turns):
        # 定位本轮增量（上一条 AI 消息之后），用 Responses API 接力 + 会话缓存。
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
                delta = [m for m in messages if not isinstance(m, AIMessage)]

        input_items = messages_to_input_items(
            delta, include_system=(prev_id is None)
        )
        try:
            result = call_responses(
                input_items=input_items,
                previous_response_id=prev_id,
                tools=tool_definitions,
            )
        except Exception as error:  # noqa: BLE001 - 模型调用失败时 fail-closed，不产生门禁结论
            return _critic_failure_result(error)

        response = tool_calls_to_ai_message(
            result.text, result.tool_calls, result.response_id
        )
        prev_id = result.response_id
        last_ai_id = result.response_id

        # 模型成功消费后，立即从本地列表删除上一轮的临时视觉消息；否则在
        # 单次最多 max_turns 轮的本地循环里 Base64 图片会逐轮累积膨胀。
        messages = filter_ephemeral_visual_messages(messages)
        messages.append(response)

        tool_calls = getattr(response, "tool_calls", None) or []
        if not tool_calls:
            final_text = _content_to_text(getattr(response, "content", ""))
            return normalize_critic_review(
                final_text or "Critic 未返回有效审查意见。"
            )

        tool_messages: list[ToolMessage] = []
        visual_outputs: list[Any] = []
        for call in tool_calls:
            name = call.get("name")
            if name not in allowed_names:
                result: Any = "CRITIC_READ_ONLY：该工具不在 Critic 的只读工具集中。"
            else:
                try:
                    result = execute_readonly_tool(name, call.get("args", {}), call.get("id"))
                except Exception as error:  # noqa: BLE001 - 闭合只读 tool-call：失败也要有对应 ToolMessage，其他工具继续
                    result = json.dumps(
                        {
                            "error": "CRITIC_TOOL_FAILED",
                            "tool": name,
                            "message": str(error),
                        },
                        ensure_ascii=False,
                    )

            summary = getattr(result, "summary", result)
            if not isinstance(summary, str):
                summary = json.dumps(summary, ensure_ascii=False)
            tool_messages.append(
                ToolMessage(content=summary, tool_call_id=call.get("id", "critic-tool"))
            )
            if getattr(result, "images", None):
                visual_outputs.append(result)

        messages.extend(tool_messages)
        if visual_outputs:
            visual_message = build_visual_message(visual_outputs)
            messages.append(build_ephemeral_visual_message(visual_message["content"]))

    return normalize_critic_review(
        "Critic 在只读审查的调用上限内没有形成结论；主 Agent 必须缩小审查范围后重试。"
    )
