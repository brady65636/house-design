"""Run one production-faithful natural-language user simulation and CLOSE audit.

The production Design Agent is used unchanged through FastAPI. DeepSeek receives
no reference plan, requirement IDs, target IDs, images, or final Scheme. It acts
as a natural user until delivery, then a fresh DeepSeek call extracts the final
requested plan from the public transcript alone.
"""

from __future__ import annotations

import json
import os
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any
from uuid import uuid4

PROJECT_ROOT = Path(__file__).resolve().parents[2]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from evals.outcome_dimension.run_eval import AgentApiClient, load_local_env, save_json
from evals.outcome_dimension.user_simulator import DeepSeekOutcomeSimulator


HERE = Path(__file__).resolve().parent
RESULTS_DIR = HERE / "natural_close_probes"
INITIAL_MESSAGE = (
    "我想把横厅做得明亮、安静、自然一点，最好有一点若有若无的雾感，但不要显得花。"
    "你先看看现状和现有素材，先和我确认方案再动手；如果素材不能原样实现，请把影响说清楚，"
    "再问我能不能接受局部替代。"
)


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def validate_exact_keys(value: dict[str, Any], keys: set[str], label: str) -> None:
    if set(value) != keys:
        raise RuntimeError(f"{label} keys must be exactly {sorted(keys)}")


def generate_private_profile(simulator: DeepSeekOutcomeSimulator) -> dict[str, Any]:
    """Lock a plausible user before the Agent says anything."""

    profile = simulator.json_response(
        instructions=(
            "你要在对话开始前生成并锁定一个真实住宅用户画像。只能依据 initial_message，"
            "可以合理形成用户尚未说出口的个人偏好，也要保留一些没有想过的问题。画像之后不得"
            "根据 Agent 方案或成品反向修改。不要生成具体资产 ID、墙面 ID 或专业施工方案。"
            "只输出严格 JSON。"
        ),
        payload={
            "initial_message": INITIAL_MESSAGE,
            "output_json_contract": {
                "persona": "one short user description",
                "stable_preferences": ["private preference"],
                "hard_rejections": ["private rejection"],
                "negotiable_preferences": ["preference that may change after explanation"],
                "undecided_topics": ["topic the user genuinely has not decided"],
            },
        },
        max_output_tokens=700,
    )
    validate_exact_keys(
        profile,
        {
            "persona",
            "stable_preferences",
            "hard_rejections",
            "negotiable_preferences",
            "undecided_topics",
        },
        "profile",
    )
    return profile


def simulate_natural_user_turn(
    simulator: DeepSeekOutcomeSimulator,
    *,
    profile: dict[str, Any],
    transcript: list[dict[str, str]],
    delivery_signals: dict[str, Any],
) -> dict[str, Any]:
    payload = {
        "private_user_profile_locked_before_conversation": profile,
        "public_conversation": transcript,
        "delivery_signals": delivery_signals,
        "output_json_contract": {
            "action": "RESPOND or CLOSE",
            "message": "natural user reply for RESPOND; null for CLOSE",
            "reason": "one short audit sentence",
        },
    }
    instructions = (
        "你是正在和住宅 Design Agent 真实交流的普通用户，不是 grader。自然回复，不要提需求 ID、"
        "JSON、评测或隐藏画像。保持 private profile 稳定，但用户原先没想过的事项可以在被问到时"
        "形成一次选择，之后保持一致。Agent 给出实施前方案时，按普通用户方式批准、拒绝或要求修改。"
        "如果 Agent 在实施中明确说明素材/结构限制并提出替代，判断是否接受；不能把未提出的限制"
        "或替代方案自己编出来。只有 Agent 已经实际实施并给出最终交付，而且 delivery_signals 中"
        "scheme_changed_from_base=true、validator_passed=true，才可 CLOSE。方案待确认、等待执行许可、"
        "仍在实施或仍问问题时必须 RESPOND。如果最新回复明确说渲染器离线、视觉验证未完成、仍需"
        "重试或还有剩余步骤，也必须 RESPOND 要求继续完成，不能把 Scheme 写入等同最终交付。"
        "CLOSE 只结束对话，不在此时评价图片。只输出严格 JSON。"
    )
    decision = simulator.json_response(
        instructions=instructions,
        payload=payload,
        max_output_tokens=700,
    )
    required_keys = {"action", "message", "reason"}
    if not required_keys <= set(decision):
        raise RuntimeError(f"user decision requires keys {sorted(required_keys)}")
    extra = {key: value for key, value in decision.items() if key not in required_keys}
    if decision["action"] not in {"RESPOND", "CLOSE"}:
        raise RuntimeError("user action must be RESPOND or CLOSE")
    if not isinstance(decision["reason"], str) or not decision["reason"].strip():
        raise RuntimeError("user reason must be non-empty")
    if decision["action"] == "RESPOND":
        if not isinstance(decision["message"], str) or not decision["message"].strip():
            raise RuntimeError("RESPOND requires a message")
    else:
        if decision["message"] is not None:
            raise RuntimeError("CLOSE requires message=null")
        if not (
            delivery_signals["scheme_changed_from_base"]
            and delivery_signals["validator_passed"]
        ):
            raise RuntimeError("DeepSeek attempted CLOSE before a valid implementation")
    normalized = {key: decision[key] for key in ("action", "message", "reason")}
    if extra:
        normalized["simulator_extra_fields"] = extra
    return normalized


def extract_close_summary(
    simulator: DeepSeekOutcomeSimulator,
    transcript: list[dict[str, str]],
) -> dict[str, Any]:
    """Fresh extraction from public natural-language turns; no profile or answer key."""

    summary = simulator.json_response(
        instructions=(
            "你是同一位用户，在对话结束时整理最终要求，但只能使用 public_conversation 中公开说过、"
            "明确批准或授权 Agent 决定的内容。不得读取隐藏画像，不得根据成品反推要求。区分：最终"
            "生效要求、已批准替代、明确拒绝项、Agent 提过但用户没有批准的提议。旧方案被后续批准"
            "替代后不能继续列为最终要求。每一项都必须给出最小充分 source_turn_ids；无法确定时写入"
            "uncertain_items，不能猜。只输出严格 JSON。"
        ),
        payload={
            "public_conversation": transcript,
            "output_json_contract": {
                "action": "CLOSE",
                "final_requested_plan": "complete natural-language final plan",
                "effective_requirements": [
                    {"statement": "final requirement", "source_turn_ids": ["U1"]}
                ],
                "approved_substitutions": [
                    {
                        "from": "original choice",
                        "to": "approved replacement",
                        "reason": "why",
                        "source_turn_ids": ["A4", "U5"],
                    }
                ],
                "rejected_or_unapproved_items": [
                    {"statement": "not part of final plan", "source_turn_ids": ["A4", "U5"]}
                ],
                "agent_discretion": [
                    {"statement": "area delegated to Agent", "source_turn_ids": ["U3"]}
                ],
                "uncertain_items": ["cannot be determined from transcript"],
            },
        },
        max_output_tokens=2200,
    )
    validate_exact_keys(
        summary,
        {
            "action",
            "final_requested_plan",
            "effective_requirements",
            "approved_substitutions",
            "rejected_or_unapproved_items",
            "agent_discretion",
            "uncertain_items",
        },
        "CLOSE summary",
    )
    if summary["action"] != "CLOSE":
        raise RuntimeError("summary action must be CLOSE")
    return summary


def main() -> int:
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")
    load_local_env(PROJECT_ROOT / ".env")
    simulator = DeepSeekOutcomeSimulator(180)
    api = AgentApiClient(
        os.getenv("EVAL_AGENT_API_URL", "http://127.0.0.1:8000"),
        os.getenv("EVAL_AGENT_API_TOKEN") or os.getenv("AGENT_API_TOKEN"),
        900,
    )
    stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    output_dir = RESULTS_DIR / stamp
    output_dir.mkdir(parents=True, exist_ok=False)
    record: dict[str, Any] = {
        "probe_id": f"natural_close_{uuid4().hex}",
        "started_at": utc_now(),
        "initial_message": INITIAL_MESSAGE,
        "private_profile": None,
        "thread_id": None,
        "design_run_id": None,
        "base_version_id": None,
        "final_version_id": None,
        "transcript": [],
        "simulator_decisions": [],
        "close_summary": None,
        "error": None,
    }
    try:
        profile = generate_private_profile(simulator)
        record["private_profile"] = profile
        session = api.create_fresh_session(f"natural-close-probe:{record['probe_id'][-8:]}")
        record["thread_id"] = session["thread_id"]
        record["design_run_id"] = session["design_run_id"]
        record["base_version_id"] = session["current_version_id"]
        user_message = INITIAL_MESSAGE

        for turn in range(1, 11):
            user_turn_id = f"U{turn}"
            record["transcript"].append(
                {"turn_id": user_turn_id, "role": "user", "content": user_message}
            )
            response = api.chat(session["thread_id"], user_message)
            assistant_turn_id = f"A{turn}"
            agent_reply = str(response.get("reply") or "")
            record["transcript"].append(
                {"turn_id": assistant_turn_id, "role": "assistant", "content": agent_reply}
            )
            run = api.design_run(session["design_run_id"])
            current_version_id = str(run["current_version_id"])
            record["final_version_id"] = current_version_id
            scheme_changed = current_version_id != str(record["base_version_id"])
            # Production update_scheme only persists Validator-passing Schemes.
            delivery_signals = {
                "scheme_changed_from_base": scheme_changed,
                "validator_passed": scheme_changed,
                "latest_agent_turn_id": assistant_turn_id,
            }
            decision = simulate_natural_user_turn(
                simulator,
                profile=profile,
                transcript=record["transcript"],
                delivery_signals=delivery_signals,
            )
            record["simulator_decisions"].append(
                {"after_turn_id": assistant_turn_id, **decision}
            )
            save_json(output_dir / "probe.json", record)
            if decision["action"] == "CLOSE":
                record["close_summary"] = extract_close_summary(
                    simulator, record["transcript"]
                )
                break
            user_message = decision["message"]
        else:
            raise RuntimeError("probe reached 10 Agent turns without CLOSE")

        history = api.history(session["thread_id"])
        save_json(output_dir / "product_history.json", history)
    except Exception as error:  # noqa: BLE001
        record["error"] = f"{type(error).__name__}: {error}"
    finally:
        record["finished_at"] = utc_now()
        save_json(output_dir / "probe.json", record)
        simulator.close()
    print(str(output_dir.resolve()))
    if record["error"]:
        print(record["error"], file=sys.stderr)
        return 1
    print(json.dumps(record["close_summary"], ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
