"""Build the three independent context layers used on a session's first turn."""

from langchain_core.messages import SystemMessage

from ..tools.tools import DESIGN_CONTEXT, DESIGN_SKILL_CONTEXT, SYSTEM_PROMPT


def build_initial_messages() -> list[SystemMessage]:
    return [
        SystemMessage(content=SYSTEM_PROMPT),
        SystemMessage(content=f"【工作方法】\n{DESIGN_SKILL_CONTEXT}"),
        SystemMessage(content=f"【住宅硬装审美知识】\n{DESIGN_CONTEXT}"),
    ]
