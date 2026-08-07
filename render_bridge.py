"""迁移 shim：真实实现在 backend/render_bridge/。

保留本文件仅为兼容旧 import（tests 与本地脚本）。新代码请直接
from backend.render_bridge import ...。
"""

from backend.render_bridge import *  # noqa: F401,F403
