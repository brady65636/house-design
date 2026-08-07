"""会话管理:创建会话、读取历史、删除会话。

thread_id 即 LangGraph checkpoint 的 config["configurable"]["thread_id"],
由 SqliteSaver 持久化,进程重启后仍可恢复。
"""

from __future__ import annotations

from datetime import datetime, timezone
from uuid import uuid4

from fastapi import APIRouter, HTTPException, Request
from pydantic import BaseModel, Field

from langchain_core.messages import AIMessage, HumanMessage, SystemMessage, ToolMessage

router = APIRouter()


class CreateSessionRequest(BaseModel):
    title: str | None = Field(default=None, max_length=120)


class CreateSessionResponse(BaseModel):
    thread_id: str
    created_at: str


def _serialize_message(message) -> dict:
    """把 LangChain 消息序列化为 API 可读结构(剥离图片 data URL 以控制体积)。"""
    if isinstance(message, ToolMessage):
        content = message.content
        if isinstance(content, list):
            content = [block for block in content if block.get("type") != "image_url"]
        return {"role": "tool", "content": content, "tool_call_id": message.tool_call_id}
    if isinstance(message, AIMessage):
        return {
            "role": "assistant",
            "content": message.content,
            "tool_calls": list(message.tool_calls) if message.tool_calls else [],
        }
    if isinstance(message, HumanMessage):
        content = message.content
        if isinstance(content, list):
            content = [block for block in content if block.get("type") != "image_url"]
        return {"role": "user", "content": content}
    if isinstance(message, SystemMessage):
        return {"role": "system", "content": message.content}
    return {"role": "unknown", "content": str(message)}


@router.post("/sessions", response_model=CreateSessionResponse)
def create_session(body: CreateSessionRequest) -> CreateSessionResponse:
    thread_id = f"sess_{uuid4().hex}"
    created_at = datetime.now(timezone.utc).isoformat()
    return CreateSessionResponse(thread_id=thread_id, created_at=created_at)


@router.get("/sessions/{thread_id}/messages")
async def get_messages(thread_id: str, request: Request) -> dict:
    graph = request.app.state.graph
    config = {"configurable": {"thread_id": thread_id}}
    state = await graph.aget_state(config)
    messages = list(state.values.get("messages", [])) if state.values else []
    return {
        "thread_id": thread_id,
        "messages": [_serialize_message(message) for message in messages],
    }


@router.delete("/sessions/{thread_id}")
async def delete_session(thread_id: str, request: Request) -> dict:
    checkpointer = request.app.state.checkpointer
    try:
        await checkpointer.adelete_thread(thread_id)
    except Exception as error:  # noqa: BLE001
        raise HTTPException(status_code=404, detail=f"thread_not_found:{error}")
    return {"ok": True}
