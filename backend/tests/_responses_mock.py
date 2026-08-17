"""测试辅助：把 AIMessage 序列 mock 成 Responses API 的 call_responses。

迁移后 graph.py / critic.py 不再调用 ChatOpenAI，而是调用
responses_client.call_responses（返回 ResponsesResult）。原有测试用 FakeModel
模拟 bind_tools().invoke() 按序返回 AIMessage；这里提供 responses_side_effect，
把同样的 AIMessage 序列转成按序返回的 ResponsesResult，测试只需把 patch 目标
从 get_model / get_critic_model 换成 call_responses。
"""

from uuid import uuid4

from backend.agent_api.agent.responses_client import ResponsesResult


def ai_message_to_result(ai_message, index: int) -> ResponsesResult:
    """把一个 AIMessage 转成等价的 ResponsesResult（text + tool_calls + 唯一 id）。"""
    text = ai_message.content if isinstance(ai_message.content, str) else ""
    tool_calls = [
        {"name": tc.get("name"), "args": tc.get("args"), "id": tc.get("id")}
        for tc in (ai_message.tool_calls or [])
    ]
    return ResponsesResult(
        text=text,
        tool_calls=tool_calls,
        # response_id 必须全局唯一：agent_node 用它作为 AIMessage 的 id，LangGraph 的
        # add_messages 会按 id 去重，跨轮/跨实例重复会把历史消息覆盖掉。
        response_id=f"fake-resp-{uuid4().hex[:12]}",
        usage=None,
    )


def responses_side_effect(ai_messages):
    """返回一个 side_effect 函数，按序把 AIMessage 转成 ResponsesResult。

    列表元素可以是 AIMessage（正常返回）或 Exception 实例（该次调用抛出）。
    返回的函数带 ``.calls`` 属性，记录每次调用的 input_items / previous_response_id，
    供测试断言视觉图片等是否被正确传给模型。
    """

    state = {"index": 0}
    calls: list[dict] = []

    def _call(*, input_items=None, previous_response_id=None, tools=None, **kwargs):
        calls.append(
            {"input_items": input_items, "previous_response_id": previous_response_id}
        )
        index = state["index"]
        if index >= len(ai_messages):
            raise AssertionError(
                f"fake responses exhausted at index {index} (only {len(ai_messages)} preset)"
            )
        state["index"] += 1
        item = ai_messages[index]
        if isinstance(item, Exception):
            raise item
        return ai_message_to_result(item, index + 1)

    _call.calls = calls
    return _call
