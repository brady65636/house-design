"""Agent 初始消息构建。"""

from langchain_core.messages import SystemMessage

from ..tools.tools import SYSTEM_PROMPT


def build_initial_messages() -> list[SystemMessage]:
    return [SystemMessage(content=SYSTEM_PROMPT)]
