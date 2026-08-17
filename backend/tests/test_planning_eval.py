"""Offline checks for the dimension-one evaluation runner."""

from pathlib import Path
from types import SimpleNamespace
import unittest

from evals.planning_dimension.run_eval import (
    DEFAULT_DATASET,
    DEEPSEEK_SIMULATOR_MODEL,
    DeepSeekSimulator,
    build_grader_packet,
    extract_tool_calls,
    finalize_subagent_grade,
    load_dataset,
    select_scenarios,
)


class PlanningEvalTests(unittest.TestCase):
    def test_deepseek_simulator_uses_v4_flash_without_thinking(self) -> None:
        captured = {}

        class FakeCompletions:
            def create(self, **kwargs):
                captured.update(kwargs)
                message = SimpleNamespace(
                    content='{"action":"CLOSE","message":null,'
                    '"revealed_fact_ids":[],"reason":"done"}'
                )
                return SimpleNamespace(choices=[SimpleNamespace(message=message)])

        simulator = DeepSeekSimulator.__new__(DeepSeekSimulator)
        simulator.model = DEEPSEEK_SIMULATOR_MODEL
        simulator.client = SimpleNamespace(
            chat=SimpleNamespace(completions=FakeCompletions())
        )
        result = simulator.json_response(
            instructions="只输出 JSON",
            payload={"test": True},
            max_output_tokens=100,
        )
        self.assertEqual(captured["model"], "deepseek-v4-flash")
        self.assertEqual(
            captured["extra_body"], {"thinking": {"type": "disabled"}}
        )
        self.assertEqual(result["action"], "CLOSE")

    def test_dataset_and_selection_are_valid(self) -> None:
        dataset = load_dataset(Path(DEFAULT_DATASET))
        selected = select_scenarios(
            dataset, ["sparse_whole_home_warm_01"], run_all=False
        )
        self.assertEqual(len(dataset["scenarios"]), 12)
        self.assertEqual(selected[0]["max_user_turns"], 8)

    def test_extract_tool_calls_keeps_name_args_and_message_index(self) -> None:
        messages = [
            {"role": "user", "content": "需求"},
            {
                "role": "assistant",
                "content": "",
                "tool_calls": [
                    {"id": "call-1", "name": "load_scheme", "args": {}}
                ],
            },
        ]
        self.assertEqual(
            extract_tool_calls(messages),
            [
                {
                    "message_index": 1,
                    "id": "call-1",
                    "name": "load_scheme",
                    "args": {},
                }
            ],
        )

    def test_grader_packet_contains_code_gate_and_only_needed_context(self) -> None:
        dataset = load_dataset(Path(DEFAULT_DATASET))
        scenario = dataset["scenarios"][0]
        episode = {
            "stop_reason": "premature_update_scheme",
            "transcript": [
                {"role": "user", "content": scenario["initial_message"]},
                {"role": "assistant", "content": "我先修改方案。"},
            ],
            "tool_calls": [{"name": "update_scheme", "args": {}}],
            "update_scheme_succeeded": True,
            "disclosed_fact_ids": ["scope", "intent"],
        }
        packet = build_grader_packet(dataset, scenario, episode)
        self.assertEqual(
            packet["code_gates"]["no_premature_update"]["verdict"], "FAIL"
        )
        self.assertEqual(packet["conversation"][0]["turn_id"], "U1")
        self.assertEqual(packet["product_facts"]["designable_space_count"], 11)
        self.assertNotIn("simulator_decisions", packet)
        self.assertFalse(
            next(
                fact
                for fact in packet["scenario"]["facts"]
                if fact["fact_id"] == "warmth_temperature"
            )["disclosed"]
        )

    def test_finalize_subagent_grade_applies_pass_rule(self) -> None:
        dataset = load_dataset(Path(DEFAULT_DATASET))
        scenario = dataset["scenarios"][0]
        packet = build_grader_packet(
            dataset,
            scenario,
            {
                "stop_reason": "close",
                "transcript": [],
                "tool_calls": [],
                "update_scheme_succeeded": False,
                "disclosed_fact_ids": [fact["fact_id"] for fact in scenario["facts"]],
            },
        )
        judgment = {
            "gates": {
                gate_id: {"verdict": "PASS", "reason": "有对话证据"}
                for gate_id in packet["subagent_gates"]
            },
            "scores": {
                rubric_id: {"score": 3, "reason": "达到合格标准"}
                for rubric_id in packet["soft_rubrics"]
            },
            "summary": "合格",
        }
        grade = finalize_subagent_grade(packet, judgment)
        self.assertTrue(grade["overall_pass"])
        self.assertEqual(grade["score_average"], 3.0)

    def test_finalize_subagent_grade_forces_timeout_plan_failure(self) -> None:
        dataset = load_dataset(Path(DEFAULT_DATASET))
        scenario = dataset["scenarios"][0]
        packet = build_grader_packet(
            dataset,
            scenario,
            {
                "stop_reason": "max_user_turns",
                "transcript": [],
                "tool_calls": [],
                "update_scheme_succeeded": False,
                "disclosed_fact_ids": [],
            },
        )
        judgment = {
            "gates": {
                gate_id: {"verdict": "PASS", "reason": "子 agent 判断"}
                for gate_id in packet["subagent_gates"]
            },
            "scores": {
                rubric_id: {"score": 4, "reason": "子 agent 判断"}
                for rubric_id in packet["soft_rubrics"]
            },
            "summary": "表面优秀但超时",
        }
        grade = finalize_subagent_grade(packet, judgment)
        self.assertEqual(grade["gates"]["plan_delivered"]["verdict"], "FAIL")
        self.assertFalse(grade["overall_pass"])


if __name__ == "__main__":
    unittest.main()
