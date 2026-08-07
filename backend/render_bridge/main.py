"""Backend-owned render-task bridge for visual Agent tools.

The Agent submits an observation command here.  A browser which owns the
Three.js renderer long-polls for that command, captures the requested evidence,
and posts the result back.  The browser is deliberately an executor, never a
tool registry or decision maker.
"""

from __future__ import annotations

import argparse
import os
from typing import Any

from fastapi import FastAPI, HTTPException, Response
from fastapi.middleware.cors import CORSMiddleware

from .broker import AgentCommandRequest, BrowserResultRequest, RenderTaskBroker


def _cors_origins() -> list[str]:
    """从 CORS_ORIGINS env 读取白名单(逗号分隔);默认本机开发三源。"""
    raw = os.environ.get(
        "CORS_ORIGINS",
        "http://localhost:3000,http://127.0.0.1:3000,http://[::1]:3002",
    )
    return [origin.strip() for origin in raw.split(",") if origin.strip()]


broker = RenderTaskBroker()
app = FastAPI(title="House Design Render Bridge", version="0.1.0")
app.add_middleware(
    CORSMiddleware,
    allow_origins=_cors_origins(),
    allow_methods=["GET", "POST", "OPTIONS"],
    allow_headers=["content-type"],
)


@app.get("/health")
def health() -> dict[str, str]:
    return {"status": "ok"}


@app.get("/v1/render-sessions/{session_id}/status")
def session_status(session_id: str) -> dict:
    """查询会话在线状态,供渲染 worker / agent-api health 探活。"""
    return {"session_id": session_id, "online": broker.is_online(session_id)}


@app.post("/v1/render-sessions/{session_id}/heartbeat")
def heartbeat(session_id: str) -> dict[str, bool]:
    broker.heartbeat(session_id)
    return {"ok": True}


@app.get("/v1/render-sessions/{session_id}/commands", response_model=None)
def get_command(session_id: str):
    command = broker.next_command(session_id)
    if command is None:
        return Response(status_code=204)
    return {"id": command.id, "tool": command.tool, "args": command.args}


@app.post("/v1/render-sessions/{session_id}/commands/{command_id}/result")
def post_result(session_id: str, command_id: str, payload: BrowserResultRequest) -> dict[str, bool]:
    try:
        broker.resolve(session_id, command_id, payload)
    except KeyError as error:
        raise HTTPException(status_code=404, detail="unknown_render_command") from error
    except ValueError as error:
        raise HTTPException(status_code=409, detail=f"command_not_pending:{error}") from error
    return {"ok": True}


@app.post("/v1/render-sessions/{session_id}/commands")
def submit_command(session_id: str, request: AgentCommandRequest) -> dict[str, Any]:
    if not broker.is_online(session_id):
        raise HTTPException(status_code=503, detail="renderer_not_online")
    command = broker.submit(session_id, request)
    if command.state == "completed" and command.result is not None:
        return {"command_id": command.id, "status": "completed", "result": command.result}
    status_code = 504 if command.state == "timed_out" else 502
    raise HTTPException(status_code=status_code, detail=command.error or command.state)


if __name__ == "__main__":
    import uvicorn

    parser = argparse.ArgumentParser()
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=8765)
    args = parser.parse_args()
    uvicorn.run(app, host=args.host, port=args.port)
