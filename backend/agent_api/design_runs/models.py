"""Explicit contracts separating chat sessions from design workspaces."""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

from ..scheme.schema import Scheme


DesignMode = Literal["fresh", "branch", "imported"]
SessionDesignMode = Literal["fresh", "branch", "continue"]


class DesignRunMetadata(BaseModel):
    model_config = ConfigDict(extra="forbid")

    schema_version: Literal["1.0.0"] = "1.0.0"
    run_id: str = Field(min_length=1)
    house_id: str = Field(min_length=1)
    title: str = Field(min_length=1, max_length=120)
    mode: DesignMode
    base_version_id: str = Field(min_length=1)
    current_version_id: str = Field(min_length=1)
    source_run_id: str | None = None
    source_version_id: str | None = None
    created_at: str = Field(min_length=1)
    updated_at: str = Field(min_length=1)


class SchemeVersionRecord(BaseModel):
    model_config = ConfigDict(extra="forbid")

    schema_version: Literal["1.0.0"] = "1.0.0"
    version_id: str = Field(min_length=1)
    run_id: str = Field(min_length=1)
    parent_version_id: str | None = None
    created_at: str = Field(min_length=1)
    reason: str = Field(min_length=1, max_length=300)
    scheme: Scheme


class SessionBinding(BaseModel):
    model_config = ConfigDict(extra="forbid")

    thread_id: str = Field(min_length=1)
    design_run_id: str = Field(min_length=1)
    design_mode: SessionDesignMode = "continue"
    bound_at: str = Field(min_length=1)
    # 归属方:浏览器生成的随机 client_id(无登录体系下的最小用户隔离)。
    # None 表示历史绑定(8 月 7 日前的旧会话),不出现在任何 client 的列表里。
    client_id: str | None = None
