"""FastAPI 应用工厂:组装 CORS、各 router 与 lifespan 生命周期。

lifespan 里完成三件事:
1. SchemeStore:按 Settings.scheme_path 构建并注入工具层(部署版先 seed);
2. SQLite checkpointer:创建共享 AsyncSqliteSaver(单 worker 强制);
3. LangGraph 图:绑定共享 checkpointer 构建一次,存到 app.state。

create_app 接受可选的 checkpointer / scheme_store 覆盖,供测试注入
临时 SQLite 与临时目录的 SchemeStore,避免污染真实数据。
"""

from __future__ import annotations

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import Depends, FastAPI
from fastapi.middleware.cors import CORSMiddleware
from langgraph.checkpoint.base import BaseCheckpointSaver

from .api import routes_chat, routes_health, routes_scheme, routes_sessions
from .api.deps import require_token
from .agent.graph import build_graph
from .config import PROJECT_ROOT, settings
from .scheme.seed import seed_scheme
from .scheme.store import SchemeStore
from .store.checkpoints import open_async_checkpointer
from .tools.tools import (
    ACTIVE_ASSET_MANIFEST,
    ACTIVE_SCENE_MANIFEST,
    get_scheme_store,
    set_scheme_store,
)


def create_app(
    *,
    checkpointer: BaseCheckpointSaver | None = None,
    scheme_store: SchemeStore | None = None,
    checkpoint_db_path: Path | None = None,
) -> FastAPI:
    @asynccontextmanager
    async def lifespan(app: FastAPI) -> AsyncIterator[None]:
        nonlocal checkpointer, scheme_store

        # 1) SchemeStore
        if scheme_store is None:
            if settings.scheme_data_dir is not None:
                seed_scheme(
                    PROJECT_ROOT / "viewer" / "public" / "current_scheme.json",
                    settings.scheme_path,
                )
            scheme_store = SchemeStore(
                settings.scheme_path,
                ACTIVE_SCENE_MANIFEST,
                ACTIVE_ASSET_MANIFEST,
            )
            scheme_store.load()
        set_scheme_store(scheme_store)

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
            conn = getattr(checkpointer, "conn", None)
            if conn is not None:
                await conn.close()
            set_scheme_store(None)

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
    app.include_router(routes_scheme.router, prefix="/api")
    return app


app = create_app()
