"""SchemeStore:并发安全的当前方案存储,替代旧的模块级 CURRENT_SCHEME 单例。

基础类仍支持单一 Scheme 文件；生产运行由 VersionedSchemeStore 包装，按
Design Run 隔离并把每次成功写入保存为不可变版本。

并发修改用 RLock 串行化 read-modify-write;写盘用"临时文件 + os.replace"
原子替换,避免读者读到半截 JSON。

同一 Design Run 内并发修改仍以 RLock 串行化；跨运行互不覆盖。
"""

from __future__ import annotations

import json
import os
import threading
import time
from pathlib import Path

from pydantic import ValidationError

from .schema import PaintParameters, Scheme
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

    def update(self, target_id: str, asset_id: str, parameters: dict | None = None) -> str:
        """修改一个 target 的 Asset 与可选参数，执行 Validator 后原子写盘。"""
        with self._lock:
            current_scheme = Scheme.model_validate(self.get())

            target_found = False
            for assignment in current_scheme.assignments:
                if assignment.target.id == target_id:
                    assignment.asset_id = asset_id
                    assignment.parameters = PaintParameters.model_validate(parameters) if parameters is not None else None
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

            # 更新 scheme_id 以便前端检测变化；VersionedSchemeStore 会改用不可变版本 ID。
            scheme_dict = json.loads(current_scheme.model_dump_json())
            scheme_dict["scheme_id"] = self._new_scheme_id(scheme_dict)
            self._commit(scheme_dict, f"update:{target_id}:{asset_id}")
            self._current = scheme_dict
            return f"修改scheme成功，新方案ID：{scheme_dict['scheme_id']}"

    def replace(self, scheme_dict: dict, *, reason: str, title: str | None = None) -> dict:
        """Validate and atomically replace the complete Scheme, preserving version history."""
        with self._lock:
            candidate = json.loads(json.dumps(scheme_dict, ensure_ascii=False))
            if title:
                candidate["title"] = title
            candidate["scheme_id"] = self._new_scheme_id(candidate)
            model = Scheme.model_validate(candidate)
            errors = validate_scheme(model, self._scene_manifest, self._asset_manifest)
            if errors:
                raise ValueError(str(errors))
            candidate = json.loads(model.model_dump_json())
            self._commit(candidate, reason)
            self._current = candidate
            return candidate

    def _new_scheme_id(self, current: dict) -> str:
        base_id = current["scheme_id"].rsplit("_", 1)[0]
        return f"{base_id}_{int(time.time())}"

    def _commit(self, scheme_dict: dict, reason: str) -> None:
        del reason
        self._write_atomic(scheme_dict)

    def _write_atomic(self, scheme_dict: dict) -> None:
        """临时文件 + os.replace 原子替换,避免读者读到半截 JSON。"""
        self._path.parent.mkdir(parents=True, exist_ok=True)
        tmp = self._path.with_suffix(self._path.suffix + ".tmp")
        tmp.write_text(
            json.dumps(scheme_dict, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )
        os.replace(tmp, self._path)
