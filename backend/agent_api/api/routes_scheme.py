"""Scheme 只读接口:前端与渲染页面从 /api/scheme 匿名拉取当前方案。"""

from __future__ import annotations

from fastapi import APIRouter

from ..tools.tools import get_scheme_store

router = APIRouter()


@router.get("/scheme")
def get_scheme() -> dict:
    return get_scheme_store().get()


@router.get("/scheme/version")
def get_scheme_version() -> dict:
    return {"scheme_id": get_scheme_store().get()["scheme_id"]}
