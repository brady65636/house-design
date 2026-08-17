"""Offline contract tests for the text-only dimension-two user simulator."""

from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace
import unittest

from evals.outcome_dimension.run_eval import (
    DEFAULT_DATASET,
    build_evidence_packet,
    load_dataset,
)
from evals.outcome_dimension.user_simulator import (
    DEEPSEEK_SIMULATOR_MODEL,
    DeepSeekOutcomeSimulator,
    apply_approved_negotiation,
    ground_plain_fact_response,
    simulate_user_turn,
    validate_simulator_decision,
)


class OutcomeUserSimulatorTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.scenario = load_dataset(Path(DEFAULT_DATASET))["scenarios"][0]
        cls.ledger = {
            item["requirement_id"]: item["statement"]
            for item in cls.scenario["requirement_facts"]
        }

    def test_deepseek_v4_flash_runs_without_thinking(self) -> None:
        captured = {}

        class FakeCompletions:
            def create(self, **kwargs):
                captured.update(kwargs)
                message = SimpleNamespace(content='{"ok":true}')
                return SimpleNamespace(choices=[SimpleNamespace(message=message)])

        simulator = DeepSeekOutcomeSimulator.__new__(DeepSeekOutcomeSimulator)
        simulator.model = DEEPSEEK_SIMULATOR_MODEL
        simulator.client = SimpleNamespace(
            chat=SimpleNamespace(completions=FakeCompletions())
        )
        self.assertTrue(
            simulator.json_response(instructions="JSON", payload={"x": 1})["ok"]
        )
        self.assertEqual(captured["model"], "deepseek-v4-flash")
        self.assertEqual(captured["extra_body"], {"thinking": {"type": "disabled"}})

    def test_close_requires_real_delivery_and_exact_final_ledger(self) -> None:
        baseline = {
            "confirmed_requirements": [
                {"requirement_id": key, "statement": value}
                for key, value in self.ledger.items()
            ],
            "approved_plan": "最终批准的实施方案",
            "allowed_target_ids": self.scenario["allowed_target_ids"],
        }
        decision = {
            "action": "CLOSE",
            "message": None,
            "referenced_requirement_ids": list(self.ledger),
            "negotiation": None,
            "plan_approval": None,
            "final_baseline": baseline,
            "reason": "已完成实施并交付。",
        }
        with self.assertRaisesRegex(RuntimeError, "premature"):
            validate_simulator_decision(
                decision,
                scenario=self.scenario,
                current_requirements=self.ledger,
                approved_baseline={
                    "approved_plan": "最终批准的实施方案",
                    "allowed_target_ids": self.scenario["allowed_target_ids"],
                },
                scheme_changed_from_base=True,
                close_eligible=False,
                latest_agent_reply="方案已经交付",
            )
        validate_simulator_decision(
            decision,
            scenario=self.scenario,
            current_requirements=self.ledger,
            approved_baseline={
                "approved_plan": "最终批准的实施方案",
                "allowed_target_ids": self.scenario["allowed_target_ids"],
            },
            scheme_changed_from_base=True,
            close_eligible=True,
            latest_agent_reply="方案已经交付",
        )
        decision["final_baseline"]["confirmed_requirements"][0]["statement"] = "凭空改需求"
        with self.assertRaisesRegex(RuntimeError, "audited requirement ledger"):
            validate_simulator_decision(
                decision,
                scenario=self.scenario,
                current_requirements=self.ledger,
                approved_baseline={
                    "approved_plan": "最终批准的实施方案",
                    "allowed_target_ids": self.scenario["allowed_target_ids"],
                },
                scheme_changed_from_base=True,
                close_eligible=True,
                latest_agent_reply="方案已经交付",
            )

    def test_approved_negotiation_is_audited_and_updates_only_named_requirement(self) -> None:
        decision = {
            "action": "RESPOND",
            "message": "可以，用浅灰米瓷砖替代。",
            "referenced_requirement_ids": ["req_04"],
            "negotiation": {
                "decision": "APPROVE",
                "agent_proposal_excerpt": "改为浅灰米瓷砖",
                "affected_requirement_ids": ["req_04"],
                "resulting_requirements": [
                    {"requirement_id": "req_04", "statement": "吊顶克制，地面改用浅灰米瓷砖"}
                ],
            },
            "plan_approval": None,
            "final_baseline": None,
            "reason": "接受了有证据的局部替代。",
        }
        validate_simulator_decision(
            decision,
            scenario=self.scenario,
            current_requirements=self.ledger,
            approved_baseline=None,
            scheme_changed_from_base=False,
            close_eligible=False,
            latest_agent_reply="现有木地板不足，建议改为浅灰米瓷砖，是否接受？",
        )
        updated = apply_approved_negotiation(self.ledger, decision)
        self.assertEqual(updated["req_04"], "吊顶克制，地面改用浅灰米瓷砖")
        self.assertEqual(updated["req_01"], self.ledger["req_01"])

    def test_first_plan_approval_cannot_be_backfilled_after_implementation(self) -> None:
        decision = {
            "action": "RESPOND",
            "message": "我确认这个方案，请继续。",
            "referenced_requirement_ids": list(self.ledger),
            "negotiation": None,
            "plan_approval": {
                "agent_plan_excerpt": "完整实施方案",
                "approved_plan": "完整实施方案",
                "allowed_target_ids": self.scenario["allowed_target_ids"],
            },
            "final_baseline": None,
            "reason": "批准实施前规划。",
        }
        with self.assertRaisesRegex(RuntimeError, "cannot be created after implementation"):
            validate_simulator_decision(
                decision,
                scenario=self.scenario,
                current_requirements=self.ledger,
                approved_baseline=None,
                scheme_changed_from_base=True,
                close_eligible=False,
                latest_agent_reply="这是完整实施方案，我已经实施完成。",
            )

    def test_plain_fact_response_is_grounded_from_the_ledger(self) -> None:
        decision = {
            "action": "RESPOND",
            "message": "我希望整体安静一些。",
            "referenced_requirement_ids": ["req_01"],
            "negotiation": None,
            "plan_approval": None,
            "final_baseline": None,
            "reason": "回答范围问题。",
        }
        validate_simulator_decision(
            decision,
            scenario=self.scenario,
            current_requirements=self.ledger,
            approved_baseline=None,
            scheme_changed_from_base=False,
            close_eligible=False,
            latest_agent_reply="这次只做哪里？",
        )
        grounded = ground_plain_fact_response(decision, self.ledger)
        self.assertEqual(grounded["simulator_raw_message"], "我希望整体安静一些。")
        self.assertIn(self.ledger["req_01"], grounded["message"])

        decision["referenced_requirement_ids"] = []
        with self.assertRaisesRegex(RuntimeError, "direct Agent question"):
            validate_simulator_decision(
                decision,
                scenario=self.scenario,
                current_requirements=self.ledger,
                approved_baseline=None,
                scheme_changed_from_base=False,
                close_eligible=False,
                latest_agent_reply="这次只做哪里？",
            )

    def test_simulator_payload_contains_no_image_or_render_evidence(self) -> None:
        captured = {}

        class FakeSimulator:
            def json_response(self, **kwargs):
                captured.update(kwargs["payload"])
                return {
                    "action": "RESPOND",
                    "message": OutcomeUserSimulatorTests.ledger["req_02"],
                    "referenced_requirement_ids": ["req_02"],
                    "negotiation": None,
                    "plan_approval": None,
                    "final_baseline": None,
                    "reason": "尚未交付。",
                }

        simulate_user_turn(
            FakeSimulator(),
            scenario=self.scenario,
            transcript=[
                {"role": "user", "content": self.scenario["initial_message"]},
                {"role": "assistant", "content": "我需要先确认风格。"},
            ],
            current_requirements=self.ledger,
            approved_baseline=None,
            disclosed_requirement_ids={"req_02"},
            close_eligible=False,
            delivery_signals={"scheme_changed_from_base": False},
        )
        serialized = str(captured).lower()
        self.assertNotIn("image", serialized)
        self.assertNotIn("render_evidence", serialized)

    def test_grader_packet_uses_close_baseline_not_reference_plan(self) -> None:
        final_baseline = {
            "confirmed_requirements": [
                {"requirement_id": key, "statement": value}
                for key, value in self.ledger.items()
            ],
            "approved_plan": "互动后批准的可实施方案",
            "allowed_target_ids": self.scenario["allowed_target_ids"][:1],
        }
        provenance = {
            "source": "deepseek_user_simulator_close",
            "simulator_model": "deepseek-v4-flash",
            "close_token": "CLOSE",
            "close_decision_index": 3,
            "initial_message": self.scenario["initial_message"],
            "negotiation_log": [],
            "plan_approval_log": [{"turn": 2}],
        }
        packet = build_evidence_packet(
            scenario=self.scenario,
            final_baseline=final_baseline,
            baseline_provenance=provenance,
            design_run_id="run-1",
            base_version_id="v1",
            final_version_id="v2",
            base_scheme={"assignments": []},
            final_scheme={"assignments": []},
            tool_calls=[],
            render_evidence=[],
            validator_passed=True,
            final_report="已交付",
        )
        self.assertEqual(packet["approved_plan"], "互动后批准的可实施方案")
        self.assertNotEqual(packet["approved_plan"], self.scenario["reference_plan"])
        self.assertEqual(packet["allowed_target_ids"], self.scenario["allowed_target_ids"][:1])
        self.assertEqual(packet["baseline_provenance"], provenance)


if __name__ == "__main__":
    unittest.main()
