"""鉴权依赖:首版用简单 Bearer token(AGENT_API_TOKEN)。

demo 级鉴权,非安全认证;目标是防止公网 PaaS 上陌生人烧 OpenAI token。
None 表示关闭(仅本机开发)。GET /api/scheme 例外(只读、无密钥)。
"""

from __future__ import annotations

from fastapi import Depends, HTTPException
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer

from ..config import settings

_bearer = HTTPBearer(auto_error=False)


def require_token(
    credentials: HTTPAuthorizationCredentials | None = Depends(_bearer),
) -> None:
    if settings.agent_api_token is None:
        return
    if credentials is None or credentials.credentials != settings.agent_api_token:
        raise HTTPException(status_code=401, detail="invalid_or_missing_token")
