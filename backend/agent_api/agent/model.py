"""模型构建：按需构建并缓存 ChatOpenAI（测试可 monkeypatch 成假模型）。

代理地址从 Settings 读取，不再硬编码本地代理；生产不设 OPENAI_PROXY 即直连。
"""

from __future__ import annotations

import httpx
from langchain_openai import ChatOpenAI

from ..config import settings


_model: ChatOpenAI | None = None


def build_model() -> ChatOpenAI:
    """构建与升级前完全一致的模型，代理从 Settings 读取。"""
    kwargs = dict(
        api_key=settings.openai_api_key,
        base_url=settings.openai_base_url,
        model=settings.openai_model,
        reasoning_effort=settings.reasoning_effort,
    )
    if settings.openai_proxy:
        kwargs["http_client"] = httpx.Client(proxy=settings.openai_proxy)
    return ChatOpenAI(**kwargs)


def get_model() -> ChatOpenAI:
    """按需构建并缓存模型实例（测试可 monkeypatch 成假模型）。"""
    global _model
    if _model is None:
        _model = build_model()
    return _model
