"""会话管理:创建会话、读取历史、删除会话。

thread_id 即 LangGraph checkpoint 的 config["configurable"]["thread_id"],
由 SqliteSaver 持久化,进程重启后仍可恢复。
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Literal
from uuid import uuid4

from fastapi import APIRouter, HTTPException, Request
from pydantic import BaseModel, Field

from langchain_core.messages import AIMessage, HumanMessage, SystemMessage, ToolMessage

router = APIRouter()


class CreateSessionRequest(BaseModel):
    title: str | None = Field(default=None, max_length=120)
    mode: Literal["fresh", "branch", "continue"] = "fresh"
    source_design_run_id: str | None = None
    # 浏览器生成的随机 client_id,用于最小用户隔离:会话归属到创建它的浏览器。
    client_id: str | None = Field(default=None, min_length=8, max_length=128)


class CreateSessionResponse(BaseModel):
    thread_id: str
    created_at: str
    design_run_id: str
    design_mode: Literal["fresh", "branch", "continue"]
    current_version_id: str


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
def create_session(body: CreateSessionRequest, request: Request) -> CreateSessionResponse:
    thread_id = f"sess_{uuid4().hex}"
    created_at = datetime.now(timezone.utc).isoformat()
    manager = getattr(request.app.state, "design_runs", None)
    if manager is None:
        raise HTTPException(status_code=503, detail="design_run_manager_unavailable")

    try:
        if body.mode == "fresh":
            design_run = manager.create_fresh_run(body.title or "从零设计")
        elif body.mode == "branch":
            source_run_id = body.source_design_run_id or manager.active_run_id
            design_run = manager.create_branch(source_run_id, body.title or "当前方案分支")
        else:
            source_run_id = body.source_design_run_id or manager.active_run_id
            design_run = manager.activate(source_run_id)
        manager.bind_session(thread_id, design_run.run_id, body.mode, client_id=body.client_id)
    except KeyError as error:
        raise HTTPException(status_code=404, detail=str(error)) from error

    return CreateSessionResponse(
        thread_id=thread_id,
        created_at=created_at,
        design_run_id=design_run.run_id,
        design_mode=body.mode,
        current_version_id=design_run.current_version_id,
    )


@router.get("/sessions")
def list_sessions(client_id: str, request: Request) -> dict:
    """按浏览器 client_id 列出其会话(最小用户隔离)。client_id 必填。"""
    manager = getattr(request.app.state, "design_runs", None)
    if manager is None:
        raise HTTPException(status_code=503, detail="design_run_manager_unavailable")
    bindings = manager.list_client_sessions(client_id)
    return {
        "client_id": client_id,
        "sessions": [
            {
                "thread_id": binding.thread_id,
                "design_run_id": binding.design_run_id,
                "design_mode": binding.design_mode,
                "bound_at": binding.bound_at,
            }
            for binding in bindings
        ],
    }


def _require_ownership(manager, thread_id: str, client_id: str | None) -> None:
    """会话归属校验:已归属的会话必须由同一 client_id 访问,否则 403。

    无归属的历史绑定(迁移前旧会话)允许直接访问,但不进入任何列表。
    """
    try:
        manager.assert_client_owns(thread_id, client_id)
    except PermissionError as error:
        raise HTTPException(status_code=403, detail=str(error)) from error


@router.get("/sessions/{thread_id}/messages")
async def get_messages(thread_id: str, request: Request, client_id: str | None = None) -> dict:
    manager = getattr(request.app.state, "design_runs", None)
    if manager is not None:
        _require_ownership(manager, thread_id, client_id)
    graph = request.app.state.graph
    config = {"configurable": {"thread_id": thread_id}}
    state = await graph.aget_state(config)
    messages = list(state.values.get("messages", [])) if state.values else []
    binding = manager.get_session_binding(thread_id) if manager is not None else None
    design_run = manager.get_run(binding.design_run_id) if binding is not None else None
    return {
        "thread_id": thread_id,
        "design_run_id": binding.design_run_id if binding is not None else None,
        "design_mode": binding.design_mode if binding is not None else None,
        "current_version_id": design_run.current_version_id if design_run is not None else None,
        "messages": [_serialize_message(message) for message in messages],
    }


@router.delete("/sessions/{thread_id}")
async def delete_session(thread_id: str, request: Request, client_id: str | None = None) -> dict:
    manager = getattr(request.app.state, "design_runs", None)
    if manager is not None:
        _require_ownership(manager, thread_id, client_id)
    checkpointer = request.app.state.checkpointer
    try:
        await checkpointer.adelete_thread(thread_id)
    except Exception as error:  # noqa: BLE001
        raise HTTPException(status_code=404, detail=f"thread_not_found:{error}")
    if manager is not None:
        manager.unbind_session(thread_id)
    return {"ok": True}
