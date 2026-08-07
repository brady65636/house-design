"""对话接口:普通 JSON 聊天(阶段2);SSE 流式在阶段3的 /chat/stream 提供。

thread_id 贯穿 LangGraph checkpoint;每一轮把 SystemMessage + 用户消息注入
图,由 checkpointer 自动维护跨轮上下文。
"""

from __future__ import annotations

from fastapi import APIRouter, Request
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, Field

from langchain_core.messages import AIMessage, HumanMessage

from ..agent.graph import build_initial_messages
from .sse import stream_sse_response

router = APIRouter()


class ChatRequest(BaseModel):
    thread_id: str = Field(min_length=1)
    message: str = Field(min_length=1)


class ChatResponse(BaseModel):
    thread_id: str
    reply: str
    message_count: int


@router.post("/chat", response_model=ChatResponse)
async def chat(request: Request, body: ChatRequest) -> ChatResponse:
    graph = request.app.state.graph
    config = {"configurable": {"thread_id": body.thread_id}}

    # System prompt 只在会话首轮注入一次;后续轮次只传用户消息,
    # 避免 checkpoint 里 system 重复追加。
    state = await graph.aget_state(config)
    existing = list(state.values.get("messages", [])) if state.values else []
    if existing:
        messages = [HumanMessage(content=body.message)]
    else:
        messages = [*build_initial_messages(), HumanMessage(content=body.message)]

    result = await graph.ainvoke({"messages": messages}, config=config)
    final_message = result["messages"][-1]
    reply = final_message.content if isinstance(final_message, AIMessage) else str(final_message)

    state = await graph.aget_state(config)
    message_count = len(state.values.get("messages", [])) if state.values else 0
    return ChatResponse(thread_id=body.thread_id, reply=reply, message_count=message_count)


@router.post("/chat/stream")
async def chat_stream(request: Request, body: ChatRequest) -> StreamingResponse:
    """SSE 流式对话:meta -> message_delta/tool_call/tool_result -> done/error。"""
    graph = request.app.state.graph
    config = {"configurable": {"thread_id": body.thread_id}}

    # 与 /chat 一致:system prompt 只在会话首轮注入一次
    state = await graph.aget_state(config)
    existing = list(state.values.get("messages", [])) if state.values else []
    if existing:
        messages = [HumanMessage(content=body.message)]
    else:
        messages = [*build_initial_messages(), HumanMessage(content=body.message)]

    return stream_sse_response(graph, config, messages)
