"""LangGraph 编排层：把 agentloop 的手写 tool-calling 循环升级为显式状态图。

State 只有一条消息列表；两个节点（agent / tools）通过条件路由组成
agent -> tools -> agent -> ... -> END 的 ReAct 循环。视觉工具（observe_*）
返回的 JPEG 图片块以一条 HumanMessage 注入，保持升级前的行为不变。
"""

from __future__ import annotations

from typing import Annotated, TypedDict

from langchain_core.messages import AIMessage, HumanMessage, ToolMessage
from langgraph.checkpoint.memory import MemorySaver
from langgraph.graph import END, START, StateGraph
from langgraph.graph.message import add_messages

from ..tools.tools import (
    VisualToolOutput,
    execute_tool,
    tools,
    visual_evidence_message,
)
from .model import get_model
from .prompt import build_initial_messages  # noqa: F401  (re-export 兼容旧 import)


class AgentState(TypedDict):
    messages: Annotated[list, add_messages]


def agent_node(state: AgentState) -> dict:
    """调用模型（绑定工具），返回它生成的 AIMessage。"""
    response = get_model().bind_tools(tools).invoke(state["messages"])
    return {"messages": [response]}


def tools_node(state: AgentState) -> dict:
    """执行上一条 AIMessage 的所有 tool_calls，返回 ToolMessage 列表。

    视觉工具的结果是 VisualToolOutput：其 summary 作为 tool result 文本，
    JPEG 图片块再以一条 HumanMessage 追加（图片作为真正的图像输入回传）。
    """
    last = state["messages"][-1]
    tool_messages: list = []
    visual_outputs: list[VisualToolOutput] = []

    for tool_call in last.tool_calls:
        result = execute_tool(tool_call["name"], tool_call["args"])
        if isinstance(result, VisualToolOutput):
            visual_outputs.append(result)
            content = result.summary
        else:
            content = result
        tool_messages.append(
            ToolMessage(content=content, tool_call_id=tool_call["id"])
        )

    new_messages: list = tool_messages
    if visual_outputs:
        evidence_content = visual_evidence_message(visual_outputs)["content"]
        new_messages = [*tool_messages, HumanMessage(content=evidence_content)]
    return {"messages": new_messages}


def route_after_agent(state: AgentState) -> str:
    """最后一条 AIMessage 有 tool_calls 就去 tools，否则结束本轮。"""
    last = state["messages"][-1]
    return "tools" if getattr(last, "tool_calls", None) else "end"


def build_graph(checkpointer=None):
    """构建并编译 ReAct 状态图。

    checkpointer 为 None 时使用 MemorySaver（CLI/旧测试行为）；
    FastAPI 服务可传入 SqliteSaver 实现跨轮与重启持久化。
    """
    builder = StateGraph(AgentState)
    builder.add_node("agent", agent_node)
    builder.add_node("tools", tools_node)
    builder.add_edge(START, "agent")
    builder.add_conditional_edges(
        "agent",
        route_after_agent,
        {"tools": "tools", "end": END},
    )
    builder.add_edge("tools", "agent")
    return builder.compile(checkpointer=checkpointer or MemorySaver())
