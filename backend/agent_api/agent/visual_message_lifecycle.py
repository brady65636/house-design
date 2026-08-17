"""共享的临时视觉消息生命周期。

主 Agent（graph）与 Critic 都在工具执行后把 Base64 图片注入一条
HumanMessage。这些图片只应被紧随其后的那一次模型调用看到，绝不能留在
checkpoint / 本地消息列表里被后续所有请求反复携带，否则单次对话会膨胀到
几十万 tokens。

生命周期契约：

  tools_node / Critic 生成带唯一 id 和 ephemeral_visual_evidence=True 的
  HumanMessage
    -> 紧邻的模型 invoke 能看到这些图片
    -> invoke 成功返回后，属主在同一个 state update 里删除这些消息
       （主 Agent 用 RemoveMessage，Critic 直接过滤本地列表）

普通用户上传的 HumanMessage 不会带 ephemeral_visual_evidence 标记，因此
永远不会被误删。
"""

from __future__ import annotations

from uuid import uuid4

from langchain_core.messages import HumanMessage, RemoveMessage

# 标记工具产生的临时视觉证据（主 Agent 与 Critic 共用）。
EPHEMERAL_VISUAL_FLAG = "ephemeral_visual_evidence"


def _is_ephemeral_visual_message(message) -> bool:
    """只有工具产生的、含 image_url 且带临时标记的 HumanMessage 才算临时视觉消息。"""
    if not isinstance(message, HumanMessage):
        return False

    if message.additional_kwargs.get(EPHEMERAL_VISUAL_FLAG) is not True:
        return False

    content = message.content
    return isinstance(content, list) and any(
        isinstance(block, dict) and block.get("type") == "image_url"
        for block in content
    )


# 模块级共享，供 graph 与 critic 跨模块使用；保留下划线形式作为内部命名。
is_ephemeral_visual_message = _is_ephemeral_visual_message


def build_ephemeral_visual_message(content) -> HumanMessage:
    """把工具视觉内容包装成带唯一 id 和临时标记的 HumanMessage。

    content 来自 tools.visual_evidence_message(...) 的 ["content"]，是含
    text + image_url 的 block 列表。普通用户消息不要经过这里。
    """
    return HumanMessage(
        id=f"visual-{uuid4().hex}",
        content=content,
        additional_kwargs={EPHEMERAL_VISUAL_FLAG: True},
    )


def remove_ephemeral_visual_messages(messages) -> list:
    """为 messages 里所有已消费的临时视觉消息生成 RemoveMessage（主 Agent 用）。"""
    return [
        RemoveMessage(id=message.id)
        for message in messages
        if _is_ephemeral_visual_message(message)
    ]


def filter_ephemeral_visual_messages(messages) -> list:
    """从本地消息列表移除已消费的临时视觉消息（Critic 用，不走 checkpoint）。"""
    return [
        message for message in messages if not _is_ephemeral_visual_message(message)
    ]
