"""SchemeStore:并发安全的当前方案存储,替代旧的模块级 CURRENT_SCHEME 单例。

产品事实是一套住宅、一个 live Scheme、一个共享 3D 场景,所以不按会话隔离
(否则会出现多个互相冲突的方案版本,破坏"改方案→viewer 实时更新"的闭环)。

并发修改用 RLock 串行化 read-modify-write;写盘用"临时文件 + os.replace"
原子替换,避免读者读到半截 JSON。

取舍:并发改同一方案是"后写覆盖先写",无版本回滚。Demo 可接受,后续可演进
为 per-project Scheme + 版本/撤销(Level 8 话题)。
"""

from __future__ import annotations

import json
import os
import threading
import time
from pathlib import Path

from pydantic import ValidationError

from .schema import Scheme
from .validator import validate_scheme


def read_json(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


class SchemeStore:
    """线程安全的 Scheme 存储:内存副本 + 原子写盘。"""

    def __init__(
        self,
        path: Path,
        scene_manifest: dict,
        asset_manifest: dict,
    ) -> None:
        self._path = path
        self._scene_manifest = scene_manifest
        self._asset_manifest = asset_manifest
        self._lock = threading.RLock()
        self._current: dict | None = None

    @property
    def path(self) -> Path:
        return self._path

    def load(self) -> dict:
        """启动时把磁盘 Scheme 读入内存,返回当前方案。"""
        with self._lock:
            self._current = read_json(self._path)
            return self._current

    def get(self) -> dict:
        """返回当前内存中的完整 Scheme(惰性首次读盘)。"""
        with self._lock:
            if self._current is None:
                self._current = read_json(self._path)
            return self._current

    def update(self, target_id: str, asset_id: str) -> str:
        """修改一个 target 的 asset_id,执行 Validator,原子写盘并更新内存。"""
        with self._lock:
            current_scheme = Scheme.model_validate(self.get())

            target_found = False
            for assignment in current_scheme.assignments:
                if assignment.target.id == target_id:
                    assignment.asset_id = asset_id
                    target_found = True
                    break

            if not target_found:
                return "该目标不存在于当前 Scheme，请检查输入"

            try:
                current_scheme = Scheme.model_validate(current_scheme.model_dump())
            except ValidationError as error:
                return str(error.errors())

            errors = validate_scheme(
                current_scheme,
                self._scene_manifest,
                self._asset_manifest,
            )
            if errors:
                return str(errors)

            # 更新 scheme_id 以便前端检测变化
            scheme_dict = json.loads(current_scheme.model_dump_json())
            base_id = scheme_dict["scheme_id"].rsplit("_", 1)[0]
            scheme_dict["scheme_id"] = f"{base_id}_{int(time.time())}"
            self._write_atomic(scheme_dict)
            self._current = scheme_dict
            return f"修改scheme成功，新方案ID：{scheme_dict['scheme_id']}"

    def _write_atomic(self, scheme_dict: dict) -> None:
        """临时文件 + os.replace 原子替换,避免读者读到半截 JSON。"""
        self._path.parent.mkdir(parents=True, exist_ok=True)
        tmp = self._path.with_suffix(self._path.suffix + ".tmp")
        tmp.write_text(
            json.dumps(scheme_dict, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )
        os.replace(tmp, self._path)
