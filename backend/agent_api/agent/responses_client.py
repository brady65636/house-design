"""火山方舟 Responses API 客户端：用 previous_response_id 接力 + 会话缓存。

替代 LangChain ChatOpenAI（走 /chat/completions）的底层 HTTP 层。Chat Completions
在豆包 v1.6+ 上不再提供上下文缓存，而 Responses API 通过 store + caching=enabled +
previous_response_id 把重复历史前缀命中缓存，使多轮 Agent 循环的 token 成本从
O(N^2) 降为 O(N)。

本模块只负责 HTTP 请求、input/response 的协议转换与错误处理；状态（previous id、
已消费的 message 位置）由调用方（graph.py / critic.py）持有，避免多会话串线。
"""

from __future__ import annotations

import json
import logging
import time
from collections.abc import Callable
from dataclasses import dataclass
from typing import Any

import httpx
from langchain_core.messages import AIMessage, HumanMessage, SystemMessage, ToolMessage

from ..config import settings
from ..telemetry import langsmith_llm_span

logger = logging.getLogger("uvicorn.error")

# LLM 调用韧性：总超时 + 自动重试。
# 豆包 Responses API 从美东服务器跨洋调用、且上下文较大时，可能出现长时间只发
# SSE keep-alive 却不吐有效 token 的"假活"状态。httpx 的 timeout 是"每块读取"
# 粒度，无法限制整次调用的总时长，所以这里用 wall-clock deadline 强制总超时，
# 并对超时/连接层错误/429/5xx 做有限重试，避免 Agent 无限挂死。
MAX_LLM_ATTEMPTS = 3
LLM_TOTAL_TIMEOUT_SECONDS = 600.0
RETRY_BASE_DELAY_SECONDS = 5.0


def _retryable(error: Exception) -> bool:
    """判断错误是否值得重试：传输层错误(连接/超时/断连)或 429/5xx。"""
    if isinstance(error, httpx.RequestError):
        return True
    text = str(error)
    return any(code in text for code in ("429", "500", "502", "503", "504"))


def _sleep_before_retry(attempt: int) -> None:
    time.sleep(RETRY_BASE_DELAY_SECONDS * (2 ** (attempt - 1)))


@dataclass
class ResponsesResult:
    """一次 Responses API 调用的归一化结果。"""

    text: str
    tool_calls: list[dict[str, Any]]
    response_id: str
    usage: dict[str, Any] | None
    reasoning: str = ""


def _client() -> httpx.Client:
    return httpx.Client(proxy=settings.ark_proxy, trust_env=False)


def to_responses_tools(tools: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """把 Chat Completions 的工具定义转成 Responses API 的扁平 function 格式。

    Chat Completions: {"type":"function","function":{"name":...,"parameters":...}}
    Responses API:   {"type":"function","name":...,"parameters":...}
    """
    result: list[dict[str, Any]] = []
    for tool in tools:
        if tool.get("type") != "function":
            continue
        function = tool.get("function") or {}
        result.append(
            {
                "type": "function",
                "name": function.get("name"),
                "description": function.get("description"),
                "parameters": function.get("parameters"),
            }
        )
    return result


def _content_to_input_blocks(content: Any) -> list[dict[str, Any]]:
    """把 LangChain 消息 content（str 或 list）转成 Responses API 的 content 块。"""
    if isinstance(content, str):
        return [{"type": "input_text", "text": content}]
    blocks: list[dict[str, Any]] = []
    for part in content:
        if not isinstance(part, dict):
            continue
        ptype = part.get("type")
        if ptype == "text":
            blocks.append({"type": "input_text", "text": part.get("text", "")})
        elif ptype == "image_url":
            url = part.get("image_url") or {}
            raw = url.get("url") if isinstance(url, dict) else url
            blocks.append({"type": "input_image", "image_url": raw})
    return blocks


def messages_to_input_items(
    messages: list[Any], *, include_system: bool
) -> list[dict[str, Any]]:
    """把「本轮新增」的 LangChain 消息转成 Responses API 的 input items。

    - SystemMessage 仅在首轮（include_system=True，即无 previous_response_id）发送；
    - AIMessage 永不重发（它已在 previous 响应历史里）；
    - HumanMessage → user message；
    - ToolMessage → function_call_output。
    """
    items: list[dict[str, Any]] = []
    for message in messages:
        if isinstance(message, SystemMessage):
            if include_system:
                items.append(
                    {
                        "role": "system",
                        "content": _content_to_input_blocks(message.content),
                    }
                )
        elif isinstance(message, HumanMessage):
            items.append(
                {"role": "user", "content": _content_to_input_blocks(message.content)}
            )
        elif isinstance(message, ToolMessage):
            items.append(
                {
                    "type": "function_call_output",
                    "call_id": message.tool_call_id,
                    "output": message.content if isinstance(message.content, str) else json.dumps(message.content, ensure_ascii=False),
                }
            )
        # AIMessage 与其它类型跳过（不重发）
    return items


def _llm_span_outputs(result: ResponsesResult) -> dict[str, Any]:
    """把 Responses API 结果转成 LangSmith llm run 的标准 outputs 结构。"""
    usage = result.usage
    outputs: dict[str, Any] = {
        "response_id": result.response_id,
        "reasoning_summary": result.reasoning,
    }
    if isinstance(usage, dict):
        outputs["usage"] = usage
        outputs["llm_output"] = {
            "token_usage": {
                "prompt_tokens": usage.get("input_tokens"),
                "completion_tokens": usage.get("output_tokens"),
                "total_tokens": usage.get("total_tokens"),
            },
            "model_name": settings.ark_model,
        }
    return outputs


def _stream_parse_response(data: dict[str, Any], pending: dict[str, Any]) -> None:
    """增量解析一条流式 SSE 事件，累积到 pending 状态。

    支持事件（火山方舟/OpenAI Responses API 兼容格式）：
    - response.created                → 记录 response_id
    - response.output_item.added      → 记录 function_call 的 name/call_id（该事件携带完整 item）
    - response.output_text.delta      → 文本增量
    - response.output_text.done       → 该文本 item 完成（text 字段为完整文本，取增量）
    - response.function_call_arguments.delta → 工具参数增量
    - response.function_call_arguments.done  → 工具调用完成（只有 item_id/arguments，无 name/call_id）
    - response.output_item.done       → 完整 item（含 function_call 的 name/call_id/arguments，兜底）
    - response.completed              → 完整 response（含 usage）
    """
    etype = data.get("type")
    if etype == "response.created":
        response = data.get("response") or {}
        if response.get("id"):
            pending["response_id"] = response["id"]
        return
    if etype == "response.output_item.added":
        item = data.get("item") or {}
        if item.get("type") == "function_call" and item.get("id"):
            pending.setdefault("fc_meta", {})[item["id"]] = {
                "name": item.get("name") or "",
                "call_id": item.get("call_id") or "",
            }
        return
    if etype == "response.output_text.delta":
        delta = data.get("delta")
        if isinstance(delta, str) and delta:
            pending.setdefault("text_parts", []).append(delta)
        return
    if etype == "response.output_text.done":
        # done 事件自带完整 text；若 delta 事件已被消费，避免重复累积
        full = data.get("text")
        if isinstance(full, str) and full and not pending.get("text_parts"):
            pending["text_parts"] = [full]
        return
    if etype == "response.function_call_arguments.delta":
        delta = data.get("delta")
        if isinstance(delta, str) and delta:
            pending.setdefault("tool_args_parts", []).append(delta)
        return
    if etype == "response.function_call_arguments.done":
        # 该事件只有 item_id + arguments；name/call_id 来自 output_item.added
        item_id = data.get("item_id") or ""
        meta = pending.get("fc_meta", {}).get(item_id, {})
        name = meta.get("name") or ""
        call_id = meta.get("call_id") or ""
        arguments = "".join(pending.pop("tool_args_parts", []))
        if name:
            pending.setdefault("tool_calls", []).append(
                {
                    "name": name,
                    "args": _safe_loads(arguments),
                    "id": call_id,
                }
            )
        return
    if etype == "response.output_item.done":
        # 兜底：若 delta/done 事件顺序异常，用完整 item 的 name/arguments 补录
        item = data.get("item") or {}
        if item.get("type") == "function_call" and item.get("name"):
            item_id = item.get("id") or ""
            meta = pending.get("fc_meta", {}).get(item_id, {})
            name = meta.get("name") or item.get("name")
            call_id = meta.get("call_id") or item.get("call_id") or ""
            if name and not any(
                tool.get("id") == call_id for tool in pending.get("tool_calls", [])
            ):
                arguments = item.get("arguments")
                if isinstance(arguments, str):
                    arguments = _safe_loads(arguments)
                elif not isinstance(arguments, dict):
                    arguments = {}
                pending.setdefault("tool_calls", []).append(
                    {
                        "name": name,
                        "args": arguments,
                        "id": call_id,
                    }
                )
        return
    if etype == "response.completed":
        response = data.get("response") or {}
        if response.get("id"):
            pending["response_id"] = response["id"]
        if isinstance(response.get("usage"), dict):
            pending["usage"] = response["usage"]
        return


def _safe_loads(raw: str) -> Any:
    try:
        return json.loads(raw)
    except json.JSONDecodeError:
        return {}


def call_responses(
    *,
    input_items: list[dict[str, Any]],
    previous_response_id: str | None,
    tools: list[dict[str, Any]],
    on_text_delta: Callable[[str], None] | None = None,
) -> ResponsesResult:
    """调用 Responses API 并解析为 ResponsesResult。

    传入 on_text_delta 时使用流式（stream=true），逐段回调文本增量；
    否则与旧行为一致，一次返回完整结果。流式与 previous_response_id 接力 +
    会话缓存兼容（缓存键是服务端前缀，与传输方式无关）。
    """
    payload: dict[str, Any] = {
        "model": settings.ark_model,
        "input": input_items,
        "store": True,
        "caching": {"type": "enabled"},
    }
    if on_text_delta is not None:
        payload["stream"] = True
    if previous_response_id:
        payload["previous_response_id"] = previous_response_id
    else:
        # 工具定义只在首轮发送；接力轮次沿用缓存中的工具定义。
        payload["tools"] = to_responses_tools(tools)

    url = f"{settings.ark_base_url.rstrip('/')}/responses"
    if on_text_delta is None:
        return _call_responses_once(url, payload, previous_response_id)
    return _call_responses_streaming(url, payload, on_text_delta)


def _call_responses_once(
    url: str, payload: dict[str, Any], previous_response_id: str | None
) -> ResponsesResult:
    last_error: Exception | None = None
    for attempt in range(1, MAX_LLM_ATTEMPTS + 1):
        try:
            return _call_responses_once_attempt(url, payload, previous_response_id)
        except Exception as error:  # noqa: BLE001
            last_error = error
            if not _retryable(error) or attempt == MAX_LLM_ATTEMPTS:
                break
            logger.warning(
                "Responses API attempt %d failed: %s; retrying", attempt, error
            )
            _sleep_before_retry(attempt)
    raise last_error  # type: ignore[misc]


def _call_responses_once_attempt(
    url: str, payload: dict[str, Any], previous_response_id: str | None
) -> ResponsesResult:
    with langsmith_llm_span() as span:
        response = _client().post(
            url,
            headers={"Authorization": f"Bearer {settings.ark_api_key}"},
            json=payload,
            timeout=180.0,
        )
        if response.status_code != 200:
            raise RuntimeError(
                f"Responses API {response.status_code}: {response.text[:400]}"
            )
        data = response.json()
        result = _parse_response(data)
        if span is not None:
            span.end(outputs=_llm_span_outputs(result))
        if isinstance(result.usage, dict):
            logger.info("[responses_usage] %s", json.dumps(result.usage, ensure_ascii=False))
        return result


def _call_responses_streaming(
    url: str,
    payload: dict[str, Any],
    on_text_delta: Callable[[str], None],
) -> ResponsesResult:
    """流式调用：httpx.stream 逐行读 SSE，文本增量实时回调。

    事件行与 data 行配对解析；响应结束后把累积状态归一化为 ResponsesResult。
    带总超时与自动重试：豆包在跨洋/大上下文下可能长时间只发 keep-alive 不吐
    有效 token，httpx 的 read 超时是"每块"粒度、无法限制总时长，这里用
    wall-clock deadline 兜底，并对可重试错误做有限重试。
    """
    last_error: Exception | None = None
    for attempt in range(1, MAX_LLM_ATTEMPTS + 1):
        try:
            return _stream_once(url, payload, on_text_delta)
        except Exception as error:  # noqa: BLE001
            last_error = error
            if not _retryable(error) or attempt == MAX_LLM_ATTEMPTS:
                break
            logger.warning(
                "Responses API stream attempt %d failed: %s; retrying", attempt, error
            )
            _sleep_before_retry(attempt)
    raise last_error  # type: ignore[misc]


def _stream_once(
    url: str,
    payload: dict[str, Any],
    on_text_delta: Callable[[str], None],
) -> ResponsesResult:
    pending: dict[str, Any] = {
        "text_parts": [],
        "tool_calls": [],
        "tool_args_parts": [],
        "fc_meta": {},
    }
    deadline = time.monotonic() + LLM_TOTAL_TIMEOUT_SECONDS
    with langsmith_llm_span() as span:
        with _client().stream(
            "POST",
            url,
            headers={"Authorization": f"Bearer {settings.ark_api_key}"},
            json=payload,
            timeout=180.0,
        ) as response:
            if response.status_code != 200:
                raw = response.read().decode("utf-8", errors="replace")
                raise RuntimeError(f"Responses API {response.status_code}: {raw[:400]}")
            event: str | None = None
            for line in response.iter_lines():
                if time.monotonic() > deadline:
                    raise httpx.ReadTimeout(
                        f"Responses API total time limit exceeded "
                        f"({LLM_TOTAL_TIMEOUT_SECONDS:.0f}s)"
                    )
                if not line:
                    continue
                if line.startswith("event:"):
                    event = line[len("event:"):].strip()
                    continue
                if line.startswith("data:"):
                    raw = line[len("data:"):].strip()
                    if raw == "[DONE]":
                        break
                    try:
                        data = json.loads(raw)
                    except json.JSONDecodeError:
                        continue
                    if event == "error":
                        message = data.get("message") or data.get("code") or raw[:200]
                        raise RuntimeError(f"Responses API stream error: {message}")
                    _stream_parse_response(data, pending)
                    if event == "response.output_text.delta":
                        delta = data.get("delta")
                        if isinstance(delta, str) and delta:
                            on_text_delta(delta)

    text = "".join(pending.get("text_parts", []))
    tool_calls = pending.get("tool_calls", [])
    result = ResponsesResult(
        text=text,
        tool_calls=tool_calls,
        response_id=pending.get("response_id") or "",
        usage=pending.get("usage"),
    )
    if span is not None:
        span.end(outputs=_llm_span_outputs(result))
    if isinstance(result.usage, dict):
        logger.info("[responses_usage] %s", json.dumps(result.usage, ensure_ascii=False))
    return result


def _parse_response(data: dict[str, Any]) -> ResponsesResult:
    """把 Responses API 响应解析为 text + tool_calls + response_id + reasoning 摘要。"""
    text_parts: list[str] = []
    tool_calls: list[dict[str, Any]] = []
    reasoning_parts: list[str] = []
    for item in data.get("output", []) or []:
        itype = item.get("type")
        if itype == "message":
            for block in item.get("content", []) or []:
                if isinstance(block, dict) and block.get("type") in {
                    "output_text",
                    "text",
                }:
                    text_parts.append(block.get("text", ""))
        elif itype == "function_call":
            raw_args = item.get("arguments") or "{}"
            try:
                args = json.loads(raw_args)
            except json.JSONDecodeError:
                args = {}
            tool_calls.append(
                {
                    "name": item.get("name"),
                    "args": args,
                    "id": item.get("call_id"),
                }
            )
        elif itype == "reasoning":
            # 豆包默认只返回思考摘要(summary_text)，不返回完整思考链(CoT)。
            for block in item.get("summary", []) or []:
                if isinstance(block, dict) and block.get("text"):
                    reasoning_parts.append(block["text"])
    return ResponsesResult(
        text="".join(text_parts),
        tool_calls=tool_calls,
        response_id=data.get("id", ""),
        usage=data.get("usage"),
        reasoning="\n".join(reasoning_parts),
    )


def tool_calls_to_ai_message(
    text: str, tool_calls: list[dict[str, Any]], message_id: str
) -> AIMessage:
    """把 Responses API 的 tool_calls 归一化成 LangChain AIMessage（供 LangGraph 路由）。

    message_id 用本次响应的 response_id，保证跨轮稳定，供 agent_node 用它定位
    「本轮新增、需要发送给模型」的消息增量。
    """
    return AIMessage(
        content=text,
        tool_calls=tool_calls if tool_calls else [],
        id=message_id,
    )
