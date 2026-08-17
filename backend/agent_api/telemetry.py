"""Project-scoped LangSmith tracing for graph turns and manual tool execution."""

from __future__ import annotations

from collections.abc import Iterator
from contextlib import contextmanager
from functools import lru_cache
from typing import Any

import langsmith as ls
from langsmith import Client

from .config import settings


@lru_cache(maxsize=1)
def get_langsmith_client() -> Client | None:
    """Build one explicit client; generic LANGSMITH_* variables stay ignored."""
    if not settings.langsmith_tracing:
        return None
    return Client(
        api_key=settings.langsmith_api_key,
        api_url=settings.langsmith_endpoint,
        workspace_id=settings.langsmith_workspace_id,
    )


def build_graph_config(
    *,
    thread_id: str,
    design_run_id: str | None,
    design_mode: str,
    transport: str,
) -> dict[str, Any]:
    """Attach stable, non-secret dimensions to every LangGraph root trace."""
    return {
        "configurable": {"thread_id": thread_id},
        "run_name": "house-design-agent-turn",
        "tags": ["house-design-agent", design_mode, transport],
        "metadata": {
            "thread_id": thread_id,
            "design_run_id": design_run_id or "legacy",
            "design_mode": design_mode,
            "transport": transport,
            "llm_provider": settings.llm_provider,
            "model": settings.active_model,
        },
    }


@contextmanager
def langsmith_tracing_scope(
    *,
    thread_id: str,
    design_run_id: str | None,
    design_mode: str,
    transport: str,
) -> Iterator[None]:
    """Enable or explicitly disable tracing for one complete Agent turn."""
    with ls.tracing_context(
        enabled=settings.langsmith_tracing,
        client=get_langsmith_client(),
        project_name=settings.langsmith_project,
        tags=["house-design-agent", design_mode, transport],
        metadata={
            "thread_id": thread_id,
            "design_run_id": design_run_id or "legacy",
            "design_mode": design_mode,
            "transport": transport,
        },
    ):
        yield


@contextmanager
def langsmith_tool_span(
    tool_name: str, args: dict[str, Any], tool_call_id: str | None = None
) -> Iterator[Any | None]:
    """Expose each manually dispatched tool as its own LangSmith tool run.

    tool_call_id 关联 LangGraph 的 assistant tool-call id，让评估读取器能把
    LangSmith 里的工具 run 与 evidence_packet 里的 tool_calls 精确对齐。
    """
    if not settings.langsmith_tracing:
        yield None
        return
    metadata: dict[str, Any] = {"tool_name": tool_name}
    if tool_call_id:
        metadata["tool_call_id"] = tool_call_id
    with ls.trace(
        name=f"house-design-tool:{tool_name}",
        run_type="tool",
        inputs={"tool_name": tool_name, "args": args},
        project_name=settings.langsmith_project,
        client=get_langsmith_client(),
        metadata=metadata,
        tags=["house-design-tool", tool_name],
    ) as run:
        yield run


@contextmanager
def langsmith_llm_span() -> Iterator[Any | None]:
    """Expose each Responses API call as a LangSmith llm run for latency/token observability.

    迁移到 Responses API 后模型调用不再走 LangChain ChatOpenAI，LangSmith 不会自动
    生成 llm run；这里手动打一个，让延迟与 token 继续可观测。调用方在拿到 usage 后
    用 run.end(outputs=...) 写入 token，使 LangSmith UI 能按标准字段显示。
    """
    if not settings.langsmith_tracing:
        yield None
        return
    with ls.trace(
        name="house-design-llm",
        run_type="llm",
        inputs={},
        project_name=settings.langsmith_project,
        client=get_langsmith_client(),
        tags=["house-design-llm"],
    ) as run:
        yield run


def flush_langsmith() -> None:
    """Flush background trace batches during graceful application shutdown."""
    client = get_langsmith_client()
    if client is not None:
        client.flush()
