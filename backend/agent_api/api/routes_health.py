"""健康检查:报告服务状态、模型与渲染桥可达性。"""

from __future__ import annotations

import httpx
from fastapi import APIRouter, Request

from ..config import settings

router = APIRouter()


@router.get("/health")
def health(request: Request) -> dict:
    bridge_reachable = False
    try:
        response = httpx.get(
            f"{settings.render_bridge_url}/health",
            timeout=2,
            trust_env=False,
        )
        bridge_reachable = response.status_code == 200
    except httpx.HTTPError:
        bridge_reachable = False

    return {
        "status": "ok",
        "llm_provider": settings.llm_provider,
        "model": settings.active_model,
        "langsmith_tracing": settings.langsmith_tracing,
        "langsmith_project": settings.langsmith_project,
        "bridge_url": settings.render_bridge_url,
        "bridge_reachable": bridge_reachable,
    }
