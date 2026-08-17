"""JSON-backed Design Runs with immutable Scheme snapshots.

The chat checkpoint and the design workspace intentionally have different lifecycles:
deleting a conversation removes its binding, not its design versions.
"""

from __future__ import annotations

import copy
import json
import os
import threading
from datetime import datetime, timezone
from pathlib import Path
from uuid import uuid4

from ..scheme.schema import Scheme
from ..scheme.store import SchemeStore
from ..scheme.validator import validate_scheme
from .models import DesignMode, DesignRunMetadata, SchemeVersionRecord, SessionBinding, SessionDesignMode


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _new_id(prefix: str) -> str:
    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S%f")
    return f"{prefix}_{stamp}_{uuid4().hex[:8]}"


def _read_json(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def _write_json_atomic(path: Path, payload: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(f".{path.name}.{uuid4().hex}.tmp")
    temporary.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    os.replace(temporary, path)


class VersionedSchemeStore(SchemeStore):
    """SchemeStore whose every successful write becomes an immutable version."""

    def __init__(self, manager: "DesignRunManager", run_id: str, path: Path) -> None:
        super().__init__(path, manager.scene_manifest, manager.asset_manifest)
        self._manager = manager
        self._run_id = run_id

    def _new_scheme_id(self, _current: dict) -> str:
        return _new_id("ver")

    def _commit(self, scheme_dict: dict, reason: str) -> None:
        self._manager.commit_version(self._run_id, scheme_dict, reason)


class DesignRunManager:
    """Own design runs, immutable versions, active run, and session bindings."""

    def __init__(
        self,
        root: Path,
        scene_manifest: dict,
        asset_manifest: dict,
        legacy_scheme_path: Path,
    ) -> None:
        self.root = root
        self.scene_manifest = scene_manifest
        self.asset_manifest = asset_manifest
        self.legacy_scheme_path = legacy_scheme_path
        self._index_path = root / "index.json"
        self._bindings_path = root / "session_bindings.json"
        self._lock = threading.RLock()
        self._stores: dict[str, VersionedSchemeStore] = {}

    def initialize(self) -> str:
        """Create the imported legacy run once and return the active run id."""
        with self._lock:
            if self._index_path.exists():
                index = _read_json(self._index_path)
                if "fallback_run_id" not in index:
                    imported = next(
                        (
                            run_id
                            for run_id in index.get("run_ids", [])
                            if self.get_run(run_id).mode == "imported"
                        ),
                        None,
                    )
                    index["fallback_run_id"] = imported or index["run_ids"][0]
                    _write_json_atomic(self._index_path, index)
                if not self._bindings_path.exists():
                    _write_json_atomic(
                        self._bindings_path,
                        {"schema_version": "1.0.0", "bindings": {}},
                    )
                return self.active_run_id
            self.root.mkdir(parents=True, exist_ok=True)
            if self.legacy_scheme_path.exists():
                scheme = _read_json(self.legacy_scheme_path)
                mode: DesignMode = "imported"
                title = "迁移前活动方案"
            else:
                scheme = self.build_neutral_baseline()
                mode = "fresh"
                title = "中性基线方案"
            metadata = self._create_run_from_scheme(
                scheme,
                mode=mode,
                title=title,
                source_run_id=None,
                source_version_id=None,
            )
            _write_json_atomic(
                self._index_path,
                {
                    "schema_version": "1.0.0",
                    "active_run_id": metadata.run_id,
                    "fallback_run_id": metadata.run_id,
                    "run_ids": [metadata.run_id],
                },
            )
            if not self._bindings_path.exists():
                _write_json_atomic(
                    self._bindings_path,
                    {"schema_version": "1.0.0", "bindings": {}},
                )
            return metadata.run_id

    @property
    def active_run_id(self) -> str:
        index = _read_json(self._index_path)
        return str(index["active_run_id"])

    @property
    def fallback_run_id(self) -> str:
        """Stable target for pre-migration threads that have no explicit binding."""
        index = _read_json(self._index_path)
        return str(index.get("fallback_run_id") or index["run_ids"][0])

    def build_neutral_baseline(self) -> dict:
        assets = {
            item["id"]: item
            for item in self.asset_manifest.get("assets", [])
            if isinstance(item.get("id"), str)
        }
        assignments: list[dict] = []
        for target in self.scene_manifest.get("design_targets", []):
            asset_id = target.get("default_asset_id")
            asset = assets.get(asset_id)
            if asset is None:
                raise ValueError(
                    f"neutral baseline target {target.get('id')} has unknown default asset {asset_id}"
                )
            assignment = {
                "target": {"kind": target["kind"], "id": target["id"]},
                "asset_id": asset_id,
            }
            if asset.get("category") == "wall_paint" and asset.get("parameterized") is True:
                parameter_schema = asset.get("parameter_schema", {})
                assignment["parameters"] = {
                    "lightness": parameter_schema.get("lightness", {}).get("default", "light"),
                    "saturation": parameter_schema.get("saturation", {}).get("default", 1.0),
                    "finish": parameter_schema.get("finish", {}).get("default", "matte"),
                }
            assignments.append(assignment)
        baseline = {
            "schema_version": "1.0.0",
            "scheme_id": "neutral_baseline",
            "title": "中性基线方案",
            "assignments": assignments,
        }
        model = Scheme.model_validate(baseline)
        errors = validate_scheme(model, self.scene_manifest, self.asset_manifest)
        if errors:
            raise ValueError(f"neutral baseline is invalid: {errors}")
        return json.loads(model.model_dump_json())

    def create_fresh_run(self, title: str = "从零设计") -> DesignRunMetadata:
        with self._lock:
            metadata = self._create_run_from_scheme(
                self.build_neutral_baseline(),
                mode="fresh",
                title=title,
                source_run_id=None,
                source_version_id=None,
            )
            self._register_and_activate(metadata.run_id)
            return metadata

    def create_branch(
        self,
        source_run_id: str,
        title: str = "当前方案分支",
    ) -> DesignRunMetadata:
        with self._lock:
            source = self.get_run(source_run_id)
            scheme = copy.deepcopy(self.get_store(source_run_id).get())
            metadata = self._create_run_from_scheme(
                scheme,
                mode="branch",
                title=title,
                source_run_id=source_run_id,
                source_version_id=source.current_version_id,
            )
            self._register_and_activate(metadata.run_id)
            return metadata

    def _create_run_from_scheme(
        self,
        scheme: dict,
        *,
        mode: DesignMode,
        title: str,
        source_run_id: str | None,
        source_version_id: str | None,
    ) -> DesignRunMetadata:
        run_id = _new_id("run")
        version_id = _new_id("ver")
        created_at = _now()
        scheme = copy.deepcopy(scheme)
        scheme["scheme_id"] = version_id
        scheme["title"] = title
        model = Scheme.model_validate(scheme)
        errors = validate_scheme(model, self.scene_manifest, self.asset_manifest)
        if errors:
            raise ValueError(f"cannot create design run from invalid scheme: {errors}")
        scheme = json.loads(model.model_dump_json())
        metadata = DesignRunMetadata(
            run_id=run_id,
            house_id=str(self.scene_manifest.get("house_id", "unknown_house")),
            title=title,
            mode=mode,
            base_version_id=version_id,
            current_version_id=version_id,
            source_run_id=source_run_id,
            source_version_id=source_version_id,
            created_at=created_at,
            updated_at=created_at,
        )
        run_dir = self.root / run_id
        record = SchemeVersionRecord(
            version_id=version_id,
            run_id=run_id,
            parent_version_id=source_version_id,
            created_at=created_at,
            reason=f"create:{mode}",
            scheme=scheme,
        )
        _write_json_atomic(run_dir / "versions" / f"{version_id}.json", record.model_dump(mode="json"))
        _write_json_atomic(run_dir / "head.json", scheme)
        _write_json_atomic(run_dir / "metadata.json", metadata.model_dump(mode="json"))
        return metadata

    def _register_and_activate(self, run_id: str) -> None:
        index = _read_json(self._index_path)
        run_ids = list(index.get("run_ids", []))
        if run_id not in run_ids:
            run_ids.append(run_id)
        index["run_ids"] = run_ids
        index["active_run_id"] = run_id
        _write_json_atomic(self._index_path, index)

    def activate(self, run_id: str) -> DesignRunMetadata:
        with self._lock:
            metadata = self.get_run(run_id)
            self._register_and_activate(run_id)
            return metadata

    def get_run(self, run_id: str) -> DesignRunMetadata:
        path = self.root / run_id / "metadata.json"
        if not path.exists():
            raise KeyError(f"unknown_design_run:{run_id}")
        return DesignRunMetadata.model_validate(_read_json(path))

    def list_runs(self) -> list[DesignRunMetadata]:
        index = _read_json(self._index_path)
        runs = [self.get_run(run_id) for run_id in index.get("run_ids", [])]
        return sorted(runs, key=lambda item: item.created_at, reverse=True)

    def get_store(self, run_id: str) -> VersionedSchemeStore:
        with self._lock:
            self.get_run(run_id)
            store = self._stores.get(run_id)
            if store is None:
                store = VersionedSchemeStore(self, run_id, self.root / run_id / "head.json")
                store.load()
                self._stores[run_id] = store
            return store

    def commit_version(self, run_id: str, scheme: dict, reason: str) -> None:
        with self._lock:
            metadata = self.get_run(run_id)
            version_id = str(scheme["scheme_id"])
            record = SchemeVersionRecord(
                version_id=version_id,
                run_id=run_id,
                parent_version_id=metadata.current_version_id,
                created_at=_now(),
                reason=reason,
                scheme=scheme,
            )
            run_dir = self.root / run_id
            version_path = run_dir / "versions" / f"{version_id}.json"
            if version_path.exists():
                raise ValueError(f"immutable version already exists: {version_id}")
            _write_json_atomic(version_path, record.model_dump(mode="json"))
            _write_json_atomic(run_dir / "head.json", scheme)
            updated = metadata.model_copy(
                update={"current_version_id": version_id, "updated_at": record.created_at}
            )
            _write_json_atomic(run_dir / "metadata.json", updated.model_dump(mode="json"))

    def list_versions(self, run_id: str) -> list[dict]:
        self.get_run(run_id)
        records = []
        for path in (self.root / run_id / "versions").glob("*.json"):
            record = SchemeVersionRecord.model_validate(_read_json(path))
            records.append(record.model_dump(mode="json", exclude={"scheme"}))
        return sorted(records, key=lambda item: item["created_at"], reverse=True)

    def get_version(self, run_id: str, version_id: str) -> SchemeVersionRecord:
        path = self.root / run_id / "versions" / f"{version_id}.json"
        if not path.exists():
            raise KeyError(f"unknown_scheme_version:{run_id}:{version_id}")
        return SchemeVersionRecord.model_validate(_read_json(path))

    def restore_version(self, run_id: str, version_id: str) -> dict:
        source = self.get_version(run_id, version_id)
        restored = source.scheme.model_dump(mode="json")
        return self.get_store(run_id).replace(
            restored,
            reason=f"restore:{version_id}",
            title=f"恢复版本 {version_id[-12:]}",
        )

    def bind_session(
        self,
        thread_id: str,
        run_id: str,
        design_mode: SessionDesignMode = "continue",
        client_id: str | None = None,
    ) -> SessionBinding:
        with self._lock:
            self.get_run(run_id)
            payload = _read_json(self._bindings_path)
            binding = SessionBinding(
                thread_id=thread_id,
                design_run_id=run_id,
                design_mode=design_mode,
                bound_at=_now(),
                client_id=client_id,
            )
            payload.setdefault("bindings", {})[thread_id] = binding.model_dump(mode="json")
            _write_json_atomic(self._bindings_path, payload)
            return binding

    def resolve_session(self, thread_id: str) -> SessionBinding:
        with self._lock:
            payload = _read_json(self._bindings_path)
            raw = payload.get("bindings", {}).get(thread_id)
            if raw:
                return SessionBinding.model_validate(raw)
            return self.bind_session(thread_id, self.fallback_run_id)

    def get_session_binding(self, thread_id: str) -> SessionBinding | None:
        """只读查询绑定,不存在时返回 None(不创建新绑定)。"""
        with self._lock:
            payload = _read_json(self._bindings_path)
            raw = payload.get("bindings", {}).get(thread_id)
            return SessionBinding.model_validate(raw) if raw else None

    def list_client_sessions(self, client_id: str) -> list[SessionBinding]:
        """返回属于该 client_id 的全部会话绑定,按绑定时间倒序。"""
        with self._lock:
            payload = _read_json(self._bindings_path)
            bindings = [
                SessionBinding.model_validate(raw)
                for raw in payload.get("bindings", {}).values()
                if raw and raw.get("client_id") == client_id
            ]
            return sorted(bindings, key=lambda item: item.bound_at, reverse=True)

    def assert_client_owns(self, thread_id: str, client_id: str | None) -> None:
        """读取/删除会话前校验归属。

        已绑定 client_id 的会话必须由同一 client_id 访问;无归属的历史绑定
        (迁移前旧会话)允许直接访问,但它们永不出现在任何 client 的列表里,
        隔离在列表层完成,不破坏 /api/chat 直连读历史的既有行为。
        """
        with self._lock:
            payload = _read_json(self._bindings_path)
            raw = payload.get("bindings", {}).get(thread_id)
            if raw is None:
                return  # 无绑定的游离 thread,由调用方按不存在处理
            owner = raw.get("client_id")
            if owner is not None and owner != client_id:
                raise PermissionError(f"session_not_owned:{thread_id}")

    def unbind_session(self, thread_id: str) -> None:
        with self._lock:
            payload = _read_json(self._bindings_path)
            payload.setdefault("bindings", {}).pop(thread_id, None)
            _write_json_atomic(self._bindings_path, payload)
