"""SchemeStore 单元测试:load/get/update、scheme_id 递增、并发原子写。"""

import json
import tempfile
import threading
import unittest
from pathlib import Path

from backend.agent_api.scheme.schema import Scheme
from backend.agent_api.scheme.store import SchemeStore

PROJECT_ROOT = Path(__file__).resolve().parents[2]


class SchemeStoreTests(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp = tempfile.TemporaryDirectory()
        self.tmpdir = Path(self.tmp.name)
        source = PROJECT_ROOT / "viewer" / "public" / "current_scheme.json"
        self.scheme_path = self.tmpdir / "current_scheme.json"
        self.scheme_path.write_text(source.read_text(encoding="utf-8"), encoding="utf-8")
        self.scene = json.loads(
            (PROJECT_ROOT / "scene_manifest.json").read_text(encoding="utf-8")
        )
        self.assets = json.loads(
            (PROJECT_ROOT / "asset_manifest.json").read_text(encoding="utf-8")
        )
        self.store = SchemeStore(self.scheme_path, self.scene, self.assets)

    def tearDown(self) -> None:
        self.tmp.cleanup()

    def test_load_then_get_returns_same_scheme(self) -> None:
        loaded = self.store.load()
        self.assertEqual(loaded, self.store.get())

    def test_update_increments_scheme_id_and_writes_disk(self) -> None:
        self.store.load()
        before_id = self.store.get()["scheme_id"]
        parameters = {"lightness": "light", "saturation": 0.85, "finish": "eggshell"}
        result = self.store.update("wall_face_real4_010", "paint_greige_01", parameters)
        self.assertIn("修改scheme成功", result)
        after_id = self.store.get()["scheme_id"]
        self.assertNotEqual(before_id, after_id)
        # 磁盘与内存同步
        disk = json.loads(self.scheme_path.read_text(encoding="utf-8"))
        self.assertEqual(disk["scheme_id"], after_id)
        updated = next(
            assignment
            for assignment in disk["assignments"]
            if assignment["target"]["id"] == "wall_face_real4_010"
        )
        self.assertEqual(updated["asset_id"], "paint_greige_01")
        self.assertEqual(updated["parameters"], parameters)

    def test_concurrent_updates_stay_serialized_and_file_valid(self) -> None:
        self.store.load()
        errors: list[Exception] = []

        def worker() -> None:
            try:
                self.store.update(
                    "wall_face_real4_010",
                    "paint_warm_white_01",
                    {"lightness": "light", "saturation": 1.0, "finish": "matte"},
                )
            except Exception as error:  # noqa: BLE001
                errors.append(error)

        threads = [threading.Thread(target=worker) for _ in range(8)]
        for thread in threads:
            thread.start()
        for thread in threads:
            thread.join()

        self.assertEqual(errors, [])
        # 并发写后文件仍是合法 Scheme(未被半截 JSON 破坏)
        disk = json.loads(self.scheme_path.read_text(encoding="utf-8"))
        Scheme.model_validate(disk)


if __name__ == "__main__":
    unittest.main()
