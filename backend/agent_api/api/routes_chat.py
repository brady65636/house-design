"""对话接口:普通 JSON 聊天(阶段2);SSE 流式在阶段3的 /chat/stream 提供。

thread_id 贯穿 LangGraph checkpoint;每一轮把 SystemMessage + 用户消息注入
图,由 checkpointer 自动维护跨轮上下文。
"""

from __future__ import annotations

from fastapi import APIRouter, Request
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, Field

from langchain_core.messages import AIMessage, HumanMessage, SystemMessage

from ..agent.graph import build_initial_messages
from ..design_runs.runtime import design_run_context
from ..telemetry import build_graph_config, langsmith_tracing_scope
from .sse import stream_sse_response

router = APIRouter()


class ChatRequest(BaseModel):
    thread_id: str = Field(min_length=1)
    message: str = Field(min_length=1)


class ChatResponse(BaseModel):
    thread_id: str
    reply: str
    message_count: int
    design_run_id: str | None = None


def _resolve_design(request: Request, thread_id: str) -> tuple[str | None, str]:
    manager = getattr(request.app.state, "design_runs", None)
    if manager is None:
        return None, "continue"
    binding = manager.resolve_session(thread_id)
    return binding.design_run_id, binding.design_mode


def _run_context_message(design_mode: str) -> SystemMessage:
    if design_mode == "fresh":
        content = (
            "本对话是一次从零设计（fresh design run）。当前 Scheme 只是中性技术基线，"
            "不是需要继承的设计结论。请根据用户目标自主读取、探索、修改和验证，不要因为基线已有值"
            "而默认它已经得到用户认可。"
        )
    elif design_mode == "branch":
        content = "本对话是现有设计的独立分支；可以参考起点，但所有后续修改和版本只写入本分支。"
    else:
        content = "本对话继续同一个设计运行；应在该运行的当前版本上推进。"
    return SystemMessage(content=content)


@router.post("/chat", response_model=ChatResponse)
async def chat(request: Request, body: ChatRequest) -> ChatResponse:
    graph = request.app.state.graph
    design_run_id, design_mode = _resolve_design(request, body.thread_id)
    config = build_graph_config(
        thread_id=body.thread_id,
        design_run_id=design_run_id,
        design_mode=design_mode,
        transport="json",
    )

    # System prompt 只在会话首轮注入一次;后续轮次只传用户消息,
    # 避免 checkpoint 里 system 重复追加。
    with design_run_context(design_run_id), langsmith_tracing_scope(
        thread_id=body.thread_id,
        design_run_id=design_run_id,
        design_mode=design_mode,
        transport="json",
    ):
        state = await graph.aget_state(config)
        existing = list(state.values.get("messages", [])) if state.values else []
        if existing:
            messages = [HumanMessage(content=body.message)]
        else:
            messages = [
                *build_initial_messages(),
                *([_run_context_message(design_mode)] if design_run_id else []),
                HumanMessage(content=body.message),
            ]

        result = await graph.ainvoke(
            {
                "messages": messages,
                "design_run_id": design_run_id or "legacy",
                "design_mode": design_mode,
            },
            config=config,
        )
        final_message = result["messages"][-1]
        reply = final_message.content if isinstance(final_message, AIMessage) else str(final_message)

        state = await graph.aget_state(config)
        message_count = len(state.values.get("messages", [])) if state.values else 0
    return ChatResponse(
        thread_id=body.thread_id,
        reply=reply,
        message_count=message_count,
        design_run_id=design_run_id,
    )


@router.post("/chat/stream")
async def chat_stream(request: Request, body: ChatRequest) -> StreamingResponse:
    """SSE 流式对话:meta -> message_delta/tool_call/tool_result -> done/error。"""
    graph = request.app.state.graph
    design_run_id, design_mode = _resolve_design(request, body.thread_id)
    config = build_graph_config(
        thread_id=body.thread_id,
        design_run_id=design_run_id,
        design_mode=design_mode,
        transport="sse",
    )

    # 与 /chat 一致:system prompt 只在会话首轮注入一次
    state = await graph.aget_state(config)
    existing = list(state.values.get("messages", [])) if state.values else []
    if existing:
        messages = [HumanMessage(content=body.message)]
    else:
        messages = [
            *build_initial_messages(),
            *([_run_context_message(design_mode)] if design_run_id else []),
            HumanMessage(content=body.message),
        ]

    return stream_sse_response(
        graph,
        config,
        messages,
        design_run_id=design_run_id,
        design_mode=design_mode,
    )
