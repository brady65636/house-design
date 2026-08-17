"""模型构建：按需构建并缓存 ChatOpenAI（测试可 monkeypatch 成假模型）。

代理地址从 Settings 读取，不再硬编码本地代理；生产不设
HOUSE_DESIGN_OPENAI_PROXY / HOUSE_DESIGN_DASHSCOPE_PROXY 即直连。
Settings 会在构建客户端前阻止把凭据发送到非官方 API（OpenAI 只允许
api.openai.com，DashScope 只允许 dashscope.aliyuncs.com 兼容端点）。
"""

from __future__ import annotations

import httpx
from langchain_openai import ChatOpenAI

from ..config import settings


_model: ChatOpenAI | None = None
_critic_model: ChatOpenAI | None = None


def _http_clients(proxy: str | None) -> tuple[httpx.Client, httpx.AsyncClient]:
    """显式客户端：只信任项目专属代理，绝不继承系统 HTTP_PROXY/HTTPS_PROXY。"""
    return (
        httpx.Client(proxy=proxy, trust_env=False),
        httpx.AsyncClient(proxy=proxy, trust_env=False),
    )


def _build_openai_model() -> ChatOpenAI:
    if not settings.openai_api_key:
        raise RuntimeError(
            "HOUSE_DESIGN_OPENAI_API_KEY is required; generic OPENAI_API_KEY "
            "is intentionally ignored"
        )
    sync_client, async_client = _http_clients(settings.openai_proxy)
    return ChatOpenAI(
        api_key=settings.openai_api_key,
        base_url=settings.openai_base_url,
        model=settings.openai_model,
        reasoning_effort=settings.reasoning_effort,
        http_socket_options=(),
        http_client=sync_client,
        http_async_client=async_client,
    )


def _build_dashscope_model() -> ChatOpenAI:
    """阿里云百炼 OpenAI 兼容模式。不传 reasoning_effort(OpenAI 专用参数)。"""
    if not settings.dashscope_api_key:
        raise RuntimeError(
            "HOUSE_DESIGN_DASHSCOPE_API_KEY is required; generic "
            "DASHSCOPE_API_KEY / OPENAI_API_KEY are intentionally ignored"
        )
    sync_client, async_client = _http_clients(settings.dashscope_proxy)
    return ChatOpenAI(
        api_key=settings.dashscope_api_key,
        base_url=settings.dashscope_base_url,
        model=settings.dashscope_model,
        http_socket_options=(),
        http_client=sync_client,
        http_async_client=async_client,
    )


def _build_ark_model() -> ChatOpenAI:
    """火山方舟 Ark OpenAI 兼容模式(豆包 Seed 2.0 Lite 等,支持视觉与工具调用)。

    与 dashscope 分支一致：不传 reasoning_effort；国内直连默认无代理。
    """
    if not settings.ark_api_key:
        raise RuntimeError(
            "HOUSE_DESIGN_ARK_API_KEY is required; generic "
            "ARK_API_KEY / OPENAI_API_KEY are intentionally ignored"
        )
    sync_client, async_client = _http_clients(settings.ark_proxy)
    return ChatOpenAI(
        api_key=settings.ark_api_key,
        base_url=settings.ark_base_url,
        model=settings.ark_model,
        http_socket_options=(),
        http_client=sync_client,
        http_async_client=async_client,
    )


def build_model() -> ChatOpenAI:
    """使用已通过 provider/endpoint 安全校验的配置构建模型。"""
    if settings.llm_provider == "dashscope":
        return _build_dashscope_model()
    if settings.llm_provider == "ark":
        return _build_ark_model()
    return _build_openai_model()


def get_model() -> ChatOpenAI:
    """按需构建并缓存模型实例（测试可 monkeypatch 成假模型）。"""
    global _model
    if _model is None:
        _model = build_model()
    return _model


def get_critic_model() -> ChatOpenAI:
    """Return a separately cached model instance for independent design review."""
    global _critic_model
    if _critic_model is None:
        _critic_model = build_model()
    return _critic_model
