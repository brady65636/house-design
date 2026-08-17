"""SQLite checkpoint 持久化测试:两次独立 graph 实例(模拟进程重启)同 thread 历史往返。"""

import asyncio
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from backend.agent_api.agent.graph import build_graph
from backend.agent_api.store.checkpoints import open_async_checkpointer
from backend.tests._responses_mock import responses_side_effect

from langchain_core.messages import AIMessage, HumanMessage


def _run_graph(db_path: Path, responses: list[AIMessage]) -> list:
    """用独立事件循环与独立连接跑一轮,模拟一个独立进程实例。"""

    async def main() -> list:
        checkpointer = await open_async_checkpointer(db_path)
        try:
            graph = build_graph(checkpointer=checkpointer)
            config = {"configurable": {"thread_id": "persist-test"}}
            with patch(
                "backend.agent_api.agent.graph.call_responses",
                side_effect=responses_side_effect(responses),
            ):
                await graph.ainvoke(
                    {"messages": [HumanMessage(content="hi")]}, config=config
                )
            state = await graph.aget_state(config)
            return list(state.values["messages"])
        finally:
            await checkpointer.conn.close()

    return asyncio.run(main())


class CheckpointPersistenceTests(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp = tempfile.TemporaryDirectory()
        self.tmpdir = Path(self.tmp.name)
        self.db_path = self.tmpdir / "checkpoints.sqlite"

    def tearDown(self) -> None:
        self.tmp.cleanup()

    def test_history_survives_independent_graph_instances(self) -> None:
        messages1 = _run_graph(self.db_path, [AIMessage(content="第一轮回复")])
        messages2 = _run_graph(self.db_path, [AIMessage(content="第二轮回复")])

        texts = [message.content for message in messages2]
        self.assertIn("第一轮回复", texts)
        self.assertIn("第二轮回复", texts)
        # 第一轮仅含本轮消息
        self.assertEqual(
            [message.content for message in messages1],
            ["hi", "第一轮回复"],
        )


if __name__ == "__main__":
    unittest.main()
