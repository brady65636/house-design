"""后端统一配置。

LLM 配置使用 ``HOUSE_DESIGN_*`` 专属环境变量，避免系统里为其他工具设置的
``OPENAI_*`` / ``DEEPSEEK_*`` 污染本项目。其余服务配置仍按字段名读取环境变量。
"""

from __future__ import annotations

from pathlib import Path
from typing import Literal
from urllib.parse import urlsplit

from pydantic import Field, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


# backend/agent_api/config.py 的父级父级父级 = 项目根目录(house design)
PROJECT_ROOT = Path(__file__).resolve().parents[2]

LANGSMITH_OFFICIAL_HOSTS = {
    "api.smith.langchain.com",
    "eu.api.smith.langchain.com",
    "apac.api.smith.langchain.com",
    "aws.api.smith.langchain.com",
}


def _is_official_endpoint(url: str, *, hostname: str, path: str) -> bool:
    """Strictly verify an official HTTPS endpoint: no port/credentials/query."""
    parsed = urlsplit(url.rstrip("/"))
    return (
        parsed.scheme.lower() == "https"
        and parsed.hostname == hostname
        and parsed.port is None
        and parsed.path == path
        and not parsed.query
        and not parsed.fragment
        and parsed.username is None
        and parsed.password is None
    )


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=str(PROJECT_ROOT / ".env"),
        env_file_encoding="utf-8",
        extra="ignore",
    )

    # --- 模型 ---
    # validation_alias 是刻意的安全边界：不接受通用 OPENAI_* / DASHSCOPE_*
    # 进程变量。provider 决定使用哪一组凭据；切换模型必须换 provider，
    # 不能通过替换 OpenAI Base URL 指向其他服务。
    llm_provider: Literal["openai", "dashscope", "ark"] = Field(
        default="openai",
        validation_alias="HOUSE_DESIGN_LLM_PROVIDER",
    )
    openai_api_key: str = Field(
        default="",
        validation_alias="HOUSE_DESIGN_OPENAI_API_KEY",
    )
    openai_base_url: str = Field(
        default="https://api.openai.com/v1",
        validation_alias="HOUSE_DESIGN_OPENAI_BASE_URL",
    )
    # 本机代理 http://127.0.0.1:7892(写进 .env);生产不设该 env 即直连
    openai_proxy: str | None = Field(
        default=None,
        validation_alias="HOUSE_DESIGN_OPENAI_PROXY",
    )
    openai_model: str = Field(
        default="gpt-5.6-luna",
        validation_alias="HOUSE_DESIGN_OPENAI_MODEL",
    )
    # 阿里云百炼 DashScope OpenAI 兼容模式。国内直连，一般不需要代理。
    dashscope_api_key: str = Field(
        default="",
        validation_alias="HOUSE_DESIGN_DASHSCOPE_API_KEY",
    )
    dashscope_base_url: str = Field(
        default="https://dashscope.aliyuncs.com/compatible-mode/v1",
        validation_alias="HOUSE_DESIGN_DASHSCOPE_BASE_URL",
    )
    dashscope_proxy: str | None = Field(
        default=None,
        validation_alias="HOUSE_DESIGN_DASHSCOPE_PROXY",
    )
    dashscope_model: str = Field(
        default="qwen3.7-plus",
        validation_alias="HOUSE_DESIGN_DASHSCOPE_MODEL",
    )
    reasoning_effort: str = Field(
        default="none",
        validation_alias="HOUSE_DESIGN_REASONING_EFFORT",
    )

    # 火山方舟 Ark：豆包 Seed 2.0 Lite 等 OpenAI 兼容模型(支持视觉与工具调用)。
    # 国内直连，一般不需要代理；与评估 grader 共用同一把 ark key。
    ark_api_key: str = Field(
        default="",
        validation_alias="HOUSE_DESIGN_ARK_API_KEY",
    )
    ark_base_url: str = Field(
        default="https://ark.cn-beijing.volces.com/api/v3",
        validation_alias="HOUSE_DESIGN_ARK_BASE_URL",
    )
    ark_proxy: str | None = Field(
        default=None,
        validation_alias="HOUSE_DESIGN_ARK_PROXY",
    )
    ark_model: str = Field(
        default="doubao-seed-2-0-lite-260428",
        validation_alias="HOUSE_DESIGN_ARK_MODEL",
    )

    # --- LangSmith 可观测性 ---
    # 与 LLM 凭据相同，刻意不读取通用 LANGSMITH_* / LANGCHAIN_* 环境变量。
    langsmith_tracing: bool = Field(
        default=False,
        validation_alias="HOUSE_DESIGN_LANGSMITH_TRACING",
    )
    langsmith_api_key: str = Field(
        default="",
        validation_alias="HOUSE_DESIGN_LANGSMITH_API_KEY",
    )
    langsmith_endpoint: str = Field(
        default="https://api.smith.langchain.com",
        validation_alias="HOUSE_DESIGN_LANGSMITH_ENDPOINT",
    )
    langsmith_project: str = Field(
        default="house-design-agent",
        min_length=1,
        validation_alias="HOUSE_DESIGN_LANGSMITH_PROJECT",
    )
    langsmith_workspace_id: str | None = Field(
        default=None,
        validation_alias="HOUSE_DESIGN_LANGSMITH_WORKSPACE_ID",
    )

    # --- 项目数据文件 ---
    scene_manifest_path: Path = PROJECT_ROOT / "scene_manifest.json"
    asset_manifest_path: Path = PROJECT_ROOT / "asset_manifest.json"
    asset_cards_path: Path = PROJECT_ROOT / "asset_cards.json"
    asset_filter_profiles_path: Path = PROJECT_ROOT / "asset_filter_profiles.json"
    design_md_path: Path = PROJECT_ROOT / "design.md"
    design_skill_path: Path = (
        PROJECT_ROOT / "skills" / "residential-aesthetic-design" / "SKILL.md"
    )

    # --- Scheme 存储 ---
    # 本机默认写回 viewer/public(与现有 CLI 行为一致);
    # 部署时设 SCHEME_DATA_DIR=/data,由后端 API 提供,前端从 /api/scheme 读取。
    scheme_data_dir: Path | None = None

    # --- 数据目录(会话 checkpoint、运行时文件) ---
    data_dir: Path = PROJECT_ROOT / "backend" / "data"

    # --- 服务 ---
    # 逗号分隔的 CORS 允许来源;Vercel 域名必须加入白名单
    cors_origins: str = (
        "http://localhost:3000,http://127.0.0.1:3000,http://[::1]:3002"
    )
    # 首版简单鉴权:Bearer token。None 表示关闭(仅本机开发)。
    agent_api_token: str | None = None

    # --- 渲染桥 ---
    render_bridge_url: str = "http://127.0.0.1:8765"
    render_session_id: str = "local-demo"

    @model_validator(mode="after")
    def validate_llm_endpoint(self) -> "Settings":
        """Validate the official OpenAI / DashScope and LangSmith boundaries."""
        if self.llm_provider == "openai" and not _is_official_endpoint(
            self.openai_base_url, hostname="api.openai.com", path="/v1"
        ):
            raise ValueError(
                "HOUSE_DESIGN_OPENAI_BASE_URL must be exactly "
                "https://api.openai.com/v1 when HOUSE_DESIGN_LLM_PROVIDER=openai"
            )
        if self.llm_provider == "openai":
            self.openai_base_url = "https://api.openai.com/v1"

        if self.llm_provider == "dashscope" and not _is_official_endpoint(
            self.dashscope_base_url,
            hostname="dashscope.aliyuncs.com",
            path="/compatible-mode/v1",
        ):
            raise ValueError(
                "HOUSE_DESIGN_DASHSCOPE_BASE_URL must be exactly "
                "https://dashscope.aliyuncs.com/compatible-mode/v1 when "
                "HOUSE_DESIGN_LLM_PROVIDER=dashscope"
            )
        if self.llm_provider == "dashscope":
            self.dashscope_base_url = "https://dashscope.aliyuncs.com/compatible-mode/v1"

        if self.llm_provider == "ark" and not _is_official_endpoint(
            self.ark_base_url,
            hostname="ark.cn-beijing.volces.com",
            path="/api/v3",
        ):
            raise ValueError(
                "HOUSE_DESIGN_ARK_BASE_URL must be exactly "
                "https://ark.cn-beijing.volces.com/api/v3 when "
                "HOUSE_DESIGN_LLM_PROVIDER=ark"
            )
        if self.llm_provider == "ark":
            self.ark_base_url = "https://ark.cn-beijing.volces.com/api/v3"

        langsmith = urlsplit(self.langsmith_endpoint.rstrip("/"))
        is_official_langsmith = (
            langsmith.scheme.lower() == "https"
            and langsmith.hostname in LANGSMITH_OFFICIAL_HOSTS
            and langsmith.port is None
            and langsmith.path in {"", "/"}
            and not langsmith.query
            and not langsmith.fragment
            and langsmith.username is None
            and langsmith.password is None
        )
        if not is_official_langsmith:
            raise ValueError(
                "HOUSE_DESIGN_LANGSMITH_ENDPOINT must be an official LangSmith "
                "HTTPS endpoint"
            )
        self.langsmith_endpoint = f"https://{langsmith.hostname}"
        if self.langsmith_tracing and not self.langsmith_api_key:
            raise ValueError(
                "HOUSE_DESIGN_LANGSMITH_API_KEY is required when "
                "HOUSE_DESIGN_LANGSMITH_TRACING=true"
            )
        return self

    @property
    def openai_key_fingerprint(self) -> str:
        """Return a log-safe credential fingerprint; never return the full key."""
        if not self.openai_api_key:
            return "missing"
        return f"****{self.openai_api_key[-4:]}"

    @property
    def dashscope_key_fingerprint(self) -> str:
        """Return a log-safe DashScope credential fingerprint."""
        if not self.dashscope_api_key:
            return "missing"
        return f"****{self.dashscope_api_key[-4:]}"

    @property
    def ark_key_fingerprint(self) -> str:
        """Return a log-safe Ark credential fingerprint."""
        if not self.ark_api_key:
            return "missing"
        return f"****{self.ark_api_key[-4:]}"

    # --- 当前 provider 的活动模型配置(日志 / health / telemetry 使用) ---
    @property
    def active_model(self) -> str:
        if self.llm_provider == "openai":
            return self.openai_model
        if self.llm_provider == "ark":
            return self.ark_model
        return self.dashscope_model

    @property
    def active_base_url(self) -> str:
        if self.llm_provider == "openai":
            return self.openai_base_url
        if self.llm_provider == "ark":
            return self.ark_base_url
        return self.dashscope_base_url

    @property
    def active_proxy(self) -> str | None:
        if self.llm_provider == "openai":
            return self.openai_proxy
        if self.llm_provider == "ark":
            return self.ark_proxy
        return self.dashscope_proxy

    @property
    def active_api_key(self) -> str:
        if self.llm_provider == "openai":
            return self.openai_api_key
        if self.llm_provider == "ark":
            return self.ark_api_key
        return self.dashscope_api_key

    @property
    def active_key_fingerprint(self) -> str:
        """Log-safe fingerprint of the active provider's key."""
        if not self.active_api_key:
            return "missing"
        return f"****{self.active_api_key[-4:]}"

    @property
    def langsmith_key_fingerprint(self) -> str:
        """Return a log-safe LangSmith credential fingerprint."""
        if not self.langsmith_api_key:
            return "missing"
        return f"****{self.langsmith_api_key[-4:]}"

    @property
    def scheme_path(self) -> Path:
        data_dir = self.scheme_data_dir or PROJECT_ROOT / "viewer" / "public"
        return data_dir / "current_scheme.json"

    @property
    def checkpoint_db_path(self) -> Path:
        return self.data_dir / "checkpoints.sqlite"

    @property
    def cors_origin_list(self) -> list[str]:
        return [origin.strip() for origin in self.cors_origins.split(",") if origin.strip()]


settings = Settings()
