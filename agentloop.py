"""CLI 入口：加载当前 Scheme，并驱动 agent_graph（LangGraph）的交互循环。

工具定义在 agent_tools.py，图编排在 agent_graph.py。本文件只负责命令行交互，
不再承载工具实现，避免编排层与 CLI 层耦合。
"""

from agent_tools import load_current_scheme


def run_cli():
    # 启动时把当前 Scheme 读入 agent_tools 模块内存（工具共享同一份状态）
    load_current_scheme()

    # 函数内惰性导入，避免 agentloop -> agent_graph -> agentloop 循环依赖
    from langchain_core.messages import AIMessage, HumanMessage

    from agent_graph import build_graph, build_initial_messages

    graph = build_graph()
    config = {"configurable": {"thread_id": "house-design-cli"}}

    while True:
        user_input = input("请开始对话   ")
        messages = [*build_initial_messages(), HumanMessage(content=user_input)]

        result = graph.invoke({"messages": messages}, config=config)
        final_message = result["messages"][-1]
        if isinstance(final_message, AIMessage) and final_message.content:
            print(final_message.content)


if __name__ == "__main__":
    run_cli()
