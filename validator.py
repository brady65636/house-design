"""迁移 shim：真实实现在 backend/agent_api/scheme/validator.py。

保留本文件仅为兼容旧 import（tests 与外部脚本）。新代码请直接
from backend.agent_api.scheme.validator import validate_scheme。
"""

from backend.agent_api.scheme.validator import *  # noqa: F401,F403
