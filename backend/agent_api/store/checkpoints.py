"""SQLite checkpointer 接线:FastAPI lifespan 里创建共享 AsyncSqliteSaver。"""

from __future__ import annotations

from pathlib import Path

import aiosqlite
from langgraph.checkpoint.sqlite.aio import AsyncSqliteSaver


async def open_async_checkpointer(db_path: Path) -> AsyncSqliteSaver:
    """打开 SQLite 连接(开启 WAL + busy_timeout),返回共享 checkpointer。

    注意:aiosqlite 连接不能跨事件循环共享;必须在 lifespan 里创建并全局复用。
    首版强制 uvicorn 单 worker,避免多进程争写同一 sqlite 文件。
    后续升级 langgraph-checkpoint-postgres 时替换本模块即可。
    """
    conn = await aiosqlite.connect(str(db_path))
    await conn.execute("PRAGMA journal_mode=WAL")
    await conn.execute("PRAGMA busy_timeout=5000")
    saver = AsyncSqliteSaver(conn)
    await saver.setup()
    return saver
