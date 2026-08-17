"""Scheme 只读接口:前端与渲染页面从 /api/scheme 匿名拉取当前方案。"""

from __future__ import annotations

from fastapi import APIRouter, HTTPException, Query, Request

from ..tools.tools import get_scheme_store

router = APIRouter()


def _resolve_store(request: Request, design_run_id: str | None):
    manager = getattr(request.app.state, "design_runs", None)
    if manager is None:
        return get_scheme_store()
    run_id = design_run_id or manager.active_run_id
    try:
        return manager.get_store(run_id)
    except KeyError as error:
        raise HTTPException(status_code=404, detail=str(error)) from error


@router.get("/scheme")
def get_scheme(
    request: Request,
    design_run_id: str | None = Query(default=None),
) -> dict:
    return _resolve_store(request, design_run_id).get()


@router.get("/scheme/version")
def get_scheme_version(
    request: Request,
    design_run_id: str | None = Query(default=None),
) -> dict:
    return {"scheme_id": _resolve_store(request, design_run_id).get()["scheme_id"]}
