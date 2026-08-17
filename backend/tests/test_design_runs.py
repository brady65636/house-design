"""Design Run isolation and immutable Scheme version history."""

from __future__ import annotations

import json
from pathlib import Path
from fastapi.testclient import TestClient

from backend.agent_api.design_runs.manager import DesignRunManager
from backend.agent_api.main import create_app
from backend.agent_api.scheme.schema import Scheme
from backend.agent_api.scheme.validator import validate_scheme


PROJECT_ROOT = Path(__file__).resolve().parents[2]


def _load_json(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def _manager(tmp_path: Path) -> DesignRunManager:
    legacy = tmp_path / "current_scheme.json"
    legacy.write_text(
        (PROJECT_ROOT / "viewer" / "public" / "current_scheme.json").read_text(
            encoding="utf-8"
        ),
        encoding="utf-8",
    )
    manager = DesignRunManager(
        tmp_path / "design_runs",
        _load_json(PROJECT_ROOT / "scene_manifest.json"),
        _load_json(PROJECT_ROOT / "asset_manifest.json"),
        legacy,
    )
    manager.initialize()
    return manager


def _paint_parameters() -> dict:
    return {"lightness": "light", "saturation": 0.85, "finish": "eggshell"}


def test_fresh_run_starts_from_complete_valid_neutral_baseline(tmp_path: Path) -> None:
    manager = _manager(tmp_path)
    fresh = manager.create_fresh_run()
    scheme = manager.get_store(fresh.run_id).get()

    targets = manager.scene_manifest["design_targets"]
    assert fresh.mode == "fresh"
    assert fresh.source_run_id is None
    assert len(scheme["assignments"]) == len(targets)
    assert {item["target"]["id"] for item in scheme["assignments"]} == {
        item["id"] for item in targets
    }
    model = Scheme.model_validate(scheme)
    assert validate_scheme(model, manager.scene_manifest, manager.asset_manifest) == []


def test_fresh_and_branch_writes_are_isolated(tmp_path: Path) -> None:
    manager = _manager(tmp_path)
    imported_id = manager.list_runs()[-1].run_id
    imported_before = json.loads(json.dumps(manager.get_store(imported_id).get()))
    fresh = manager.create_fresh_run()

    result = manager.get_store(fresh.run_id).update(
        "wall_face_real4_010", "paint_greige_01", _paint_parameters()
    )
    assert result.startswith("修改scheme成功")
    assert manager.get_store(imported_id).get() == imported_before

    branch = manager.create_branch(fresh.run_id)
    branch_before = json.loads(json.dumps(manager.get_store(branch.run_id).get()))
    assert branch.source_run_id == fresh.run_id
    assert branch_before["assignments"] == manager.get_store(fresh.run_id).get()["assignments"]

    manager.get_store(branch.run_id).update(
        "wall_face_real4_010", "paint_warm_white_01", _paint_parameters()
    )
    assert manager.get_store(branch.run_id).get()["scheme_id"] != branch_before["scheme_id"]
    assert manager.get_store(fresh.run_id).get()["assignments"] == branch_before["assignments"]


def test_versions_are_immutable_and_restore_creates_a_new_version(tmp_path: Path) -> None:
    manager = _manager(tmp_path)
    fresh = manager.create_fresh_run()
    initial_version = fresh.current_version_id
    initial_record = manager.get_version(fresh.run_id, initial_version)

    manager.get_store(fresh.run_id).update(
        "wall_face_real4_010", "paint_greige_01", _paint_parameters()
    )
    changed_version = manager.get_run(fresh.run_id).current_version_id
    assert changed_version != initial_version
    assert len(manager.list_versions(fresh.run_id)) == 2
    assert manager.get_version(fresh.run_id, initial_version) == initial_record

    restored = manager.restore_version(fresh.run_id, initial_version)
    restored_version = manager.get_run(fresh.run_id).current_version_id
    assert restored_version not in {initial_version, changed_version}
    assert restored["assignments"] == initial_record.scheme.model_dump(mode="json")["assignments"]
    assert len(manager.list_versions(fresh.run_id)) == 3


def test_session_binding_records_mode_without_owning_design_lifecycle(tmp_path: Path) -> None:
    manager = _manager(tmp_path)
    migration_run_id = manager.fallback_run_id
    fresh = manager.create_fresh_run()
    binding = manager.bind_session("thread-fresh", fresh.run_id, "fresh", client_id="client_aaa")

    assert manager.resolve_session("thread-fresh") == binding
    assert binding.design_mode == "fresh"
    assert binding.client_id == "client_aaa"
    manager.unbind_session("thread-fresh")
    rebound = manager.resolve_session("thread-fresh")
    assert rebound.design_mode == "continue"
    assert rebound.design_run_id == migration_run_id
    assert manager.get_run(fresh.run_id).run_id == fresh.run_id


def test_client_session_isolation(tmp_path: Path) -> None:
    """client_id 列表隔离:只返回创建它的浏览器会话;跨 client 读取被拒。"""
    manager = _manager(tmp_path)
    app = create_app(
        checkpoint_db_path=tmp_path / "checkpoints.sqlite",
        design_run_manager=manager,
    )

    with TestClient(app) as client:
        a = client.post("/api/sessions", json={"client_id": "client_aaa"}).json()
        b = client.post("/api/sessions", json={"client_id": "client_bbb"}).json()
        legacy = client.post("/api/sessions", json={}).json()  # 无 client_id 的历史绑定

        # 各自列表只含自己的会话
        list_a = client.get("/api/sessions", params={"client_id": "client_aaa"}).json()
        list_b = client.get("/api/sessions", params={"client_id": "client_bbb"}).json()
        assert [s["thread_id"] for s in list_a["sessions"]] == [a["thread_id"]]
        assert [s["thread_id"] for s in list_b["sessions"]] == [b["thread_id"]]
        # 无归属的历史会话不出现在任何列表
        assert legacy["thread_id"] not in {s["thread_id"] for s in list_a["sessions"]}
        assert legacy["thread_id"] not in {s["thread_id"] for s in list_b["sessions"]}

        # 跨 client 读取被 403 拒绝
        denied = client.get(
            f"/api/sessions/{a['thread_id']}/messages",
            params={"client_id": "client_bbb"},
        )
        assert denied.status_code == 403
        # 归属方读取正常(空历史也不报错)
        owned = client.get(
            f"/api/sessions/{a['thread_id']}/messages",
            params={"client_id": "client_aaa"},
        )
        assert owned.status_code == 200
        # 跨 client 删除被 403 拒绝
        assert (
            client.delete(
                f"/api/sessions/{a['thread_id']}",
                params={"client_id": "client_bbb"},
            ).status_code
            == 403
        )
        # 归属方删除成功
        assert (
            client.delete(
                f"/api/sessions/{a['thread_id']}",
                params={"client_id": "client_aaa"},
            ).status_code
            == 200
        )


def test_session_api_defaults_to_fresh_and_exposes_branch_and_continue(tmp_path: Path) -> None:
    manager = _manager(tmp_path)
    app = create_app(
        checkpoint_db_path=tmp_path / "checkpoints.sqlite",
        design_run_manager=manager,
    )

    with TestClient(app) as client:
        fresh_response = client.post("/api/sessions", json={})
        assert fresh_response.status_code == 200
        fresh = fresh_response.json()
        assert fresh["design_mode"] == "fresh"

        branch_response = client.post(
            "/api/sessions",
            json={
                "mode": "branch",
                "source_design_run_id": fresh["design_run_id"],
            },
        )
        assert branch_response.status_code == 200
        branch = branch_response.json()
        assert branch["design_mode"] == "branch"
        assert branch["design_run_id"] != fresh["design_run_id"]

        continue_response = client.post(
            "/api/sessions",
            json={
                "mode": "continue",
                "source_design_run_id": fresh["design_run_id"],
            },
        )
        assert continue_response.status_code == 200
        continued = continue_response.json()
        assert continued["design_mode"] == "continue"
        assert continued["design_run_id"] == fresh["design_run_id"]

        history = client.get(
            f"/api/sessions/{continued['thread_id']}/messages"
        ).json()
        assert history["design_mode"] == "continue"
        assert history["design_run_id"] == fresh["design_run_id"]

        scheme = client.get(
            "/api/scheme",
            params={"design_run_id": branch["design_run_id"]},
        )
        assert scheme.status_code == 200
        assert scheme.json()["scheme_id"] == branch["current_version_id"]
