"""Text-only DeepSeek user simulator for interactive outcome evaluation."""

from __future__ import annotations

import json
import os
from typing import Any

import httpx
from openai import OpenAI


DEEPSEEK_BASE_URL = "https://api.deepseek.com"
DEEPSEEK_SIMULATOR_MODEL = "deepseek-v4-flash"


class DeepSeekOutcomeSimulator:
    """DeepSeek V4 Flash client with thinking disabled and strict JSON retries."""

    def __init__(self, timeout: float) -> None:
        api_key = os.getenv("EVAL_DEEPSEEK_API_KEY") or os.getenv("DEEPSEEK_API_KEY", "")
        if not api_key:
            raise RuntimeError("EVAL_DEEPSEEK_API_KEY or DEEPSEEK_API_KEY is required")
        base_url = os.getenv("EVAL_DEEPSEEK_BASE_URL", DEEPSEEK_BASE_URL).rstrip("/")
        if base_url not in {DEEPSEEK_BASE_URL, f"{DEEPSEEK_BASE_URL}/v1"}:
            raise RuntimeError(
                "EVAL_DEEPSEEK_BASE_URL must use the official https://api.deepseek.com endpoint"
            )
        proxy = os.getenv("EVAL_DEEPSEEK_PROXY") or None
        self.http_client = httpx.Client(proxy=proxy, trust_env=False, timeout=timeout)
        self.client = OpenAI(
            api_key=api_key,
            base_url=base_url,
            http_client=self.http_client,
            timeout=timeout,
        )
        self.model = DEEPSEEK_SIMULATOR_MODEL

    def close(self) -> None:
        self.http_client.close()

    def json_response(
        self,
        *,
        instructions: str,
        payload: dict[str, Any],
        max_output_tokens: int = 1800,
    ) -> dict[str, Any]:
        last_error: Exception | None = None
        for attempt in range(2):
            retry_note = (
                "\n上次输出无法解析。请缩短文字并只输出完整 JSON。" if attempt else ""
            )
            response = self.client.chat.completions.create(
                model=self.model,
                messages=[
                    {"role": "system", "content": instructions + retry_note},
                    {"role": "user", "content": json.dumps(payload, ensure_ascii=False)},
                ],
                max_tokens=max_output_tokens,
                response_format={"type": "json_object"},
                extra_body={"thinking": {"type": "disabled"}},
            )
            content = response.choices[0].message.content
            if not content:
                last_error = RuntimeError("DeepSeek simulator returned no content")
                continue
            try:
                return json.loads(content)
            except json.JSONDecodeError as error:
                last_error = error
        raise RuntimeError(f"DeepSeek simulator returned invalid JSON twice: {last_error}")


def _requirement_map(scenario: dict[str, Any]) -> dict[str, str]:
    return {
        item["requirement_id"]: item["statement"]
        for item in scenario["requirement_facts"]
    }


def validate_simulator_decision(
    decision: dict[str, Any],
    *,
    scenario: dict[str, Any],
    current_requirements: dict[str, str],
    approved_baseline: dict[str, Any] | None,
    scheme_changed_from_base: bool,
    close_eligible: bool,
    latest_agent_reply: str,
) -> dict[str, Any]:
    """Validate grounding, negotiation evidence and the final baseline."""

    required_keys = {
        "action",
        "message",
        "referenced_requirement_ids",
        "negotiation",
        "plan_approval",
        "final_baseline",
        "reason",
    }
    if set(decision) != required_keys:
        raise RuntimeError(f"JSON keys must be exactly {sorted(required_keys)}")
    if decision["action"] not in {"RESPOND", "CLOSE"}:
        raise RuntimeError("action must be RESPOND or CLOSE")
    if not isinstance(decision["reason"], str) or not decision["reason"].strip():
        raise RuntimeError("reason must be a non-empty string")

    valid_ids = set(_requirement_map(scenario))
    references = decision["referenced_requirement_ids"]
    if not isinstance(references, list) or not all(isinstance(item, str) for item in references):
        raise RuntimeError("referenced_requirement_ids must be a string array")
    if len(references) != len(set(references)) or not set(references) <= valid_ids:
        raise RuntimeError("referenced_requirement_ids contain duplicates or unknown IDs")

    negotiation = decision["negotiation"]
    if negotiation is not None:
        if not isinstance(negotiation, dict) or set(negotiation) != {
            "decision",
            "agent_proposal_excerpt",
            "affected_requirement_ids",
            "resulting_requirements",
        }:
            raise RuntimeError("negotiation has an invalid shape")
        if negotiation["decision"] not in {"APPROVE", "REJECT"}:
            raise RuntimeError("negotiation decision must be APPROVE or REJECT")
        excerpt = negotiation["agent_proposal_excerpt"]
        if not isinstance(excerpt, str) or not excerpt.strip() or excerpt not in latest_agent_reply:
            raise RuntimeError("negotiation excerpt must be copied from the latest Agent reply")
        affected = negotiation["affected_requirement_ids"]
        if (
            not isinstance(affected, list)
            or not affected
            or len(affected) != len(set(affected))
            or not set(affected) <= valid_ids
        ):
            raise RuntimeError("negotiation affected_requirement_ids are invalid")
        resulting = negotiation["resulting_requirements"]
        if not isinstance(resulting, list):
            raise RuntimeError("resulting_requirements must be an array")
        if negotiation["decision"] == "REJECT" and resulting:
            raise RuntimeError("rejected negotiation cannot change requirements")
        resulting_ids: set[str] = set()
        for item in resulting:
            if not isinstance(item, dict) or set(item) != {"requirement_id", "statement"}:
                raise RuntimeError("resulting requirement has an invalid shape")
            requirement_id = item["requirement_id"]
            statement = item["statement"]
            if requirement_id not in set(affected) or requirement_id in resulting_ids:
                raise RuntimeError("resulting requirement ID is duplicated or not affected")
            if not isinstance(statement, str) or not statement.strip():
                raise RuntimeError("resulting requirement statement must be non-empty")
            resulting_ids.add(requirement_id)

    plan_approval = decision["plan_approval"]
    if plan_approval is not None:
        if not isinstance(plan_approval, dict) or set(plan_approval) != {
            "agent_plan_excerpt",
            "approved_plan",
            "allowed_target_ids",
        }:
            raise RuntimeError("plan_approval has an invalid shape")
        excerpt = plan_approval["agent_plan_excerpt"]
        if not isinstance(excerpt, str) or not excerpt.strip() or excerpt not in latest_agent_reply:
            raise RuntimeError("plan approval excerpt must be copied from the latest Agent reply")
        if not isinstance(plan_approval["approved_plan"], str) or not plan_approval[
            "approved_plan"
        ].strip():
            raise RuntimeError("approved plan must be non-empty")
        target_ids = plan_approval["allowed_target_ids"]
        if (
            not isinstance(target_ids, list)
            or not target_ids
            or len(target_ids) != len(set(target_ids))
            or not set(target_ids) <= set(scenario["allowed_target_ids"])
        ):
            raise RuntimeError("approved plan target IDs are invalid or outside scope")
        if approved_baseline is None and scheme_changed_from_base:
            raise RuntimeError("the first plan approval cannot be created after implementation")
        if set(references) != valid_ids:
            raise RuntimeError("plan approval must account for every requirement ID")

    if decision["action"] == "RESPOND":
        if not isinstance(decision["message"], str) or not decision["message"].strip():
            raise RuntimeError("RESPOND requires a non-empty message")
        if decision["final_baseline"] is not None:
            raise RuntimeError("RESPOND requires final_baseline=null")
        if (
            negotiation is None
            and plan_approval is None
            and ("?" in latest_agent_reply or "？" in latest_agent_reply)
            and not references
        ):
            raise RuntimeError(
                "a direct Agent question requires at least one grounded requirement ID"
            )
        return decision

    if decision["message"] is not None:
        raise RuntimeError("CLOSE requires message=null")
    if negotiation is not None:
        raise RuntimeError("CLOSE cannot approve a new change in the same turn")
    if plan_approval is not None:
        raise RuntimeError("CLOSE cannot create or revise the approved plan")
    if approved_baseline is None:
        raise RuntimeError("CLOSE requires a plan baseline locked before implementation")
    if not close_eligible:
        raise RuntimeError("CLOSE is premature: no valid implemented Scheme is available")

    baseline = decision["final_baseline"]
    if not isinstance(baseline, dict) or set(baseline) != {
        "confirmed_requirements",
        "approved_plan",
        "allowed_target_ids",
    }:
        raise RuntimeError("CLOSE requires a complete final_baseline")
    requirements = baseline["confirmed_requirements"]
    if not isinstance(requirements, list) or len(requirements) != len(current_requirements):
        raise RuntimeError("final baseline must contain every requirement exactly once")
    resolved: dict[str, str] = {}
    for item in requirements:
        if not isinstance(item, dict) or set(item) != {"requirement_id", "statement"}:
            raise RuntimeError("final requirement has an invalid shape")
        requirement_id = item["requirement_id"]
        if requirement_id in resolved or requirement_id not in current_requirements:
            raise RuntimeError("final requirement ID is duplicated or unknown")
        if item["statement"] != current_requirements[requirement_id]:
            raise RuntimeError("final requirement does not match the audited requirement ledger")
        resolved[requirement_id] = item["statement"]
    if set(resolved) != set(current_requirements):
        raise RuntimeError("final baseline omits requirement IDs")
    if not isinstance(baseline["approved_plan"], str) or not baseline["approved_plan"].strip():
        raise RuntimeError("final baseline approved_plan must be non-empty")
    if baseline["approved_plan"] != approved_baseline["approved_plan"]:
        raise RuntimeError("final approved_plan differs from the locked plan baseline")
    target_ids = baseline["allowed_target_ids"]
    if (
        not isinstance(target_ids, list)
        or not target_ids
        or len(target_ids) != len(set(target_ids))
        or not set(target_ids) <= set(scenario["allowed_target_ids"])
    ):
        raise RuntimeError("final baseline target IDs are empty, duplicated, or outside scope")
    if target_ids != approved_baseline["allowed_target_ids"]:
        raise RuntimeError("final target IDs differ from the locked plan baseline")
    return decision


def simulate_user_turn(
    simulator: DeepSeekOutcomeSimulator,
    *,
    scenario: dict[str, Any],
    transcript: list[dict[str, str]],
    current_requirements: dict[str, str],
    approved_baseline: dict[str, Any] | None,
    disclosed_requirement_ids: set[str],
    close_eligible: bool,
    delivery_signals: dict[str, Any],
) -> dict[str, Any]:
    """Produce one grounded user turn. No image or image path enters this payload."""

    payload = {
        "scenario": {
            "scenario_id": scenario["scenario_id"],
            "initial_message": scenario["initial_message"],
            "requirements": scenario["requirement_facts"],
            "current_requirement_ledger": [
                {"requirement_id": key, "statement": value}
                for key, value in current_requirements.items()
            ],
            "reference_design_envelope": scenario["reference_plan"],
            "maximum_allowed_target_ids": scenario["allowed_target_ids"],
        },
        "already_disclosed_requirement_ids": sorted(disclosed_requirement_ids),
        "conversation": transcript,
        "delivery_signals": {**delivery_signals, "close_eligible": close_eligible},
        "output_json_contract": {
            "action": "RESPOND or CLOSE",
            "message": "ordinary user message for RESPOND; null for CLOSE",
            "referenced_requirement_ids": ["IDs used by this decision"],
            "negotiation": {
                "decision": "APPROVE or REJECT",
                "agent_proposal_excerpt": "exact excerpt from latest Agent reply",
                "affected_requirement_ids": ["requirement ID"],
                "resulting_requirements": [
                    {"requirement_id": "ID", "statement": "new final statement"}
                ],
            },
            "plan_approval": {
                "agent_plan_excerpt": "exact excerpt from latest Agent reply",
                "approved_plan": "approved pre-implementation plan or audited revision",
                "allowed_target_ids": ["approved target IDs within maximum scope"],
            },
            "final_baseline": {
                "confirmed_requirements": [
                    {"requirement_id": "ID", "statement": "ledger statement"}
                ],
                "approved_plan": "the final plan the user asked the Agent to deliver",
                "allowed_target_ids": ["approved target IDs within maximum scope"],
            },
            "reason": "one short audit sentence",
        },
    }
    instructions = (
        "你是住宅设计评估中的模拟用户，不是设计师也不是评分员。你只有文字能力，绝不能判断图片、"
        "渲染好坏或视觉是否达标。只使用 scenario 的需求，不得创造新偏好。初始消息只是感觉；Agent"
        "最高优先级规则：如果最新 Agent 回复包含需求问句或问号，必须直接回答该问题，至少选择一个"
        "相关 referenced_requirement_id，绝不能催 Agent 先给规划，也不能把问句称为占位符。"
        "询问时再披露直接相关需求。普通澄清/纠错回复只在 referenced_requirement_ids 中选择真正"
        "直接回答问题的少量 ID；Runner 会用账本原文生成实际用户消息，所以不得为了自然感多选事实。"
        "如果没有对应需求事实，可以用普通用户口吻说不确定且 referenced_requirement_ids=[]。"
        "Agent 给出规划时，要检查它是否覆盖当前需求；缺项或冲突时继续"
        "RESPOND，不得为了帮助 Agent 而替它写设计。Agent 若说明素材库限制并提出局部替代，你可以"
        "在仍满足需求时 APPROVE，否则 REJECT。negotiation 只能引用最新 Agent 回复中的原文片段；"
        "如果替代只改具体资产、不改变高层需求，resulting_requirements 可为空。若改变需求，必须列出"
        "变更后的 affected requirement。普通澄清不属于 negotiation，填 null。"
        "当 Agent 给出可实施规划并请求确认时，用 RESPOND 表达批准，同时填写 plan_approval，引用最新"
        "Agent 规划原文并锁定批准方案与目标范围；不能在 Agent 已经改动 Scheme 后才第一次补做方案"
        "批准。普通澄清时 plan_approval=null。已经锁定方案后若批准替代，需要同时用 plan_approval"
        "给出更新后的完整方案快照。只有 Agent 已完成实施并交付最终结果，且"
        "delivery_signals.close_eligible=true 时才能 CLOSE。"
        "规划待审批、替代待审批、正在实施、等待用户允许执行时都必须 RESPOND。CLOSE 不是满意评分，"
        "只表示交互结束；此时 final_baseline 必须逐项照抄 current_requirement_ledger，并用 approved_plan"
        "原样复述 Runner 提供的 locked_approved_baseline，目标 ID 只能来自 maximum_allowed_target_ids。"
        "填写 plan_approval 时 referenced_requirement_ids 必须包含全部需求 ID。RESPOND 时"
        "final_baseline 必须为 null；CLOSE 时 message、negotiation 与 plan_approval 必须为 null。"
        "只输出符合契约的 JSON，不要 Markdown。"
    )
    payload["locked_approved_baseline"] = approved_baseline
    latest_agent_reply = next(
        item["content"] for item in reversed(transcript) if item["role"] == "assistant"
    )
    last_error: Exception | None = None
    for attempt in range(2):
        decision = simulator.json_response(instructions=instructions, payload=payload)
        try:
            validated = validate_simulator_decision(
                decision,
                scenario=scenario,
                current_requirements=current_requirements,
                approved_baseline=approved_baseline,
                scheme_changed_from_base=bool(
                    delivery_signals.get("scheme_changed_from_base")
                ),
                close_eligible=close_eligible,
                latest_agent_reply=latest_agent_reply,
            )
            return ground_plain_fact_response(validated, current_requirements)
        except RuntimeError as error:
            last_error = error
            if attempt == 0:
                payload["validation_retry"] = f"上次输出无效：{error}。严格修正后重答。"
    raise RuntimeError(f"simulator response invalid twice: {last_error}")


def ground_plain_fact_response(
    decision: dict[str, Any], current_requirements: dict[str, str]
) -> dict[str, Any]:
    """Resolve selected fact IDs into the exact user message sent to the Agent."""

    if (
        decision["action"] != "RESPOND"
        or decision["negotiation"] is not None
        or decision["plan_approval"] is not None
        or not decision["referenced_requirement_ids"]
    ):
        return decision
    grounded = dict(decision)
    grounded["simulator_raw_message"] = decision["message"]
    statements = [
        current_requirements[requirement_id]
        for requirement_id in decision["referenced_requirement_ids"]
    ]
    grounded["message"] = "我确认的相关要求是：\n- " + "\n- ".join(statements)
    return grounded


def apply_approved_negotiation(
    current_requirements: dict[str, str], decision: dict[str, Any]
) -> dict[str, str]:
    """Return a new ledger after an explicitly approved user negotiation."""

    updated = dict(current_requirements)
    negotiation = decision.get("negotiation")
    if not negotiation or negotiation["decision"] != "APPROVE":
        return updated
    for item in negotiation["resulting_requirements"]:
        updated[item["requirement_id"]] = item["statement"]
    return updated
