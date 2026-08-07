"""首启 seed:把 viewer/public/current_scheme.json 拷贝到后端数据目录。

部署版通过 SCHEME_DATA_DIR 让后端拥有自己的方案副本,不再写 viewer/public。
"""

from __future__ import annotations

import shutil
from pathlib import Path


def seed_scheme(source: Path, target: Path) -> bool:
    """若 target 不存在,从 source 拷贝 seed;返回是否执行了拷贝。"""
    if target.exists():
        return False
    target.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(source, target)
    return True
