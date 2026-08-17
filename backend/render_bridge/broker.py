"""RenderTaskBroker:进程内任务队列。Agent 提交命令,浏览器会话消费并回传。

设计为"以后可换 Redis/消息队列"——部署版替换本类即可,Agent 工具契约不变。
"""

from __future__ import annotations

import threading
import time
import uuid
from dataclasses import dataclass, field
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field


CommandName = Literal["observe_room", "observe_home_harmony"]


class AgentCommandRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    tool: CommandName
    args: dict[str, Any] = Field(default_factory=dict)
    timeout_ms: int = Field(default=90_000, ge=5_000, le=180_000)


class BrowserResultRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    status: Literal["completed", "failed"]
    result: dict[str, Any] | None = None
    error: str | None = Field(default=None, max_length=800)


@dataclass
class PendingCommand:
    id: str
    session_id: str
    tool: CommandName
    args: dict[str, Any]
    created_at: float = field(default_factory=time.time)
    state: Literal["queued", "delivered", "completed", "failed", "timed_out"] = "queued"
    result: dict[str, Any] | None = None
    error: str | None = None


class RenderTaskBroker:
    """Small in-memory broker, intentionally replaceable by Redis/queue later."""

    def __init__(self) -> None:
        self._condition = threading.Condition()
        self._commands: dict[str, PendingCommand] = {}
        self._online_sessions: dict[str, float] = {}

    def heartbeat(self, session_id: str) -> None:
        with self._condition:
            self._online_sessions[session_id] = time.monotonic()
            self._condition.notify_all()

    def submit(self, session_id: str, request: AgentCommandRequest) -> PendingCommand:
        command = PendingCommand(
            id=str(uuid.uuid4()), session_id=session_id, tool=request.tool, args=request.args
        )
        deadline = time.monotonic() + request.timeout_ms / 1000
        with self._condition:
            self._commands[command.id] = command
            self._condition.notify_all()
            while command.state in {"queued", "delivered"}:
                remaining = deadline - time.monotonic()
                if remaining <= 0:
                    command.state = "timed_out"
                    command.error = "renderer_timeout"
                    break
                self._condition.wait(timeout=remaining)
        return command

    def next_command(self, session_id: str) -> PendingCommand | None:
        with self._condition:
            self._online_sessions[session_id] = time.monotonic()
            for command in self._commands.values():
                if command.session_id == session_id and command.state == "queued":
                    command.state = "delivered"
                    return command
        return None

    def resolve(self, session_id: str, command_id: str, payload: BrowserResultRequest) -> None:
        with self._condition:
            command = self._commands.get(command_id)
            if command is None or command.session_id != session_id:
                raise KeyError(command_id)
            if command.state not in {"queued", "delivered"}:
                raise ValueError(command.state)
            command.state = payload.status
            command.result = payload.result
            command.error = payload.error
            self._condition.notify_all()

    def is_online(self, session_id: str, freshness_seconds: float = 90) -> bool:
        # The viewer polls commands from a Web Worker every ~2s; next_command()
        # refreshes this timestamp. 90s tolerates OS sleep / brief network stalls
        # without hiding a truly dead session after its worker has stopped.
        with self._condition:
            last_seen = self._online_sessions.get(session_id)
            return last_seen is not None and time.monotonic() - last_seen <= freshness_seconds
