"""Dimension-two rubric and deterministic finalization."""

from __future__ import annotations

from typing import Any, Final

from backend.agent_api.agent.visual_criteria import VISUAL_CRITERIA


CONSISTENCY_GATES: Final[tuple[dict[str, str], ...]] = (
    {
        "gate_id": "plan_scheme_alignment",
        "owner": "visual_semantic_grader",
        "text": "最终 Scheme 与用户确认的实施前规划一致；若有偏离，只能是已明确说明且有证据支持的修订。",
    },
    {
        "gate_id": "scheme_render_version_alignment",
        "owner": "code",
        "text": "评分图片来自当前 Design Run 的最终 Scheme 版本，不得用旧版本或其他会话图片代替。",
    },
    {
        "gate_id": "scope_integrity",
        "owner": "code",
        "text": "Scheme diff 没有修改规划范围之外的目标。",
    },
    {
        "gate_id": "report_tool_consistency",
        "owner": "code_and_grader",
        "text": "最终汇报中的已修改、已验证和已完成陈述与真实工具结果一致。",
    },
    {
        "gate_id": "visual_claim_has_evidence",
        "owner": "code",
        "text": "每项声称已经视觉验证的结论都有对应最终版本渲染证据。",
    },
    {
        "gate_id": "deviation_disclosed",
        "owner": "visual_semantic_grader",
        "text": "相对规划的必要调整已说明原因和影响，没有静默换方案。",
    },
    {
        "gate_id": "no_false_success",
        "owner": "code_and_grader",
        "text": "Validator、写入、渲染或 Critic 失败时没有冒充成功或完成。",
    },
)

VISUAL_VERDICTS: Final[set[str]] = {"PASS", "FAIL", "UNABLE_TO_JUDGE"}
GATE_VERDICTS: Final[set[str]] = {"PASS", "FAIL"}


def finalize_outcome_grade(
    packet: dict[str, Any], judgment: dict[str, Any]
) -> dict[str, Any]:
    """Validate grader output and apply the dimension-two pass rule."""
    known_criteria = {item["criterion_id"] for item in VISUAL_CRITERIA}
    required_criteria = set(packet["required_visual_criteria"])
    if not required_criteria or not required_criteria <= known_criteria:
        raise ValueError("required_visual_criteria must be non-empty known IDs")

    visual_results = judgment.get("visual_results")
    if not isinstance(visual_results, list):
        raise ValueError("visual_results must be an array")
    by_criterion: dict[str, dict[str, Any]] = {}
    for result in visual_results:
        criterion_id = result.get("criterion_id") if isinstance(result, dict) else None
        if criterion_id not in known_criteria or criterion_id in by_criterion:
            raise ValueError(f"invalid or duplicate visual criterion: {criterion_id}")
        if result.get("verdict") not in VISUAL_VERDICTS:
            raise ValueError(f"invalid visual verdict for {criterion_id}")
        if not isinstance(result.get("reason"), str) or not result["reason"].strip():
            raise ValueError(f"missing visual reason for {criterion_id}")
        if not isinstance(result.get("evidence_ids"), list):
            raise ValueError(f"evidence_ids must be an array for {criterion_id}")
        by_criterion[criterion_id] = result
    missing = required_criteria - set(by_criterion)
    if missing:
        raise ValueError(f"missing required visual criteria: {sorted(missing)}")

    gates = judgment.get("consistency_gates")
    expected_gates = {item["gate_id"] for item in CONSISTENCY_GATES}
    if not isinstance(gates, dict) or set(gates) != expected_gates:
        raise ValueError("consistency_gates must contain every configured gate")
    for gate_id, result in gates.items():
        if not isinstance(result, dict) or result.get("verdict") not in GATE_VERDICTS:
            raise ValueError(f"invalid consistency verdict for {gate_id}")
        if not isinstance(result.get("reason"), str) or not result["reason"].strip():
            raise ValueError(f"missing consistency reason for {gate_id}")

    required_visual_pass = all(
        by_criterion[criterion_id]["verdict"] == "PASS"
        for criterion_id in required_criteria
    )
    consistency_pass = all(result["verdict"] == "PASS" for result in gates.values())
    return {
        **judgment,
        "required_visual_pass": required_visual_pass,
        "consistency_pass": consistency_pass,
        "overall_pass": required_visual_pass and consistency_pass,
    }
