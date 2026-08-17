"""Run dimension two with natural dialogue as the grader's authority.

DeepSeek only plays the user and emits RESPOND/CLOSE. It does not summarize the
final plan. The unchanged production Design Agent speaks natural language. The
Codex grader receives the full numbered dialogue together with Scheme, tools and
render evidence, and directly judges the final approved intent versus outcome.
"""

from __future__ import annotations

import argparse
import json
import os
import sys
from datetime import datetime
from pathlib import Path
from typing import Any
from uuid import uuid4

PROJECT_ROOT = Path(__file__).resolve().parents[2]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from evals.outcome_dimension.probe_natural_close import (
    generate_private_profile,
    simulate_natural_user_turn,
    utc_now,
)
from evals.outcome_dimension.run_eval import (
    AgentApiClient,
    DEFAULT_DATASET,
    DEFAULT_RESULTS_DIR,
    RenderBridgeClient,
    SCENE_MANIFEST,
    assignment_map,
    collect_render_evidence,
    compact_history,
    critic_review_from_trace,
    extract_tool_trace,
    load_dataset,
    load_local_env,
    save_json,
    scheme_diff,
    select_scenarios,
    validate_final_scheme,
)
from evals.outcome_dimension.rubric import finalize_outcome_grade
from evals.outcome_dimension.user_simulator import (
    DEEPSEEK_SIMULATOR_MODEL,
    DeepSeekOutcomeSimulator,
)


def numbered_dialogue(transcript: list[dict[str, str]]) -> list[dict[str, str]]:
    return [
        {
            "turn_id": item["turn_id"],
            "role": item["role"],
            "content": item["content"],
        }
        for item in transcript
    ]


def _scene_target_rooms() -> tuple[dict[str, str], dict[str, list[str]]]:
    target_to_room: dict[str, str] = {}
    room_to_targets: dict[str, list[str]] = {}
    spaces = [
        *SCENE_MANIFEST.get("rooms", []),
        *SCENE_MANIFEST.get("balconies", []),
    ]
    for space in spaces:
        room_id = space.get("id")
        if not isinstance(room_id, str) or not room_id:
            continue
        target_ids = [
            *space.get("wall_face_ids", []),
            *space.get("surface_ids", {}).values(),
        ]
        room_to_targets[room_id] = []
        for target_id in target_ids:
            if not isinstance(target_id, str) or not target_id:
                continue
            target_to_room[target_id] = room_id
            room_to_targets[room_id].append(target_id)
    return target_to_room, room_to_targets


TARGET_TO_ROOM, ROOM_TO_TARGETS = _scene_target_rooms()


def _tool_result_object(call: dict[str, Any]) -> dict[str, Any] | None:
    result = call.get("result")
    if isinstance(result, dict):
        return result
    if not isinstance(result, str):
        return None
    try:
        decoded = json.loads(result)
    except json.JSONDecodeError:
        return None
    return decoded if isinstance(decoded, dict) else None


def _successful_final_update_targets(
    tool_calls: list[dict[str, Any]], final_scheme: dict[str, Any]
) -> list[str]:
    """Return targets whose last successful write is represented by final Scheme.

    Comparing the last successful write with final Scheme keeps no-op writes (which
    are essential when the approved design already matches the base) while excluding
    temporary experiments that were later reverted.
    """

    last_writes: dict[str, dict[str, Any]] = {}
    for call in tool_calls:
        if call.get("name") != "update_scheme":
            continue
        args = call.get("args")
        result = call.get("result")
        if not isinstance(args, dict) or not isinstance(result, str):
            continue
        target_id = args.get("target_id")
        asset_id = args.get("asset_id")
        if (
            not isinstance(target_id, str)
            or not isinstance(asset_id, str)
            or not result.startswith("修改scheme成功")
        ):
            continue
        last_writes[target_id] = args

    final_assignments = assignment_map(final_scheme)
    targets: list[str] = []
    for target_id, write in last_writes.items():
        assignment = final_assignments.get(target_id)
        if not assignment or assignment.get("asset_id") != write.get("asset_id"):
            continue
        if "parameters" in write and assignment.get("parameters") != write.get("parameters"):
            continue
        targets.append(target_id)
    return sorted(targets)


def _final_observations(
    tool_calls: list[dict[str, Any]], final_version_id: str
) -> dict[str, list[str]]:
    observed: dict[str, list[str]] = {}
    for call in tool_calls:
        if call.get("name") != "observe_room":
            continue
        result = _tool_result_object(call)
        if not result or result.get("status") != "ready":
            continue
        if str((result.get("scheme") or {}).get("schemeId")) != final_version_id:
            continue
        result_room_id = (result.get("room") or {}).get("id")
        args = call.get("args") if isinstance(call.get("args"), dict) else {}
        requested_room_id = args.get("room_id")
        if not isinstance(result_room_id, str) or result_room_id != requested_room_id:
            continue
        focus_ids = [
            target_id
            for target_id in args.get("focus_target_ids", [])
            if isinstance(target_id, str) and TARGET_TO_ROOM.get(target_id) == result_room_id
        ]
        observed.setdefault(result_room_id, [])
        observed[result_room_id].extend(focus_ids)
    return {
        room_id: list(dict.fromkeys(target_ids))
        for room_id, target_ids in observed.items()
    }


def derive_dynamic_capture_plan(
    *,
    scenario: dict[str, Any],
    tool_calls: list[dict[str, Any]],
    base_scheme: dict[str, Any],
    final_scheme: dict[str, Any],
    final_version_id: str,
) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    """Build post-CLOSE evidence targets from the executed final design.

    The dataset capture plan supplies only criterion intent. Room and target scope
    comes from successful final writes, net Scheme changes, and—only when neither
    exists—ready observations bound to the final Scheme version.
    """

    written_targets = _successful_final_update_targets(tool_calls, final_scheme)
    changed_targets = sorted(
        change["target_id"] for change in scheme_diff(base_scheme, final_scheme)
    )
    final_observations = _final_observations(tool_calls, final_version_id)
    executed_targets = sorted(set(written_targets) | set(changed_targets))
    unknown_targets = [target_id for target_id in executed_targets if target_id not in TARGET_TO_ROOM]
    if unknown_targets:
        raise RuntimeError(
            "cannot map executed targets to rooms: " + ", ".join(unknown_targets)
        )

    room_ids = sorted({TARGET_TO_ROOM[target_id] for target_id in executed_targets})
    source = "successful_final_writes_and_scheme_diff"
    if not room_ids:
        room_ids = sorted(final_observations)
        source = "final_version_ready_observations"
    if not room_ids:
        raise RuntimeError(
            "cannot derive final capture rooms from successful writes, Scheme diff, "
            "or final-version ready observations"
        )

    required_criteria = list(scenario["required_visual_criteria"])
    captures: list[dict[str, Any]] = []
    for room_id in room_ids:
        focus_target_ids = [
            target_id for target_id in executed_targets if TARGET_TO_ROOM[target_id] == room_id
        ]
        if not focus_target_ids:
            focus_target_ids = final_observations.get(room_id, [])
        if not focus_target_ids:
            focus_target_ids = ROOM_TO_TARGETS.get(room_id, [])
        captures.append(
            {
                "capture_id": f"final_room_{room_id}",
                "tool": "observe_room",
                "room_id": room_id,
                "focus_target_ids": list(dict.fromkeys(focus_target_ids)),
                "minimum_image_count": 3,
                "covers_criteria": required_criteria,
            }
        )

    static_requests_harmony = any(
        capture.get("tool") == "observe_home_harmony"
        for capture in scenario.get("capture_plan", [])
    )
    if len(room_ids) > 1 or static_requests_harmony:
        captures.append(
            {
                "capture_id": "final_home_harmony",
                "tool": "observe_home_harmony",
                "minimum_image_count": 3,
                "covers_criteria": required_criteria,
            }
        )

    provenance = {
        "kind": "post_close_execution_derived",
        "source": source,
        "successful_final_write_target_ids": written_targets,
        "net_changed_target_ids": changed_targets,
        "final_version_observed_room_ids": sorted(final_observations),
        "derived_room_ids": room_ids,
    }
    return captures, provenance


def validate_capture_room_alignment(
    capture_plan: list[dict[str, Any]], render_evidence: list[dict[str, Any]]
) -> None:
    """Fail closed if a room capture returns evidence for a different room."""

    for capture in capture_plan:
        if capture.get("tool") != "observe_room":
            continue
        expected_room_id = capture["room_id"]
        actual_room_ids = {
            item.get("room_id")
            for item in render_evidence
            if item.get("capture_id") == capture["capture_id"]
        }
        mismatches = sorted(
            room_id
            for room_id in actual_room_ids
            if isinstance(room_id, str) and room_id != expected_room_id
        )
        if mismatches:
            raise RuntimeError(
                f"capture {capture['capture_id']} requested {expected_room_id} "
                f"but returned {', '.join(mismatches)}"
            )


def build_direct_packet(
    *,
    scenario: dict[str, Any],
    transcript: list[dict[str, str]],
    infrastructure_recoveries: list[dict[str, Any]],
    design_run_id: str,
    base_version_id: str,
    final_version_id: str,
    base_scheme: dict[str, Any],
    final_scheme: dict[str, Any],
    tool_calls: list[dict[str, Any]],
    render_evidence: list[dict[str, Any]],
    capture_plan: list[dict[str, Any]],
    capture_plan_provenance: dict[str, Any],
    validator_passed: bool,
    final_report: str,
    close_decision: dict[str, Any],
) -> dict[str, Any]:
    return {
        "scenario_id": scenario["scenario_id"],
        "rubric_version": "outcome_dimension_v1",
        "grading_authority": {
            "kind": "full_natural_dialogue",
            "instruction": (
                "完整编号对话是最终用户要求、审批、替代、授权和未解决事项的唯一语义依据。"
                "直接结合后续 Scheme、工具轨迹与图片评分；没有独立的 approved_plan 摘要。"
            ),
        },
        "conversation": numbered_dialogue(transcript),
        "conversation_stop": {"action": close_decision["action"]},
        "infrastructure_recoveries": infrastructure_recoveries,
        "allowed_target_ids": scenario["allowed_target_ids"],
        "required_visual_criteria": scenario["required_visual_criteria"],
        "capture_plan": capture_plan,
        "capture_plan_provenance": capture_plan_provenance,
        "base_state": {
            "design_run_id": design_run_id,
            "scheme_version_id": base_version_id,
            "scheme": base_scheme,
        },
        "final_state": {
            "design_run_id": design_run_id,
            "scheme_version_id": final_version_id,
            "scheme": final_scheme,
            "validator_passed": validator_passed,
        },
        "scheme_diff": scheme_diff(base_scheme, final_scheme),
        "tool_calls": tool_calls,
        "render_evidence": render_evidence,
        "critic_review": critic_review_from_trace(tool_calls),
        "final_report": final_report,
    }


def direct_code_overrides(packet: dict[str, Any]) -> dict[str, dict[str, Any]]:
    """Override only run/version alignment, which remains fully deterministic."""

    final_state = packet["final_state"]
    valid_evidence = [
        item for item in packet["render_evidence"] if item.get("evidence_valid", False)
    ]
    aligned = bool(valid_evidence) and all(
        item["design_run_id"] == final_state["design_run_id"]
        and item["scheme_version_id"] == final_state["scheme_version_id"]
        for item in valid_evidence
    )
    return {
        "scheme_render_version_alignment": {
            "verdict": "PASS" if aligned else "FAIL",
            "reason": (
                "全部有效图片绑定最终 Design Run/Scheme 版本。"
                if aligned
                else "有效图片为空或存在 run/version 不一致。"
            ),
            "evidence_refs": [item["evidence_id"] for item in valid_evidence],
        },
    }


def finalize_direct_run(run_dirs: list[Path]) -> dict[str, Any]:
    results: list[dict[str, Any]] = []
    for run_dir in run_dirs:
        for case_dir in sorted(path for path in run_dir.iterdir() if path.is_dir()):
            packet_path = case_dir / "evidence_packet.json"
            judgment_path = case_dir / "grader_judgment.json"
            if not packet_path.exists():
                continue
            if not judgment_path.exists():
                results.append(
                    {
                        "scenario_id": case_dir.name,
                        "source_directory": str(case_dir.resolve()),
                        "grading_status": "missing_judgment",
                        "overall_pass": False,
                    }
                )
                continue
            packet = json.loads(packet_path.read_text(encoding="utf-8"))
            judgment = json.loads(judgment_path.read_text(encoding="utf-8"))
            overrides = direct_code_overrides(packet)
            judgment.setdefault("consistency_gates", {}).update(overrides)
            grade = finalize_outcome_grade(packet, judgment)
            grade["deterministic_overrides"] = overrides
            save_json(case_dir / "grade.json", grade)
            results.append(
                {
                    "scenario_id": case_dir.name,
                    "source_directory": str(case_dir.resolve()),
                    "grading_status": "completed",
                    "required_visual_pass": grade["required_visual_pass"],
                    "consistency_pass": grade["consistency_pass"],
                    "overall_pass": grade["overall_pass"],
                    "summary": grade["summary"],
                }
            )
    completed = [item for item in results if item["grading_status"] == "completed"]
    summary = {
        "protocol": "direct_full_natural_dialogue_v1",
        "finalized_at": utc_now(),
        "run_dirs": [str(path.resolve()) for path in run_dirs],
        "scenario_count": len(results),
        "graded_count": len(completed),
        "pass_count": sum(bool(item["overall_pass"]) for item in completed),
        "all_pass": bool(results) and len(completed) == len(results) and all(
            item["overall_pass"] for item in completed
        ),
        "results": results,
    }
    save_json(run_dirs[0] / "evaluation_summary_direct_dialogue.json", summary)
    return summary


def run_scenario(
    *,
    scenario: dict[str, Any],
    api: AgentApiClient,
    bridge: RenderBridgeClient,
    simulator: DeepSeekOutcomeSimulator,
    case_dir: Path,
) -> dict[str, Any]:
    episode: dict[str, Any] = {
        "episode_id": f"ep_{uuid4().hex}",
        "scenario_id": scenario["scenario_id"],
        "started_at": utc_now(),
        "finished_at": None,
        "status": "running",
        "stop_reason": None,
        "thread_id": None,
        "design_run_id": None,
        "base_version_id": None,
        "final_version_id": None,
        "private_user_profile": None,
        "simulator_decisions": [],
        "infrastructure_recoveries": [],
        "conversation_turn_count": 0,
        "tool_call_count": 0,
        "render_evidence_count": 0,
        "capture_failures": [],
        "capture_plan_source": None,
        "capture_room_ids": [],
        "error": None,
    }
    save_json(case_dir / "episode.json", episode)
    try:
        profile = generate_private_profile(simulator)
        episode["private_user_profile"] = profile
        session = api.create_fresh_session(
            f"d2-dialogue:{scenario['scenario_id']}:{episode['episode_id'][-8:]}"
        )
        episode["thread_id"] = session["thread_id"]
        episode["design_run_id"] = session["design_run_id"]
        episode["base_version_id"] = session["current_version_id"]
        base_scheme = api.scheme(session["design_run_id"])
        transcript: list[dict[str, str]] = []
        user_message = scenario["initial_message"]
        final_report = ""
        product_history: list[dict[str, Any]] = []
        tool_calls: list[dict[str, Any]] = []
        final_scheme = base_scheme
        final_version_id = str(session["current_version_id"])
        validator_passed = False
        validator_errors: list[str] = []

        turn = 1
        recovery_count = 0
        while turn <= scenario["max_user_turns"] + 2:
            transcript.append(
                {"turn_id": f"U{turn}", "role": "user", "content": user_message}
            )
            try:
                response = api.chat(session["thread_id"], user_message)
            except RuntimeError as error:
                run_after_error = api.design_run(session["design_run_id"])
                version_after_error = str(run_after_error["current_version_id"])
                changed_after_error = version_after_error != str(episode["base_version_id"])
                if recovery_count >= 5 or "returned 500" not in str(error):
                    raise
                recovery_count += 1
                episode["infrastructure_recoveries"].append(
                    {
                        "failed_user_turn_id": f"U{turn}",
                        "error": str(error),
                        "scheme_version_id_after_error": version_after_error,
                    }
                )
                user_message = (
                    "刚才执行回复中断了。请从当前已经保存的方案版本继续完成剩余实施、"
                    "Validator 和真实视觉检查，最后把成功、失败及未验证事项如实交付给我。"
                )
                turn += 1
                save_json(case_dir / "conversation.json", numbered_dialogue(transcript))
                save_json(case_dir / "episode.json", episode)
                continue
            final_report = str(response.get("reply") or "")
            transcript.append(
                {"turn_id": f"A{turn}", "role": "assistant", "content": final_report}
            )
            history = api.history(session["thread_id"])
            product_history = compact_history(history)
            tool_calls = extract_tool_trace(product_history)
            run = api.design_run(session["design_run_id"])
            final_version_id = str(run["current_version_id"])
            final_scheme = api.scheme(session["design_run_id"])
            validator_passed, validator_errors = validate_final_scheme(final_scheme)
            changed = final_version_id != str(episode["base_version_id"])
            decision = simulate_natural_user_turn(
                simulator,
                profile=profile,
                transcript=transcript,
                delivery_signals={
                    "scheme_changed_from_base": changed,
                    "validator_passed": validator_passed,
                    "latest_agent_turn_id": f"A{turn}",
                    "tool_names": [call.get("name") for call in tool_calls],
                },
            )
            episode["simulator_decisions"].append(
                {"after_turn_id": f"A{turn}", **decision}
            )
            episode["conversation_turn_count"] = len(transcript)
            episode["tool_call_count"] = len(tool_calls)
            episode["final_version_id"] = final_version_id
            save_json(case_dir / "conversation.json", numbered_dialogue(transcript))
            save_json(case_dir / "product_history.json", product_history)
            save_json(case_dir / "episode.json", episode)
            if decision["action"] == "CLOSE":
                episode["stop_reason"] = "close"
                break
            user_message = decision["message"]
            turn += 1
        else:
            episode["stop_reason"] = "max_user_turns"
            raise RuntimeError("natural user did not CLOSE within max_user_turns")

        capture_plan, capture_plan_provenance = derive_dynamic_capture_plan(
            scenario=scenario,
            tool_calls=tool_calls,
            base_scheme=base_scheme,
            final_scheme=final_scheme,
            final_version_id=final_version_id,
        )
        episode["capture_plan_source"] = capture_plan_provenance["source"]
        episode["capture_room_ids"] = capture_plan_provenance["derived_room_ids"]
        save_json(case_dir / "capture_plan.json", {
            "provenance": capture_plan_provenance,
            "captures": capture_plan,
        })
        render_evidence, capture_records = collect_render_evidence(
            bridge=bridge,
            scenario={**scenario, "capture_plan": capture_plan},
            design_run_id=session["design_run_id"],
            final_version_id=final_version_id,
            case_dir=case_dir,
        )
        validate_capture_room_alignment(capture_plan, render_evidence)
        episode["render_evidence_count"] = len(render_evidence)
        episode["capture_failures"] = [
            {
                "capture_id": item["capture_id"],
                "status": item["status"],
                "error": item["error"],
                "image_count": item["image_count"],
                "minimum_image_count": item["minimum_image_count"],
            }
            for item in capture_records
            if item["status"] != "completed"
        ]
        packet = build_direct_packet(
            scenario=scenario,
            transcript=transcript,
            infrastructure_recoveries=episode["infrastructure_recoveries"],
            design_run_id=session["design_run_id"],
            base_version_id=str(episode["base_version_id"]),
            final_version_id=final_version_id,
            base_scheme=base_scheme,
            final_scheme=final_scheme,
            tool_calls=tool_calls,
            render_evidence=render_evidence,
            capture_plan=capture_plan,
            capture_plan_provenance=capture_plan_provenance,
            validator_passed=validator_passed,
            final_report=final_report,
            close_decision=episode["simulator_decisions"][-1],
        )
        save_json(case_dir / "evidence_packet.json", packet)
        save_json(
            case_dir / "validation.json",
            {
                "validator_passed": validator_passed,
                "validator_errors": validator_errors,
                "base_to_final_change_count": len(packet["scheme_diff"]),
            },
        )
        episode["status"] = "pending_codex_grade"
    except Exception as error:  # noqa: BLE001
        episode["status"] = "error"
        episode["stop_reason"] = episode["stop_reason"] or "error"
        episode["error"] = f"{type(error).__name__}: {error}"
    finally:
        episode["finished_at"] = utc_now()
        save_json(case_dir / "episode.json", episode)
    return episode


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--dataset", type=Path, default=DEFAULT_DATASET)
    parser.add_argument("--subset", default="smoke_6")
    parser.add_argument("--scenario", action="append", default=[])
    parser.add_argument("--results-dir", type=Path, default=DEFAULT_RESULTS_DIR)
    parser.add_argument("--api-url", default="http://127.0.0.1:8000")
    parser.add_argument("--bridge-url", default="http://127.0.0.1:8765")
    parser.add_argument("--render-session", default="worker")
    parser.add_argument("--api-timeout", type=float, default=900)
    parser.add_argument("--simulator-timeout", type=float, default=180)
    parser.add_argument("--finalize-run", type=Path, action="append")
    args = parser.parse_args(argv)
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")
    load_local_env(PROJECT_ROOT / ".env")
    if args.finalize_run:
        summary = finalize_direct_run([path.resolve() for path in args.finalize_run])
        print(json.dumps(summary, ensure_ascii=False, indent=2))
        return 0 if summary["all_pass"] else 1
    dataset = load_dataset(args.dataset.resolve())
    scenarios = select_scenarios(dataset, args.subset, args.scenario)
    api = AgentApiClient(
        args.api_url,
        os.getenv("EVAL_AGENT_API_TOKEN") or os.getenv("AGENT_API_TOKEN"),
        args.api_timeout,
    )
    bridge = RenderBridgeClient(args.bridge_url, args.render_session, args.api_timeout)
    if bridge.status().get("online") is not True:
        raise RuntimeError(f"render session {args.render_session!r} is offline")
    simulator = DeepSeekOutcomeSimulator(args.simulator_timeout)
    run_dir = args.results_dir.resolve() / datetime.now().strftime("%Y%m%d_%H%M%S")
    run_dir.mkdir(parents=True, exist_ok=False)
    manifest: dict[str, Any] = {
        "runner": "direct_natural_dialogue_v1",
        "dataset_version": dataset["dataset_version"],
        "subset": args.subset if not args.scenario else None,
        "scenario_ids": [item["scenario_id"] for item in scenarios],
        "simulator_model": DEEPSEEK_SIMULATOR_MODEL,
        "grader_authority": "full_natural_dialogue",
        "started_at": utc_now(),
        "finished_at": None,
        "results": [],
    }
    save_json(run_dir / "run_manifest.json", manifest)
    try:
        for index, scenario in enumerate(scenarios, start=1):
            print(f"[{index}/{len(scenarios)}] {scenario['scenario_id']}", flush=True)
            result = run_scenario(
                scenario=scenario,
                api=api,
                bridge=bridge,
                simulator=simulator,
                case_dir=run_dir / scenario["scenario_id"],
            )
            manifest["results"].append(
                {
                    "scenario_id": scenario["scenario_id"],
                    "status": result["status"],
                    "stop_reason": result["stop_reason"],
                    "error": result["error"],
                    "conversation_turn_count": result["conversation_turn_count"],
                    "render_evidence_count": result["render_evidence_count"],
                }
            )
            save_json(run_dir / "run_manifest.json", manifest)
    finally:
        simulator.close()
    manifest["finished_at"] = utc_now()
    save_json(run_dir / "run_manifest.json", manifest)
    print(str(run_dir), flush=True)
    return 0 if all(item["status"] == "pending_codex_grade" for item in manifest["results"]) else 1


if __name__ == "__main__":
    raise SystemExit(main())
