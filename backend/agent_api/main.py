"""FastAPI 应用工厂:组装 CORS、各 router 与 lifespan 生命周期。

lifespan 里完成三件事:
1. DesignRunManager:首次导入旧 Scheme，并注入活动运行的 VersionedSchemeStore;
2. SQLite checkpointer:创建共享 AsyncSqliteSaver(单 worker 强制);
3. LangGraph 图:绑定共享 checkpointer 构建一次,存到 app.state。

create_app 接受可选的 checkpointer / scheme_store / design_run_manager 覆盖,
供测试注入临时 SQLite 与临时设计目录,避免污染真实数据。
"""

from __future__ import annotations

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
import logging
from pathlib import Path

from fastapi import Depends, FastAPI
from fastapi.middleware.cors import CORSMiddleware
from langgraph.checkpoint.base import BaseCheckpointSaver

from .api import routes_chat, routes_designs, routes_health, routes_scheme, routes_sessions
from .api.deps import require_token
from .agent.graph import build_graph
from .config import PROJECT_ROOT, settings
from .design_runs.manager import DesignRunManager
from .design_runs.runtime import set_design_run_manager
from .scheme.seed import seed_scheme
from .scheme.store import SchemeStore
from .store.checkpoints import open_async_checkpointer
from .telemetry import flush_langsmith
from .tools.tools import (
    ACTIVE_ASSET_MANIFEST,
    ACTIVE_SCENE_MANIFEST,
    get_scheme_store,
    set_scheme_store,
)


logger = logging.getLogger("uvicorn.error")


def create_app(
    *,
    checkpointer: BaseCheckpointSaver | None = None,
    scheme_store: SchemeStore | None = None,
    checkpoint_db_path: Path | None = None,
    design_run_manager: DesignRunManager | None = None,
) -> FastAPI:
    @asynccontextmanager
    async def lifespan(app: FastAPI) -> AsyncIterator[None]:
        nonlocal checkpointer, scheme_store, design_run_manager

        logger.info(
            "LLM config provider=%s base_url=%s model=%s key=%s proxy_enabled=%s",
            settings.llm_provider,
            settings.active_base_url,
            settings.active_model,
            settings.active_key_fingerprint,
            bool(settings.active_proxy),
        )
        logger.info(
            "LangSmith tracing=%s endpoint=%s project=%s workspace=%s key=%s",
            settings.langsmith_tracing,
            settings.langsmith_endpoint,
            settings.langsmith_project,
            settings.langsmith_workspace_id or "default",
            settings.langsmith_key_fingerprint,
        )

        # 1) Design Runs / SchemeStore
        if scheme_store is None:
            if settings.scheme_data_dir is not None:
                seed_scheme(
                    PROJECT_ROOT / "viewer" / "public" / "current_scheme.json",
                    settings.scheme_path,
                )
            if design_run_manager is None:
                design_run_manager = DesignRunManager(
                    settings.data_dir / "design_runs",
                    ACTIVE_SCENE_MANIFEST,
                    ACTIVE_ASSET_MANIFEST,
                    settings.scheme_path,
                )
                design_run_manager.initialize()
            scheme_store = design_run_manager.get_store(design_run_manager.active_run_id)
        set_scheme_store(scheme_store)
        set_design_run_manager(design_run_manager)
        app.state.design_runs = design_run_manager

        # 2) 会话 checkpointer
        if checkpointer is None:
            db_path = checkpoint_db_path or settings.checkpoint_db_path
            checkpointer = await open_async_checkpointer(db_path)

        # 3) 图(共享 checkpointer)
        app.state.graph = build_graph(checkpointer=checkpointer)
        app.state.checkpointer = checkpointer
        try:
            yield
        finally:
            try:
                flush_langsmith()
            except Exception as error:  # noqa: BLE001
                logger.warning("LangSmith trace flush failed during shutdown: %s", error)
            conn = getattr(checkpointer, "conn", None)
            if conn is not None:
                await conn.close()
            set_scheme_store(None)
            set_design_run_manager(None)

    app = FastAPI(
        title="House Design Agent API",
        version="0.1.0",
        lifespan=lifespan,
    )
    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.cors_origin_list,
        allow_methods=["GET", "POST", "DELETE", "OPTIONS"],
        allow_headers=["*"],
        allow_credentials=False,
    )

    app.include_router(routes_health.router, prefix="/api")
    # 会话与对话需要 token;/api/scheme 匿名只读(前端/渲染页直拉)
    app.include_router(
        routes_sessions.router, prefix="/api", dependencies=[Depends(require_token)]
    )
    app.include_router(
        routes_chat.router, prefix="/api", dependencies=[Depends(require_token)]
    )
    app.include_router(
        routes_designs.router, prefix="/api", dependencies=[Depends(require_token)]
    )
    app.include_router(routes_scheme.router, prefix="/api")
    return app


app = create_app()
