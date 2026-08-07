"""SSE 事件流:把 LangGraph astream 的两种 stream_mode 转成前端可消费的事件。

graph.astream(input, config, stream_mode=["messages", "updates"]) 产出
(mode, payload) 元组:
- "messages": (AIMessageChunk, metadata),用于 message_delta 增量;
- "updates": {node: state_update},用于 tool_call(agent 节点)与
  tool_result(tools 节点)。

事件序列:meta -> (message_delta / tool_call / tool_result 交错) -> done / error。
"""

from __future__ import annotations

import json
from collections.abc import AsyncIterator
from typing import Any
from uuid import uuid4

from fastapi.responses import StreamingResponse

from langchain_core.messages import AIMessage

# 工具结果文本截断上限,防止超大 JSON 打爆事件流
TOOL_RESULT_MAX_CHARS = 2000


def sse_line(event: str, data: dict[str, Any]) -> str:
    return f"event: {event}\ndata: {json.dumps(data, ensure_ascii=False)}\n\n"


async def _stream_agent_events(graph, config: dict, messages: list) -> AsyncIterator[str]:
    """把一次对话的流式输出序列化成 SSE 行。"""

    run_id = uuid4().hex[:12]
    thread_id = config["configurable"]["thread_id"]

    async def _yield(event: str, data: dict[str, Any]) -> str:
        return sse_line(event, data)

    yield await _yield("meta", {"run_id": run_id, "thread_id": thread_id})

    try:
        async for mode, payload in graph.astream(
            {"messages": messages},
            config,
            stream_mode=["messages", "updates"],
        ):
            if mode == "messages":
                message_chunk, metadata = payload
                if metadata.get("langgraph_node") == "agent":
                    content = message_chunk.content
                    if isinstance(content, str) and content:
                        yield await _yield(
                            "message_delta", {"run_id": run_id, "delta": content}
                        )
            elif mode == "updates":
                for node, update in payload.items():
                    if node == "agent":
                        for message in update.get("messages", []):
                            for call in getattr(message, "tool_calls", []) or []:
                                yield await _yield(
                                    "tool_call",
                                    {
                                        "run_id": run_id,
                                        "tool": call.get("name", ""),
                                        "args": call.get("args", {}),
                                        "tool_call_id": call.get("id", ""),
                                    },
                                )
                    elif node == "tools":
                        for message in update.get("messages", []):
                            content = message.content
                            if isinstance(content, list):
                                content = json.dumps(content, ensure_ascii=False)
                            else:
                                content = str(content)
                            yield await _yield(
                                "tool_result",
                                {
                                    "run_id": run_id,
                                    "tool_call_id": getattr(message, "tool_call_id", ""),
                                    "status": "ok",
                                    "summary": content[:TOOL_RESULT_MAX_CHARS],
                                },
                            )

        # 流结束后取最终完整回复
        final_state = await graph.aget_state(config)
        final_message = final_state.values["messages"][-1]
        reply = (
            final_message.content
            if isinstance(final_message, AIMessage)
            else str(final_message)
        )
        yield await _yield(
            "done", {"run_id": run_id, "thread_id": thread_id, "reply": reply}
        )
    except Exception as error:  # noqa: BLE001
        yield await _yield(
            "error",
            {
                "run_id": run_id,
                "type": type(error).__name__,
                "message": str(error),
            },
        )


def stream_sse_response(graph, config: dict, messages: list) -> StreamingResponse:
    """包装为 SSE StreamingResponse,附带反向代理友好的响应头。"""
    return StreamingResponse(
        _stream_agent_events(graph, config, messages),
        media_type="text/event-stream",
        headers={
            "X-Accel-Buffering": "no",
            "Cache-Control": "no-cache",
        },
    )
