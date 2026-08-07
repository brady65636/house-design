"""后端统一配置:所有可配置项集中于此,环境变量覆盖默认值。

字段名 = 环境变量名(不区分大小写),例如 openai_proxy -> OPENAI_PROXY。
本地默认值保持当前 CLI 行为不变;生产部署通过 PaaS/容器 env 覆盖。
"""

from __future__ import annotations

from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict


# backend/agent_api/config.py 的父级父级父级 = 项目根目录(house design)
PROJECT_ROOT = Path(__file__).resolve().parents[2]


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=str(PROJECT_ROOT / ".env"),
        env_file_encoding="utf-8",
        extra="ignore",
    )

    # --- 模型 ---
    openai_api_key: str = ""
    openai_base_url: str = "https://api.openai.com/v1"
    # 本机代理 http://127.0.0.1:7892(写进 .env);生产不设该 env 即直连
    openai_proxy: str | None = None
    openai_model: str = "gpt-5.6-luna"
    reasoning_effort: str = "none"

    # --- 项目数据文件 ---
    scene_manifest_path: Path = PROJECT_ROOT / "scene_manifest.json"
    asset_manifest_path: Path = PROJECT_ROOT / "asset_manifest.json"
    asset_cards_path: Path = PROJECT_ROOT / "asset_cards.json"
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
