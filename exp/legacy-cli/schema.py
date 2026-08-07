"""迁移 shim：真实实现在 backend/agent_api/scheme/schema.py。

保留本文件仅为兼容旧 import（tests 与外部脚本）。新代码请直接
from backend.agent_api.scheme.schema import Scheme。
"""

from backend.agent_api.scheme.schema import *  # noqa: F401,F403
