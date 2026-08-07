"""迁移 shim：真实实现在 backend/agent_api/prompt_context.py。

保留本文件仅为兼容旧 import（tests 与外部脚本）。新代码请直接
from backend.agent_api.prompt_context import build_system_prompt。
"""

from backend.agent_api.prompt_context import *  # noqa: F401,F403
