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

from backend.agent_api.agent.graph import CRITIC_BLOCKED_MESSAGE
from backend.agent_api.tools.tools import VisualToolOutput
from backend.tests._responses_mock import responses_side_effect

PROJECT_ROOT = Path(__file__).resolve().parents[2]


def _tool_call(name: str, args: dict, call_id: str) -> dict:
    return {"name": name, "args": args, "id": call_id, "type": "tool_call"}


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


def responses_streaming_side_effect(ai_messages):
    """流式 mock：每次调用时用 on_text_delta 逐段推送文本，再返回完整结果。"""
    from uuid import uuid4

    from backend.agent_api.agent.responses_client import ResponsesResult

    state = {"index": 0}
    calls: list[dict] = []

    def _call(*, input_items=None, previous_response_id=None, tools=None, **kwargs):
        calls.append({"input_items": input_items, "previous_response_id": previous_response_id})
        index = state["index"]
        if index >= len(ai_messages):
            raise AssertionError(f"fake responses exhausted at index {index}")
        state["index"] += 1
        item = ai_messages[index]
        if isinstance(item, Exception):
            raise item
        text = item.content if isinstance(item.content, str) else ""
        on_text_delta = kwargs.get("on_text_delta")
        if on_text_delta is not None:
            # 模拟真实流式：按句子拆分，逐段回调
            for chunk in _split_into_chunks(text, 3):
                on_text_delta(chunk)
        tool_calls = [
            {"name": tc.get("name"), "args": tc.get("args"), "id": tc.get("id")}
            for tc in (item.tool_calls or [])
        ]
        return ResponsesResult(
            text=text,
            tool_calls=tool_calls,
            response_id=f"fake-stream-{uuid4().hex[:12]}",
            usage=None,
        )

    _call.calls = calls
    return _call


def _split_into_chunks(text: str, size: int) -> list[str]:
    return [text[i : i + size] for i in range(0, len(text), size)] if text else []


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
        fake = [
            AIMessage(
                content="",
                tool_calls=[_tool_call("load_scheme", {}, "c1")],
            ),
            AIMessage(content="这是最终回复"),
        ]
        app = create_app(
            checkpoint_db_path=self.tmpdir / "checkpoints.sqlite",
            scheme_store=self.scheme_store,
        )
        with TestClient(app) as client:
            with patch("backend.agent_api.agent.graph.call_responses", side_effect=responses_side_effect(fake)):
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

    def test_sse_never_streams_delivery_text_while_critic_gate_is_blocked(self) -> None:
        fake = [
            AIMessage(
                content="",
                tool_calls=[
                    _tool_call(
                        "set_design_work_type",
                            {
                                "work_type": "HEAVY",
                                "reason": "用户已经批准完整设计开始实施",
                            },
                            "start-heavy",
                        )
                    ],
                ),
                AIMessage(
                    content="",
                    tool_calls=[
                        _tool_call(
                            "update_scheme",
                            {
                                "target_id": "wall_face_real4_010",
                                "asset_id": "paint_greige_01",
                            },
                            "write-1",
                        )
                    ],
                ),
                AIMessage(
                    content="",
                    tool_calls=[
                        _tool_call(
                            "observe_room",
                            {"room_id": "open_public", "focus_target_ids": []},
                            "observe-1",
                        )
                    ],
                ),
                AIMessage(
                    content="",
                    tool_calls=[_tool_call("ask_design_critic", {}, "critic-1")],
                ),
                AIMessage(content="错误的完成声明一"),
                AIMessage(content="错误的完成声明二"),
                AIMessage(content="错误的完成声明三"),
                AIMessage(content="错误的完成声明四"),
        ]
        app = create_app(
            checkpoint_db_path=self.tmpdir / "critic-checkpoints.sqlite",
            scheme_store=self.scheme_store,
        )
        critic_result = json.dumps(
            {"verdict": "REVISE", "review": "焦点关系仍未通过"},
            ensure_ascii=False,
        )

        def execute(name, _args, _call_id=None):
            if name == "set_design_work_type":
                return json.dumps(
                    {
                        "status": "WORK_TYPE_REQUEST_VALID",
                        "requested_work_type": "HEAVY",
                        "reason": "用户已经批准完整设计开始实施",
                    },
                    ensure_ascii=False,
                )
            if name == "update_scheme":
                return "修改scheme成功，新方案ID：scheme-v1"
            if name == "observe_room":
                return VisualToolOutput(
                    summary=json.dumps(
                        {
                            "status": "ready",
                            "modelEvidenceReady": True,
                            "scheme": {"schemeId": "scheme-v1"},
                            "room": {"id": "open_public"},
                        },
                        ensure_ascii=False,
                    ),
                    images=[("客厅当前版本", "data:image/jpeg;base64,ZmFrZQ==")],
                )
            if name == "ask_design_critic":
                return critic_result
            raise AssertionError(f"unexpected tool: {name}")

        with TestClient(app) as client:
            with patch("backend.agent_api.agent.graph.call_responses", side_effect=responses_side_effect(fake)), patch(
                "backend.agent_api.agent.graph.execute_tool", side_effect=execute
            ):
                response = client.post(
                    "/api/chat/stream",
                    json={"thread_id": "critic-stream", "message": "完成并交付"},
                )

        self.assertNotIn("错误的完成声明", response.text)
        events = parse_sse(response.text)
        self.assertEqual(events[-1][0], "done")
        self.assertEqual(events[-1][1]["reply"], CRITIC_BLOCKED_MESSAGE)

    def test_sse_streams_text_deltas_via_custom_channel(self) -> None:
        """流式模式：on_text_delta 通过 custom stream 转成逐段 message_delta。

        最终文本由各 delta 拼接还原，且不重复出现整块文本。
        """
        fake = [AIMessage(content="第一段。第二段，完成。")]
        app = create_app(
            checkpoint_db_path=self.tmpdir / "stream-checkpoints.sqlite",
            scheme_store=self.scheme_store,
        )
        with TestClient(app) as client:
            with patch(
                "backend.agent_api.agent.graph.call_responses",
                side_effect=responses_streaming_side_effect(fake),
            ):
                response = client.post(
                    "/api/chat/stream",
                    json={"thread_id": "stream-t1", "message": "流式输出测试"},
                )

        self.assertEqual(response.status_code, 200)
        events = parse_sse(response.text)
        types = [event_type for event_type, _ in events]
        self.assertEqual(types[0], "meta")
        self.assertEqual(types[-1], "done")
        deltas = [
            data["delta"]
            for event_type, data in events
            if event_type == "message_delta"
        ]
        self.assertGreater(len(deltas), 1, "应当有多个 message_delta 增量")
        self.assertEqual("".join(deltas), "第一段。第二段，完成。")
        done = events[-1][1]
        self.assertEqual(done["reply"], "第一段。第二段，完成。")

    def test_stream_parse_preserves_function_call_from_output_item(self) -> None:
        """流式解析：function_call 的 name/call_id 来自 output_item.added，
        arguments 来自 function_call_arguments.delta/done，必须完整保留。

        这是"欧克空气泡"回归：此前只在 function_call_arguments.done 读
        name/call_id（该事件没有这两个字段），导致工具调用被丢弃。
        """
        from backend.agent_api.agent.responses_client import _stream_parse_response

        pending: dict = {
            "text_parts": [],
            "tool_calls": [],
            "tool_args_parts": [],
            "fc_meta": {},
        }
        fc_id = "fc_02178679397216000000000000000000000ffffac154c91674439"
        events = [
            {
                "type": "response.created",
                "response": {"id": "resp_test_1"},
            },
            {
                "type": "response.output_item.added",
                "output_index": 0,
                "item": {
                    "type": "function_call",
                    "id": fc_id,
                    "name": "set_design_work_type",
                    "call_id": "call_8g9oq1v730gzahevn9nloxw8",
                    "status": "in_progress",
                },
            },
            {
                "type": "response.function_call_arguments.delta",
                "delta": '{"work_type": "',
                "item_id": fc_id,
            },
            {
                "type": "response.function_call_arguments.delta",
                "delta": 'HEAVY"}',
                "item_id": fc_id,
            },
            {
                "type": "response.function_call_arguments.done",
                "item_id": fc_id,
                "arguments": '{"work_type": "HEAVY"}',
            },
        ]
        for event in events:
            _stream_parse_response(event, pending)

        self.assertEqual(pending["response_id"], "resp_test_1")
        self.assertEqual(len(pending["tool_calls"]), 1)
        tool = pending["tool_calls"][0]
        self.assertEqual(tool["name"], "set_design_work_type")
        self.assertEqual(tool["id"], "call_8g9oq1v730gzahevn9nloxw8")
        self.assertEqual(tool["args"], {"work_type": "HEAVY"})
        # 工具调用不应被误当成文本
        self.assertEqual(pending["text_parts"], [])

    def test_stream_parse_output_item_done_backfill(self) -> None:
        """兜底：若 delta 事件缺失，output_item.done 的完整 item 也能补录工具调用。"""
        from backend.agent_api.agent.responses_client import _stream_parse_response

        pending: dict = {
            "text_parts": [],
            "tool_calls": [],
            "tool_args_parts": [],
            "fc_meta": {},
        }
        fc_id = "fc_backfill_001"
        # 只有 added + output_item.done（无 arguments delta/done）
        _stream_parse_response(
            {
                "type": "response.output_item.added",
                "item": {
                    "type": "function_call",
                    "id": fc_id,
                    "name": "load_scheme",
                    "call_id": "call_backfill",
                    "status": "in_progress",
                },
            },
            pending,
        )
        _stream_parse_response(
            {
                "type": "response.output_item.done",
                "item": {
                    "type": "function_call",
                    "id": fc_id,
                    "name": "load_scheme",
                    "call_id": "call_backfill",
                    "arguments": '{"full": true}',
                    "status": "completed",
                },
            },
            pending,
        )

        self.assertEqual(len(pending["tool_calls"]), 1)
        tool = pending["tool_calls"][0]
        self.assertEqual(tool["name"], "load_scheme")
        self.assertEqual(tool["id"], "call_backfill")
        self.assertEqual(tool["args"], {"full": True})


if __name__ == "__main__":
    unittest.main()
