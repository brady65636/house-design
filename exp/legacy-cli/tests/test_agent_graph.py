"""agent_graph.py（LangGraph 编排层）的图结构与节点行为测试。

这些测试不调用真实模型 API：
- tools_node 用构造的假 AIMessage 驱动，验证工具执行、ToolMessage 与视觉证据注入；
- execute_tool 复用现有工具契约；
- build_graph 只验证图结构本身。
"""

import json
import unittest
from unittest.mock import patch

import agent_graph
from langchain_core.messages import AIMessage, HumanMessage, SystemMessage, ToolMessage


def _tool_call(name: str, args: dict, call_id: str) -> dict:
    return {"name": name, "args": args, "id": call_id, "type": "tool_call"}


class AgentGraphTests(unittest.TestCase):
    def test_initial_messages_only_contain_system_prompt(self) -> None:
        messages = agent_graph.build_initial_messages()
        self.assertEqual(len(messages), 1)
        self.assertIsInstance(messages[0], SystemMessage)
        self.assertIn("整屋装修设计", messages[0].content)

    def test_tools_node_executes_room_lookup(self) -> None:
        call = _tool_call("get_room_by_id", {"room_id": "open_public"}, "call_room_1")
        state = {"messages": [AIMessage(content="", tool_calls=[call])]}
        result = agent_graph.tools_node(state)
        self.assertEqual(len(result["messages"]), 1)
        message = result["messages"][0]
        self.assertIsInstance(message, ToolMessage)
        self.assertEqual(message.tool_call_id, "call_room_1")
        room = json.loads(message.content)
        self.assertEqual(room["name_zh"], "完整横厅客厅")

    def test_tools_node_passes_visual_jpeg_as_image_input(self) -> None:
        class Response:
            status_code = 200
            text = ""

            @staticmethod
            def json():
                return {
                    "result": {
                        "tool": "observe_room",
                        "room": {"label": "客厅"},
                        "views": [{"label": "主视角", "imageDataUrl": "data:image/jpeg;base64,abc"}],
                    }
                }

        call = _tool_call("observe_room", {"room_id": "open_public"}, "call_obs_1")
        state = {"messages": [AIMessage(content="", tool_calls=[call])]}
        with patch("agent_tools.httpx.post", return_value=Response()):
            result = agent_graph.tools_node(state)

        # 工具消息 + 视觉证据用户消息
        self.assertEqual(len(result["messages"]), 2)
        tool_message, evidence_message = result["messages"]
        self.assertIsInstance(tool_message, ToolMessage)
        self.assertNotIn("data:image", tool_message.content)
        self.assertIsInstance(evidence_message, HumanMessage)
        self.assertEqual(evidence_message.content[2]["type"], "image_url")
        self.assertEqual(
            evidence_message.content[2]["image_url"]["url"],
            "data:image/jpeg;base64,abc",
        )

    def test_execute_tool_rejects_extra_forbidden_argument(self) -> None:
        error = agent_graph.execute_tool(
            "get_asset_by_category", {"category": "tile", "limit": 5}
        )
        self.assertIn("extra_forbidden", error)

    def test_execute_tool_unknown_name(self) -> None:
        self.assertEqual(agent_graph.execute_tool("no_such_tool", {}), "该工具不存在")

    def test_route_after_agent_routes_to_tools_when_tool_calls_present(self) -> None:
        call = _tool_call("get_room_by_id", {"room_id": "open_public"}, "call_room_2")
        state = {"messages": [AIMessage(content="", tool_calls=[call])]}
        self.assertEqual(agent_graph.route_after_agent(state), "tools")

    def test_route_after_agent_ends_when_no_tool_calls(self) -> None:
        state = {"messages": [AIMessage(content="这是最终回答")]}
        self.assertEqual(agent_graph.route_after_agent(state), "end")

    def test_build_graph_has_agent_and_tools_nodes(self) -> None:
        graph = agent_graph.build_graph()
        nodes = set(graph.nodes.keys())
        self.assertIn("agent", nodes)
        self.assertIn("tools", nodes)


if __name__ == "__main__":
    unittest.main()
