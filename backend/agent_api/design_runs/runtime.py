"""Runtime selection of the Design Run used by synchronous Agent tools."""

from __future__ import annotations

from contextlib import contextmanager
from contextvars import ContextVar
from collections.abc import Iterator

from .manager import DesignRunManager


_manager: DesignRunManager | None = None
_current_run_id: ContextVar[str | None] = ContextVar(
    "house_design_current_run_id",
    default=None,
)


def set_design_run_manager(manager: DesignRunManager | None) -> None:
    global _manager
    _manager = manager


def get_design_run_manager() -> DesignRunManager | None:
    return _manager


def get_current_design_run_id() -> str | None:
    return _current_run_id.get()


@contextmanager
def design_run_context(run_id: str | None) -> Iterator[None]:
    token = _current_run_id.set(run_id)
    try:
        yield
    finally:
        _current_run_id.reset(token)
