from __future__ import annotations

import json
import unittest
from pathlib import Path

from backend.agent_api.prompt_context import (
    build_design_context,
    build_skill_context,
    build_system_prompt,
)


PROJECT_ROOT = Path(__file__).resolve().parents[2]


class PromptLayerTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.scene_manifest = json.loads(
            (PROJECT_ROOT / "scene_manifest.json").read_text(encoding="utf-8")
        )
        cls.asset_manifest = json.loads(
            (PROJECT_ROOT / "asset_manifest.json").read_text(encoding="utf-8")
        )
        cls.system_prompt = build_system_prompt(cls.scene_manifest, cls.asset_manifest)
        cls.skill = build_skill_context(
            PROJECT_ROOT / "skills" / "residential-aesthetic-design" / "SKILL.md"
        )
        cls.design = build_design_context(PROJECT_ROOT / "design.md")

    def test_system_prompt_contains_identity_responsibilities_and_goal_only(self) -> None:
        for heading in ("【身份】", "【职能】", "【目标】"):
            self.assertIn(heading, self.system_prompt)
        for workflow_detail in (
            "begin_design_execution",
            "filter_assets",
            "submit_for_critic",
            "surface_style_gap",
            "工具工作流",
            "对话状态机",
        ):
            self.assertNotIn(workflow_detail, self.system_prompt)
        self.assertIn("交付规划的这一轮必须结束回复", self.system_prompt)
        self.assertIn("不得调用 `update_scheme`", self.system_prompt)
        self.assertIn("最早从用户下一条消息开始执行", self.system_prompt)
        self.assertIn("该回复只提出必要问题", self.system_prompt)
        self.assertIn("都不等于完整设计的信息已经充分", self.system_prompt)
        self.assertIn("2–4 项边界", self.system_prompt)
        self.assertIn("不能只询问颜色和纹理", self.system_prompt)
        self.assertIn("完整设计的信息已经充分", self.system_prompt)

    def test_skill_contains_open_operational_guidance_without_design_textbook_sections(self) -> None:
        for process_heading in (
            "自主工作原则",
            "完整设计：先理解与规划",
            "执行与调整",
            "工具与事实",
            "验证与汇报",
        ):
            self.assertIn(process_heading, self.skill)
        for knowledge_heading in ("色彩故事", "材质复杂度预算", "五类资产的专业知识"):
            self.assertNotIn(knowledge_heading, self.skill)
        self.assertFalse(self.skill.startswith("---"))
        for removed_workflow_term in (
            "workflow_stage",
            "propose_style_brief",
            "submit_for_critic",
            "complete_light_edit",
        ):
            self.assertNotIn(removed_workflow_term, self.skill)
        self.assertIn("ask_design_critic", self.skill)
        self.assertIn("set_design_work_type", self.skill)
        self.assertIn("`NOT_STARTED`", self.skill)
        self.assertIn("`LIGHT`", self.skill)
        self.assertIn("`HEAVY`", self.skill)
        self.assertIn("任务尺度与 Critic", self.skill)
        self.assertIn("完整设计", self.skill)
        self.assertIn("轻度修改不调用 Critic", self.skill)
        self.assertIn("拥有交付阻断权", self.skill)
        self.assertIn("只有最新结论为 `PASS` 才能交付", self.skill)
        self.assertIn("需求已经充分，不为走流程而追问", self.skill)
        self.assertIn("目标彼此冲突，先请用户确认优先级", self.skill)
        self.assertIn("冲突尚未解决的回复只提必要问题", self.skill)
        self.assertIn("宽泛词时，不能据此确定", self.skill)
        self.assertIn("“你来决定”只表示", self.skill)
        self.assertIn("整屋任务不能只问颜色和纹理", self.skill)
        self.assertIn("充分不等于每个房间和材料都由用户指定", self.skill)
        self.assertIn("用户表示“不知道”或授权你决定时，不重复追问", self.skill)
        self.assertIn("交付规划的同一轮，都不得调用 `update_scheme`", self.skill)
        self.assertIn("规划至少包括", self.skill)

    def test_design_context_contains_knowledge_without_agent_process(self) -> None:
        for knowledge_heading in ("基础视觉语法", "色彩知识", "五类资产的专业知识", "审美验收维度"):
            self.assertIn(knowledge_heading, self.design)
        for process_heading in (
            "住宅硬装审美设计流程",
            "自适应访谈知识",
            "Agent 知识建模",
            "当前项目的落地次序",
            "begin_design_execution",
            "submit_for_critic",
        ):
            self.assertNotIn(process_heading, self.design)

    def test_context_layers_are_materially_smaller_than_previous_bundle(self) -> None:
        self.assertLess(len(self.system_prompt), 3_000)
        self.assertLess(len(self.skill), 5_000)
        self.assertLess(len(self.system_prompt) + len(self.skill) + len(self.design), 20_000)

    def test_initial_messages_keep_layers_separate_when_langchain_is_available(self) -> None:
        try:
            from backend.agent_api.agent.prompt import build_initial_messages
        except ModuleNotFoundError as error:
            if error.name == "langchain_core":
                self.skipTest("langchain_core is not installed in this local Python environment")
            raise

        messages = build_initial_messages()
        self.assertEqual(len(messages), 3)
        self.assertTrue(messages[0].content.startswith("【身份】"))
        self.assertTrue(messages[1].content.startswith("【工作方法】"))
        self.assertTrue(messages[2].content.startswith("【住宅硬装审美知识】"))


if __name__ == "__main__":
    unittest.main()
