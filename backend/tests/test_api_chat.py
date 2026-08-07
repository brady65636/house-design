"""Agent API 集成测试:TestClient + 假模型,不调用真实模型 API。

覆盖:同 thread 两轮上下文延续、历史查询、/api/scheme 读取、
update_scheme 工具经 API 写穿 SchemeStore。
"""

import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from fastapi.testclient import TestClient

from backend.agent_api.main import create_app
from backend.agent_api.scheme.store import SchemeStore

from langchain_core.messages import AIMessage

PROJECT_ROOT = Path(__file__).resolve().parents[2]


def _tool_call(name: str, args: dict, call_id: str) -> dict:
    return {"name": name, "args": args, "id": call_id, "type": "tool_call"}


class FakeModel:
    """按序返回预置 AIMessage 的最小假模型(忽略输入)。"""

    def __init__(self, responses: list[AIMessage]) -> None:
        self._responses = list(responses)
        self._index = 0

    def bind_tools(self, tools):
        return self

    def invoke(self, messages):
        response = self._responses[self._index]
        self._index += 1
        return response


class ApiChatTests(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp = tempfile.TemporaryDirectory()
        self.tmpdir = Path(self.tmp.name)

        source = PROJECT_ROOT / "viewer" / "public" / "current_scheme.json"
        scheme_path = self.tmpdir / "current_scheme.json"
        scheme_path.write_text(source.read_text(encoding="utf-8"), encoding="utf-8")
        scene = json.loads(
            (PROJECT_ROOT / "scene_manifest.json").read_text(encoding="utf-8")
        )
        assets = json.loads(
            (PROJECT_ROOT / "asset_manifest.json").read_text(encoding="utf-8")
        )
        self.scheme_store = SchemeStore(scheme_path, scene, assets)
        self.scheme_store.load()

    def tearDown(self) -> None:
        self.tmp.cleanup()

    def _client(self) -> TestClient:
        app = create_app(
            checkpoint_db_path=self.tmpdir / "checkpoints.sqlite",
            scheme_store=self.scheme_store,
        )
        return TestClient(app)

    def test_chat_round_trip_keeps_context_within_thread(self) -> None:
        fake = FakeModel(
            [
                AIMessage(content="", tool_calls=[_tool_call("load_scheme", {}, "c1")]),
                AIMessage(content="第一轮最终回复"),
                AIMessage(content="第二轮最终回复"),
            ]
        )
        with self._client() as client:
            with patch("backend.agent_api.agent.graph.get_model", return_value=fake):
                first = client.post(
                    "/api/chat", json={"thread_id": "t1", "message": "看看方案"}
                )
                second = client.post(
                    "/api/chat", json={"thread_id": "t1", "message": "继续"}
                )

        self.assertEqual(first.status_code, 200)
        self.assertEqual(first.json()["reply"], "第一轮最终回复")
        self.assertEqual(first.json()["message_count"], 5)  # system,user,ai(tc),tool,ai

        self.assertEqual(second.status_code, 200)
        self.assertEqual(second.json()["reply"], "第二轮最终回复")
        # 第二轮叠加第一轮全部消息
        self.assertEqual(second.json()["message_count"], 7)

    def test_messages_history_endpoint(self) -> None:
        fake = FakeModel([AIMessage(content="仅文字回复")])
        with self._client() as client:
            with patch("backend.agent_api.agent.graph.get_model", return_value=fake):
                client.post("/api/chat", json={"thread_id": "t2", "message": "你好"})
                history = client.get("/api/sessions/t2/messages")

        self.assertEqual(history.status_code, 200)
        roles = [message["role"] for message in history.json()["messages"]]
        self.assertEqual(roles, ["system", "user", "assistant"])

    def test_scheme_endpoint_returns_current_scheme(self) -> None:
        with self._client() as client:
            scheme = client.get("/api/scheme")
            version = client.get("/api/scheme/version")

        self.assertEqual(scheme.status_code, 200)
        self.assertEqual(scheme.json()["scheme_id"], self.scheme_store.get()["scheme_id"])
        self.assertEqual(version.json()["scheme_id"], self.scheme_store.get()["scheme_id"])

    def test_update_scheme_tool_writes_through_api(self) -> None:
        fake = FakeModel(
            [
                AIMessage(
                    content="",
                    tool_calls=[
                        _tool_call(
                            "update_scheme",
                            {
                                "target_id": "wall_face_real4_010",
                                "asset_id": "paint_light_greige_eggshell_01",
                            },
                            "c3",
                        )
                    ],
                ),
                AIMessage(content="已更新"),
            ]
        )
        before_id = self.scheme_store.get()["scheme_id"]
        with self._client() as client:
            with patch("backend.agent_api.agent.graph.get_model", return_value=fake):
                response = client.post(
                    "/api/chat", json={"thread_id": "t3", "message": "改客厅墙"}
                )
            version = client.get("/api/scheme/version")

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["reply"], "已更新")
        self.assertNotEqual(version.json()["scheme_id"], before_id)

    def test_chat_requires_token_when_configured(self) -> None:
        from backend.agent_api.config import settings

        fake = FakeModel([AIMessage(content="有鉴权回复")])
        original = settings.agent_api_token
        settings.agent_api_token = "test-token"
        try:
            with self._client() as client:
                no_token = client.post(
                    "/api/chat", json={"thread_id": "t9", "message": "hi"}
                )
                self.assertEqual(no_token.status_code, 401)

                with patch("backend.agent_api.agent.graph.get_model", return_value=fake):
                    with_token = client.post(
                        "/api/chat",
                        json={"thread_id": "t9", "message": "hi"},
                        headers={"Authorization": "Bearer test-token"},
                    )
                self.assertEqual(with_token.status_code, 200)
                self.assertEqual(with_token.json()["reply"], "有鉴权回复")

                # /api/scheme 匿名可读(只读例外)
                scheme = client.get("/api/scheme")
                self.assertEqual(scheme.status_code, 200)
        finally:
            settings.agent_api_token = original


if __name__ == "__main__":
    unittest.main()
