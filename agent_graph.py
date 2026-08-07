"""迁移 shim：真实实现在 backend/agent_api/agent/graph.py。

保留本文件仅为兼容旧 import（agentloop CLI 与既有测试）。新代码请直接
from backend.agent_api.agent.graph import ...。
"""

from backend.agent_api.agent.graph import *  # noqa: F401,F403
