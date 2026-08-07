"""SSE 流式接口测试:消费 /api/chat/stream,解析事件序列。

假模型不流式(自定义 FakeModel),因此 message_delta 只会在真实模型下
出现;这里断言不依赖它的关键事件:meta 开头 -> tool_call/tool_result
交错 -> done 结尾。
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
    def __init__(self, responses: list[AIMessage]) -> None:
        self._responses = list(responses)
        self._index = 0

    def bind_tools(self, tools):
        return self

    def invoke(self, messages):
        response = self._responses[self._index]
        self._index += 1
        return response


def parse_sse(text: str) -> list[tuple[str, dict]]:
    events: list[tuple[str, dict]] = []
    for block in text.split("\n\n"):
        block = block.strip()
        if not block:
            continue
        event, data = None, None
        for line in block.split("\n"):
            if line.startswith("event: "):
                event = line[7:]
            elif line.startswith("data: "):
                data = json.loads(line[6:])
        if event is not None:
            events.append((event, data))
    return events


class ApiSseTests(unittest.TestCase):
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

    def test_sse_emits_key_events_in_order(self) -> None:
        fake = FakeModel(
            [
                AIMessage(
                    content="",
                    tool_calls=[_tool_call("load_scheme", {}, "c1")],
                ),
                AIMessage(content="这是最终回复"),
            ]
        )
        app = create_app(
            checkpoint_db_path=self.tmpdir / "checkpoints.sqlite",
            scheme_store=self.scheme_store,
        )
        with TestClient(app) as client:
            with patch("backend.agent_api.agent.graph.get_model", return_value=fake):
                response = client.post(
                    "/api/chat/stream",
                    json={"thread_id": "t1", "message": "看看方案"},
                )

        self.assertEqual(response.status_code, 200)
        self.assertIn("text/event-stream", response.headers["content-type"])

        events = parse_sse(response.text)
        types = [event_type for event_type, _ in events]
        self.assertEqual(types[0], "meta")
        self.assertIn("tool_call", types)
        self.assertIn("tool_result", types)
        self.assertEqual(types[-1], "done")

        tool_call = next(data for event_type, data in events if event_type == "tool_call")
        self.assertEqual(tool_call["tool"], "load_scheme")
        done = events[-1][1]
        self.assertEqual(done["reply"], "这是最终回复")
        self.assertEqual(done["thread_id"], "t1")


if __name__ == "__main__":
    unittest.main()
