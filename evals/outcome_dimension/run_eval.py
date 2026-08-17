"""Run interactive dimension-two evaluations against production HTTP surfaces.

A text-only DeepSeek user simulator negotiates and freezes the final approved
baseline after delivery. Visual evidence is then collected independently through
the render bridge; Codex subagents perform the image grading.
"""

from __future__ import annotations

import argparse
import base64
import json
import os
import re
import sys
import urllib.error
import urllib.parse
import urllib.request
from datetime import datetime, timezone
from pathlib import Path
from typing import Any
from uuid import uuid4

PROJECT_ROOT_FOR_IMPORT = Path(__file__).resolve().parents[2]
if str(PROJECT_ROOT_FOR_IMPORT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT_FOR_IMPORT))

from backend.agent_api.scheme.schema import Scheme
from backend.agent_api.scheme.validator import validate_scheme
from evals.outcome_dimension.rubric import finalize_outcome_grade
from evals.outcome_dimension.user_simulator import (
    DEEPSEEK_SIMULATOR_MODEL,
    DeepSeekOutcomeSimulator,
    apply_approved_negotiation,
    simulate_user_turn,
)


HERE = Path(__file__).resolve().parent
PROJECT_ROOT = HERE.parents[1]
DEFAULT_DATASET = HERE / "dataset_v2.json"
DEFAULT_RESULTS_DIR = HERE / "results"
SCENE_MANIFEST = json.loads((PROJECT_ROOT / "scene_manifest.json").read_text(encoding="utf-8"))
ASSET_MANIFEST = json.loads((PROJECT_ROOT / "asset_manifest.json").read_text(encoding="utf-8"))


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def save_json(path: Path, payload: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    os.replace(temporary, path)


def load_local_env(path: Path) -> None:
    """Read the project's simple .env without introducing dotenv."""
    if not path.is_file():
        return
    for raw_line in path.read_text(encoding="utf-8").splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        key = key.strip()
        value = value.strip()
        if len(value) >= 2 and value[0] == value[-1] and value[0] in {'"', "'"}:
            value = value[1:-1]
        if key and key not in os.environ:
            os.environ[key] = value


def load_dataset(path: Path) -> dict[str, Any]:
    data = json.loads(path.read_text(encoding="utf-8"))
    if data.get("entry_contract", {}).get("mode") == "interactive_final_baseline":
        contract = data["entry_contract"]
        if contract.get("simulator_model") != DEEPSEEK_SIMULATOR_MODEL:
            raise ValueError(
                f"interactive outcome eval requires {DEEPSEEK_SIMULATOR_MODEL}"
            )
        if contract.get("close_token") != "CLOSE":
            raise ValueError("interactive outcome eval close_token must be CLOSE")
        if not isinstance(contract.get("max_user_turns"), int) or not 2 <= contract[
            "max_user_turns"
        ] <= 20:
            raise ValueError("interactive outcome eval max_user_turns must be 2..20")
        base_name = data.get("base_dataset")
        if not isinstance(base_name, str) or Path(base_name).name != base_name:
            raise ValueError("interactive dataset requires a local base_dataset filename")
        base = json.loads((path.parent / base_name).read_text(encoding="utf-8"))
        template = data["entry_contract"].get("initial_message_template")
        if not isinstance(template, str) or "{title}" not in template:
            raise ValueError("interactive dataset initial_message_template requires {title}")
        scenarios = []
        for source in base.get("scenarios", []):
            scenario = dict(source)
            scenario["initial_message"] = template.format(title=scenario["title"])
            scenario["reference_plan"] = scenario.pop("approved_plan")
            scenario["requirement_facts"] = [
                {
                    "requirement_id": f"req_{index:02d}",
                    "statement": statement,
                    "disclosure": "initial" if index == 2 else "if_asked_or_conflict",
                }
                for index, statement in enumerate(
                    scenario.pop("confirmed_requirements"), start=1
                )
            ]
            scenario["max_user_turns"] = contract["max_user_turns"]
            scenarios.append(scenario)
        data = {
            **data,
            "subsets": base.get("subsets", {}),
            "scenarios": scenarios,
            "source_dataset_version": base.get("dataset_version"),
        }
    scenarios = data.get("scenarios")
    if not isinstance(scenarios, list) or not scenarios:
        raise ValueError("dataset requires non-empty scenarios")
    scenario_ids = [scenario.get("scenario_id") for scenario in scenarios]
    if len(scenario_ids) != len(set(scenario_ids)) or any(not item for item in scenario_ids):
        raise ValueError("scenario_id values must be unique non-empty strings")
    if data.get("entry_contract", {}).get("mode") == "interactive_final_baseline":
        for scenario in scenarios:
            requirement_ids = [
                item.get("requirement_id") for item in scenario.get("requirement_facts", [])
            ]
            if not requirement_ids or len(requirement_ids) != len(set(requirement_ids)):
                raise ValueError(f"{scenario['scenario_id']} has invalid requirement facts")
    return data


class JsonHttpClient:
    def __init__(self, base_url: str, token: str | None, timeout: float) -> None:
        self.base_url = base_url.rstrip("/")
        self.token = token
        self.timeout = timeout

    def request(
        self,
        method: str,
        path: str,
        payload: dict[str, Any] | None = None,
        *,
        timeout: float | None = None,
    ) -> dict[str, Any]:
        headers = {"Accept": "application/json"}
        if self.token:
            headers["Authorization"] = f"Bearer {self.token}"
        body = None
        if payload is not None:
            body = json.dumps(payload, ensure_ascii=False).encode("utf-8")
            headers["Content-Type"] = "application/json"
        request = urllib.request.Request(
            f"{self.base_url}{path}", data=body, headers=headers, method=method
        )
        try:
            with urllib.request.urlopen(request, timeout=timeout or self.timeout) as response:
                raw = response.read().decode("utf-8")
                return json.loads(raw) if raw else {}
        except urllib.error.HTTPError as error:
            detail = error.read().decode("utf-8", errors="replace")
            raise RuntimeError(
                f"{method} {self.base_url}{path} returned {error.code}: {detail}"
            ) from error
        except urllib.error.URLError as error:
            raise RuntimeError(f"service unavailable at {self.base_url}: {error}") from error


class AgentApiClient(JsonHttpClient):
    def create_fresh_session(self, title: str) -> dict[str, Any]:
        return self.request("POST", "/api/sessions", {"title": title, "mode": "fresh"})

    def chat(self, thread_id: str, message: str) -> dict[str, Any]:
        return self.request(
            "POST", "/api/chat", {"thread_id": thread_id, "message": message}
        )

    def history(self, thread_id: str) -> dict[str, Any]:
        encoded = urllib.parse.quote(thread_id)
        return self.request("GET", f"/api/sessions/{encoded}/messages")

    def design_run(self, design_run_id: str) -> dict[str, Any]:
        encoded = urllib.parse.quote(design_run_id)
        return self.request("GET", f"/api/design-runs/{encoded}")

    def scheme(self, design_run_id: str) -> dict[str, Any]:
        query = urllib.parse.urlencode({"design_run_id": design_run_id})
        return self.request("GET", f"/api/scheme?{query}")


class RenderBridgeClient(JsonHttpClient):
    def __init__(self, base_url: str, session_id: str, timeout: float) -> None:
        super().__init__(base_url, None, timeout)
        self.session_id = session_id

    def status(self) -> dict[str, Any]:
        session = urllib.parse.quote(self.session_id)
        return self.request("GET", f"/v1/render-sessions/{session}/status")

    def capture(
        self, tool: str, args: dict[str, Any], *, timeout_ms: int = 180_000
    ) -> dict[str, Any]:
        session = urllib.parse.quote(self.session_id)
        response = self.request(
            "POST",
            f"/v1/render-sessions/{session}/commands",
            {"tool": tool, "args": args, "timeout_ms": timeout_ms},
            timeout=(timeout_ms / 1000) + 15,
        )
        if response.get("status") != "completed" or not isinstance(response.get("result"), dict):
            raise RuntimeError(f"render command did not complete: {response}")
        return response["result"]


def assignment_map(scheme: dict[str, Any]) -> dict[str, dict[str, Any]]:
    return {
        assignment["target"]["id"]: assignment
        for assignment in scheme.get("assignments", [])
        if isinstance(assignment, dict)
        and isinstance(assignment.get("target"), dict)
        and isinstance(assignment["target"].get("id"), str)
    }


def scheme_diff(base: dict[str, Any], final: dict[str, Any]) -> list[dict[str, Any]]:
    before = assignment_map(base)
    after = assignment_map(final)
    changes: list[dict[str, Any]] = []
    for target_id in sorted(set(before) | set(after)):
        if before.get(target_id) == after.get(target_id):
            continue
        changes.append(
            {
                "target_id": target_id,
                "before": before.get(target_id),
                "after": after.get(target_id),
            }
        )
    return changes


def compact_history(history: dict[str, Any]) -> list[dict[str, Any]]:
    return [
        message
        for message in history.get("messages", [])
        if message.get("role") in {"user", "assistant", "tool"}
    ]


def extract_tool_trace(messages: list[dict[str, Any]]) -> list[dict[str, Any]]:
    tool_results: dict[str, Any] = {}
    for message in messages:
        if message.get("role") == "tool" and isinstance(message.get("tool_call_id"), str):
            tool_results[message["tool_call_id"]] = message.get("content")

    trace: list[dict[str, Any]] = []
    sequence = 0
    for message_index, message in enumerate(messages):
        if message.get("role") != "assistant":
            continue
        for call in message.get("tool_calls", []) or []:
            sequence += 1
            call_id = call.get("id")
            trace.append(
                {
                    "sequence": sequence,
                    "message_index": message_index,
                    "call_id": call_id,
                    "name": call.get("name"),
                    "args": call.get("args", {}),
                    "result": tool_results.get(call_id),
                }
            )
    return trace


def validate_final_scheme(scheme: dict[str, Any]) -> tuple[bool, list[str]]:
    try:
        model = Scheme.model_validate(scheme)
    except Exception as error:  # noqa: BLE001
        return False, [f"schema:{error}"]
    errors = validate_scheme(model, SCENE_MANIFEST, ASSET_MANIFEST)
    return not errors, errors


def slug(value: str) -> str:
    compact = re.sub(r"[^A-Za-z0-9._-]+", "_", value).strip("._")
    return compact[:100] or "view"


def decode_data_url(data_url: str, output_path: Path) -> None:
    if not data_url.startswith("data:image/") or ";base64," not in data_url:
        raise ValueError("render evidence is not a base64 image data URL")
    _, encoded = data_url.split(",", 1)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_bytes(base64.b64decode(encoded, validate=True))


def strip_image_data(value: Any) -> Any:
    if isinstance(value, dict):
        return {
            key: ("<saved-to-visuals>" if key == "imageDataUrl" and item else strip_image_data(item))
            for key, item in value.items()
        }
    if isinstance(value, list):
        return [strip_image_data(item) for item in value]
    if isinstance(value, str) and value.startswith("data:image/"):
        return "<saved-to-visuals>"
    return value


def save_render_result(
    *,
    result: dict[str, Any],
    capture: dict[str, Any],
    case_dir: Path,
    design_run_id: str,
    fallback_version_id: str,
) -> list[dict[str, Any]]:
    evidence: list[dict[str, Any]] = []
    capture_id = capture["capture_id"]
    del fallback_version_id
    scheme_version_id = str((result.get("scheme") or {}).get("schemeId") or "unknown")
    visuals_dir = case_dir / "visuals"

    def add_image(
        *,
        image_data_url: str,
        room_id: str,
        view_id: str,
        view_label: str,
        quality: dict[str, Any] | None = None,
        target_visibility: list[dict[str, Any]] | None = None,
        mask_quality: dict[str, Any] | None = None,
        individually_valid: bool = True,
    ) -> None:
        evidence_id = f"{capture_id}:{view_id}"
        filename = f"{slug(capture_id)}__{slug(view_id)}.jpg"
        path = visuals_dir / filename
        decode_data_url(image_data_url, path)
        evidence.append(
            {
                "evidence_id": evidence_id,
                "capture_id": capture_id,
                "view_id": view_id,
                "design_run_id": design_run_id,
                "scheme_version_id": scheme_version_id,
                "room_id": room_id,
                "view_label": view_label,
                "image_path": str(path.resolve()),
                "evidence_valid": bool(individually_valid and result.get("status") == "ready"),
                "observation_status": str(result.get("status") or "unknown"),
                "quality": quality,
                "target_visibility": target_visibility or [],
                "mask_quality": mask_quality,
            }
        )

    if capture["tool"] == "observe_room":
        room_id = str((result.get("room") or {}).get("id") or capture.get("room_id") or "unknown")
        for index, view in enumerate(result.get("views", []), start=1):
            image = view.get("imageDataUrl")
            if not isinstance(image, str) or not image:
                continue
            add_image(
                image_data_url=image,
                room_id=room_id,
                view_id=str(view.get("viewId") or f"view_{index}"),
                view_label=str(view.get("label") or f"视角 {index}"),
                quality=view.get("quality") if isinstance(view.get("quality"), dict) else None,
                target_visibility=(
                    view.get("targetVisibility")
                    if isinstance(view.get("targetVisibility"), list)
                    else []
                ),
                mask_quality=(
                    view.get("maskQuality")
                    if isinstance(view.get("maskQuality"), dict)
                    else None
                ),
                individually_valid=bool((view.get("quality") or {}).get("valid")),
            )
    else:
        contact_sheet = result.get("roomContactSheet")
        if isinstance(contact_sheet, str) and contact_sheet:
            add_image(
                image_data_url=contact_sheet,
                room_id="whole_home",
                view_id="room_contact_sheet",
                view_label="全屋代表视图总览",
                individually_valid=not bool(result.get("invalidHeroRoomIds")),
            )
        for pair_index, pair in enumerate(result.get("transitionPairs", []), start=1):
            pair_id = str(pair.get("id") or f"transition_{pair_index}")
            for side in ("from", "to"):
                view = pair.get(side) or {}
                image = view.get("imageDataUrl")
                if not isinstance(image, str) or not image:
                    continue
                add_image(
                    image_data_url=image,
                    room_id=f"transition:{pair_id}:{side}",
                    view_id=f"{pair_id}_{side}",
                    view_label=str(view.get("label") or f"{pair_id} {side}"),
                    quality=view.get("quality") if isinstance(view.get("quality"), dict) else None,
                    target_visibility=(
                        view.get("targetVisibility")
                        if isinstance(view.get("targetVisibility"), list)
                        else []
                    ),
                    mask_quality=(
                        view.get("maskQuality")
                        if isinstance(view.get("maskQuality"), dict)
                        else None
                    ),
                    individually_valid=bool(
                        pair.get("status") == "ready"
                        and (view.get("quality") or {}).get("valid")
                    ),
                )
    return evidence


def collect_render_evidence(
    *,
    bridge: RenderBridgeClient,
    scenario: dict[str, Any],
    design_run_id: str,
    final_version_id: str,
    case_dir: Path,
) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    evidence: list[dict[str, Any]] = []
    captures: list[dict[str, Any]] = []
    for capture in scenario["capture_plan"]:
        args: dict[str, Any] = {"design_run_id": design_run_id}
        if capture["tool"] == "observe_room":
            args["room_id"] = capture["room_id"]
            args["focus_target_ids"] = capture.get("focus_target_ids", [])
        record = {
            "capture_id": capture["capture_id"],
            "tool": capture["tool"],
            "started_at": utc_now(),
            "finished_at": None,
            "status": "running",
            "error": None,
            "image_count": 0,
            "minimum_image_count": capture["minimum_image_count"],
            "result": None,
        }
        try:
            result = bridge.capture(capture["tool"], args)
            new_evidence = save_render_result(
                result=result,
                capture=capture,
                case_dir=case_dir,
                design_run_id=design_run_id,
                fallback_version_id=final_version_id,
            )
            evidence.extend(new_evidence)
            valid_image_count = sum(1 for item in new_evidence if item["evidence_valid"])
            record["image_count"] = valid_image_count
            if result.get("status") != "ready":
                record["status"] = "incomplete_observation"
            elif valid_image_count < capture["minimum_image_count"]:
                record["status"] = "insufficient_images"
            else:
                record["status"] = "completed"
            record["result"] = strip_image_data(result)
        except Exception as error:  # noqa: BLE001
            record["status"] = "failed"
            record["error"] = f"{type(error).__name__}: {error}"
        finally:
            record["finished_at"] = utc_now()
            captures.append(record)
            save_json(case_dir / "render_captures.json", captures)
    return evidence, captures


def critic_review_from_trace(tool_calls: list[dict[str, Any]]) -> str | None:
    reviews = [
        str(call.get("result"))
        for call in tool_calls
        if call.get("name") == "ask_design_critic" and call.get("result")
    ]
    return "\n\n---\n\n".join(reviews) if reviews else None


def build_evidence_packet(
    *,
    scenario: dict[str, Any],
    final_baseline: dict[str, Any],
    baseline_provenance: dict[str, Any],
    design_run_id: str,
    base_version_id: str,
    final_version_id: str,
    base_scheme: dict[str, Any],
    final_scheme: dict[str, Any],
    tool_calls: list[dict[str, Any]],
    render_evidence: list[dict[str, Any]],
    validator_passed: bool,
    final_report: str,
) -> dict[str, Any]:
    return {
        "scenario_id": scenario["scenario_id"],
        "rubric_version": "outcome_dimension_v1",
        "confirmed_requirements": [
            item["statement"] for item in final_baseline["confirmed_requirements"]
        ],
        "approved_plan": final_baseline["approved_plan"],
        "allowed_target_ids": final_baseline["allowed_target_ids"],
        "baseline_provenance": baseline_provenance,
        "required_visual_criteria": scenario["required_visual_criteria"],
        "capture_plan": scenario["capture_plan"],
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


def run_scenario(
    *,
    dataset: dict[str, Any],
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
        "thread_id": None,
        "design_run_id": None,
        "base_version_id": None,
        "final_version_id": None,
        "agent_reply": None,
        "stop_reason": None,
        "simulated_user_replies": 0,
        "disclosed_requirement_ids": [],
        "simulator_decisions": [],
        "negotiation_log": [],
        "plan_approval_log": [],
        "locked_approved_baseline": None,
        "final_baseline": None,
        "tool_call_count": 0,
        "render_evidence_count": 0,
        "capture_failures": [],
        "error": None,
    }
    save_json(case_dir / "episode.json", episode)
    try:
        session = api.create_fresh_session(
            f"outcome-eval:{scenario['scenario_id']}:{episode['episode_id'][-8:]}"
        )
        episode["thread_id"] = session["thread_id"]
        episode["design_run_id"] = session["design_run_id"]
        episode["base_version_id"] = session["current_version_id"]
        base_scheme = api.scheme(session["design_run_id"])
        current_requirements = {
            item["requirement_id"]: item["statement"]
            for item in scenario["requirement_facts"]
        }
        disclosed = {
            item["requirement_id"]
            for item in scenario["requirement_facts"]
            if item["disclosure"] == "initial"
        }
        episode["disclosed_requirement_ids"] = sorted(disclosed)
        transcript: list[dict[str, str]] = []
        user_message = scenario["initial_message"]
        final_report = ""
        final_scheme = base_scheme
        final_version_id = str(session["current_version_id"])
        validator_passed = False
        validator_errors: list[str] = []
        approved_baseline: dict[str, Any] | None = None
        product_history: list[dict[str, Any]] = []
        tool_calls: list[dict[str, Any]] = []

        while True:
            transcript.append({"role": "user", "content": user_message})
            response = api.chat(session["thread_id"], user_message)
            final_report = str(response.get("reply") or "")
            episode["agent_reply"] = final_report
            transcript.append({"role": "assistant", "content": final_report})

            history = api.history(session["thread_id"])
            product_history = compact_history(history)
            save_json(case_dir / "conversation.json", product_history)
            tool_calls = extract_tool_trace(product_history)
            episode["tool_call_count"] = len(tool_calls)
            run = api.design_run(session["design_run_id"])
            final_version_id = str(run["current_version_id"])
            final_scheme = api.scheme(session["design_run_id"])
            episode["final_version_id"] = final_version_id
            validator_passed, validator_errors = validate_final_scheme(final_scheme)
            changed = final_version_id != str(episode["base_version_id"])
            delivery_signals = {
                "scheme_changed_from_base": changed,
                "validator_passed": validator_passed,
                "tool_names": [call.get("name") for call in tool_calls],
            }
            close_eligible = changed and validator_passed and approved_baseline is not None
            save_json(case_dir / "episode.json", episode)

            decision = simulate_user_turn(
                simulator,
                scenario=scenario,
                transcript=transcript,
                current_requirements=current_requirements,
                approved_baseline=approved_baseline,
                disclosed_requirement_ids=disclosed,
                close_eligible=close_eligible,
                delivery_signals=delivery_signals,
            )
            episode["simulator_decisions"].append(decision)
            disclosed.update(decision["referenced_requirement_ids"])
            episode["disclosed_requirement_ids"] = sorted(disclosed)
            if decision["negotiation"] is not None:
                event = {
                    "turn": len(episode["simulator_decisions"]),
                    "scheme_version_id_at_decision": final_version_id,
                    **decision["negotiation"],
                }
                episode["negotiation_log"].append(event)
                current_requirements = apply_approved_negotiation(
                    current_requirements, decision
                )
            if decision["plan_approval"] is not None:
                approved_baseline = {
                    "approved_plan": decision["plan_approval"]["approved_plan"],
                    "allowed_target_ids": decision["plan_approval"]["allowed_target_ids"],
                }
                episode["locked_approved_baseline"] = approved_baseline
                episode["plan_approval_log"].append(
                    {
                        "turn": len(episode["simulator_decisions"]),
                        "scheme_version_id_at_approval": final_version_id,
                        "scheme_changed_from_base_at_approval": changed,
                        **decision["plan_approval"],
                        "confirmed_requirements": [
                            {"requirement_id": key, "statement": value}
                            for key, value in current_requirements.items()
                        ],
                    }
                )

            if decision["action"] == "CLOSE":
                episode["stop_reason"] = "close"
                episode["final_baseline"] = decision["final_baseline"]
                break
            if episode["simulated_user_replies"] >= scenario["max_user_turns"]:
                episode["stop_reason"] = "max_user_turns"
                raise RuntimeError("simulator reached max_user_turns before final delivery")
            episode["simulated_user_replies"] += 1
            user_message = decision["message"]
            save_json(case_dir / "episode.json", episode)

        save_json(case_dir / "simulator_trace.json", {
            "model": DEEPSEEK_SIMULATOR_MODEL,
            "text_only": True,
            "initial_message": scenario["initial_message"],
            "decisions": episode["simulator_decisions"],
            "negotiation_log": episode["negotiation_log"],
            "plan_approval_log": episode["plan_approval_log"],
            "locked_approved_baseline": episode["locked_approved_baseline"],
            "final_baseline": episode["final_baseline"],
        })

        render_evidence, capture_records = collect_render_evidence(
            bridge=bridge,
            scenario=scenario,
            design_run_id=session["design_run_id"],
            final_version_id=final_version_id,
            case_dir=case_dir,
        )
        episode["render_evidence_count"] = len(render_evidence)
        episode["capture_failures"] = [
            {
                "capture_id": capture["capture_id"],
                "status": capture["status"],
                "error": capture["error"],
                "image_count": capture["image_count"],
                "minimum_image_count": capture["minimum_image_count"],
            }
            for capture in capture_records
            if capture["status"] != "completed"
        ]

        packet = build_evidence_packet(
            scenario=scenario,
            final_baseline=episode["final_baseline"],
            baseline_provenance={
                "source": "deepseek_user_simulator_close",
                "simulator_model": DEEPSEEK_SIMULATOR_MODEL,
                "close_token": dataset["entry_contract"]["close_token"],
                "close_decision_index": len(episode["simulator_decisions"]),
                "initial_message": scenario["initial_message"],
                "negotiation_log": episode["negotiation_log"],
                "plan_approval_log": episode["plan_approval_log"],
            },
            design_run_id=session["design_run_id"],
            base_version_id=session["current_version_id"],
            final_version_id=final_version_id,
            base_scheme=base_scheme,
            final_scheme=final_scheme,
            tool_calls=tool_calls,
            render_evidence=render_evidence,
            validator_passed=validator_passed,
            final_report=final_report,
        )
        save_json(case_dir / "evidence_packet.json", packet)
        save_json(
            case_dir / "validation.json",
            {
                "validator_passed": validator_passed,
                "validator_errors": validator_errors,
                "base_to_final_change_count": len(packet["scheme_diff"]),
                "allowed_change_count": len(
                    {
                        change["target_id"]
                        for change in packet["scheme_diff"]
                        if change["target_id"] in set(packet["allowed_target_ids"])
                    }
                ),
            },
        )
        episode["status"] = "pending_subagent_grade"
    except Exception as error:  # noqa: BLE001
        episode["status"] = "error"
        episode["stop_reason"] = episode["stop_reason"] or "error"
        episode["error"] = f"{type(error).__name__}: {error}"
    finally:
        episode["finished_at"] = utc_now()
        save_json(case_dir / "episode.json", episode)
    return episode


def select_scenarios(
    dataset: dict[str, Any], subset: str | None, requested: list[str]
) -> list[dict[str, Any]]:
    by_id = {scenario["scenario_id"]: scenario for scenario in dataset["scenarios"]}
    if requested:
        ids = requested
    else:
        if subset not in dataset["subsets"]:
            raise ValueError(f"unknown subset: {subset}")
        ids = dataset["subsets"][subset]
    unknown = [scenario_id for scenario_id in ids if scenario_id not in by_id]
    if unknown:
        raise ValueError(f"unknown scenario IDs: {unknown}")
    return [by_id[scenario_id] for scenario_id in ids]


def deterministic_gate_overrides(packet: dict[str, Any]) -> dict[str, dict[str, Any]]:
    final_state = packet["final_state"]
    expected_run = final_state["design_run_id"]
    expected_version = final_state["scheme_version_id"]
    evidence = packet["render_evidence"]
    valid_evidence = [item for item in evidence if item.get("evidence_valid", False)]
    aligned = bool(valid_evidence) and all(
        item["design_run_id"] == expected_run
        and item["scheme_version_id"] == expected_version
        for item in valid_evidence
    )

    changed_targets = {change.get("target_id") for change in packet["scheme_diff"]}
    out_of_scope = sorted(changed_targets - set(packet["allowed_target_ids"]))

    capture_counts: dict[str, int] = {}
    for item in evidence:
        if not item.get("evidence_valid", False):
            continue
        capture_counts[item["capture_id"]] = capture_counts.get(item["capture_id"], 0) + 1
    missing_captures = [
        capture["capture_id"]
        for capture in packet["capture_plan"]
        if capture_counts.get(capture["capture_id"], 0) < capture["minimum_image_count"]
    ]
    return {
        "scheme_render_version_alignment": {
            "verdict": "PASS" if aligned else "FAIL",
            "reason": (
                "全部评分图片均绑定当前 Design Run 的最终 Scheme 版本。"
                if aligned
                else "评分图片为空，或存在 run/version 与最终状态不一致。"
            ),
            "evidence_refs": [item["evidence_id"] for item in valid_evidence],
        },
        "scope_integrity": {
            "verdict": "PASS" if not out_of_scope else "FAIL",
            "reason": (
                "Scheme diff 的全部目标均在审批范围内。"
                if not out_of_scope
                else f"发现范围外修改：{', '.join(out_of_scope)}"
            ),
            "evidence_refs": [f"scheme_diff:{target}" for target in sorted(changed_targets)],
        },
        "visual_claim_has_evidence": {
            "verdict": "PASS" if not missing_captures else "FAIL",
            "reason": (
                "每项标准截图计划均取得最低数量的最终版本图片。"
                if not missing_captures
                else f"缺少标准截图证据：{', '.join(missing_captures)}"
            ),
            "evidence_refs": [item["evidence_id"] for item in valid_evidence],
        },
    }


def finalize_case(case_dir: Path) -> dict[str, Any]:
    packet = json.loads((case_dir / "evidence_packet.json").read_text(encoding="utf-8"))
    judgment = json.loads((case_dir / "grader_judgment.json").read_text(encoding="utf-8"))
    overrides = deterministic_gate_overrides(packet)
    judgment.setdefault("consistency_gates", {}).update(overrides)
    grade = finalize_outcome_grade(packet, judgment)
    grade["deterministic_overrides"] = overrides
    save_json(case_dir / "grade.json", grade)
    return grade


def finalize_run(run_dir: Path) -> dict[str, Any]:
    results: list[dict[str, Any]] = []
    for case_dir in sorted(path for path in run_dir.iterdir() if path.is_dir()):
        packet_path = case_dir / "evidence_packet.json"
        judgment_path = case_dir / "grader_judgment.json"
        if not packet_path.exists():
            continue
        if not judgment_path.exists():
            results.append(
                {
                    "scenario_id": case_dir.name,
                    "grading_status": "missing_judgment",
                    "overall_pass": False,
                }
            )
            continue
        try:
            grade = finalize_case(case_dir)
            results.append(
                {
                    "scenario_id": case_dir.name,
                    "grading_status": "completed",
                    "required_visual_pass": grade["required_visual_pass"],
                    "consistency_pass": grade["consistency_pass"],
                    "overall_pass": grade["overall_pass"],
                    "summary": grade["summary"],
                }
            )
        except Exception as error:  # noqa: BLE001
            results.append(
                {
                    "scenario_id": case_dir.name,
                    "grading_status": "invalid_judgment",
                    "overall_pass": False,
                    "error": f"{type(error).__name__}: {error}",
                }
            )
    completed = [result for result in results if result["grading_status"] == "completed"]
    summary = {
        "run_dir": str(run_dir.resolve()),
        "finalized_at": utc_now(),
        "scenario_count": len(results),
        "graded_count": len(completed),
        "pass_count": sum(bool(result["overall_pass"]) for result in completed),
        "all_pass": bool(results) and len(completed) == len(results) and all(
            result["overall_pass"] for result in completed
        ),
        "results": results,
    }
    save_json(run_dir / "evaluation_summary.json", summary)
    return summary


def finalize_run_set(run_dirs: list[Path]) -> dict[str, Any]:
    """Finalize multiple directories, preferring the newest graded copy per case."""
    candidates: dict[str, list[Path]] = {}
    per_run: list[dict[str, Any]] = []
    for run_dir in run_dirs:
        per_run.append(finalize_run(run_dir))
        for case_dir in (path for path in run_dir.iterdir() if path.is_dir()):
            if (case_dir / "evidence_packet.json").exists():
                candidates.setdefault(case_dir.name, []).append(case_dir)

    results: list[dict[str, Any]] = []
    selected_cases: dict[str, str] = {}
    for scenario_id, case_dirs in sorted(candidates.items()):
        graded = [path for path in case_dirs if (path / "grade.json").exists()]
        selected = max(graded or case_dirs, key=lambda path: path.stat().st_mtime)
        selected_cases[scenario_id] = str(selected.resolve())
        grade_path = selected / "grade.json"
        if not grade_path.exists():
            results.append(
                {
                    "scenario_id": scenario_id,
                    "grading_status": "missing_judgment",
                    "overall_pass": False,
                }
            )
            continue
        grade = json.loads(grade_path.read_text(encoding="utf-8"))
        results.append(
            {
                "scenario_id": scenario_id,
                "grading_status": "completed",
                "required_visual_pass": grade["required_visual_pass"],
                "consistency_pass": grade["consistency_pass"],
                "overall_pass": grade["overall_pass"],
                "summary": grade["summary"],
            }
        )

    completed = [result for result in results if result["grading_status"] == "completed"]
    summary = {
        "run_dirs": [str(path.resolve()) for path in run_dirs],
        "selected_cases": selected_cases,
        "finalized_at": utc_now(),
        "scenario_count": len(results),
        "graded_count": len(completed),
        "pass_count": sum(bool(result["overall_pass"]) for result in completed),
        "all_pass": bool(results) and len(completed) == len(results) and all(
            result["overall_pass"] for result in completed
        ),
        "results": results,
        "per_run_summaries": per_run,
    }
    save_json(run_dirs[0] / "evaluation_summary_corrected.json", summary)
    return summary


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--dataset", type=Path, default=DEFAULT_DATASET)
    parser.add_argument("--results-dir", type=Path, default=DEFAULT_RESULTS_DIR)
    parser.add_argument("--subset", default="smoke_6")
    parser.add_argument("--scenario", action="append", default=[])
    parser.add_argument("--api-url", default="http://127.0.0.1:8000")
    parser.add_argument("--bridge-url", default="http://127.0.0.1:8765")
    parser.add_argument("--render-session", default="worker")
    parser.add_argument("--token", default=os.getenv("AGENT_API_TOKEN"))
    parser.add_argument("--api-timeout", type=float, default=900)
    parser.add_argument("--simulator-timeout", type=float, default=180.0)
    parser.add_argument("--list", action="store_true")
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--finalize-run", type=Path, action="append")
    return parser


def main(argv: list[str] | None = None) -> int:
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")
        sys.stderr.reconfigure(encoding="utf-8")
    load_local_env(PROJECT_ROOT / ".env")
    args = build_parser().parse_args(argv)
    if args.finalize_run:
        run_dirs = [path.resolve() for path in args.finalize_run]
        summary = (
            finalize_run(run_dirs[0])
            if len(run_dirs) == 1
            else finalize_run_set(run_dirs)
        )
        print(json.dumps(summary, ensure_ascii=False, indent=2))
        return 0 if summary["all_pass"] else 1

    dataset = load_dataset(args.dataset.resolve())
    scenarios = select_scenarios(dataset, args.subset, args.scenario)
    if args.list:
        for scenario in dataset["scenarios"]:
            print(f"{scenario['scenario_id']}\t{scenario['title']}")
        return 0
    if args.dry_run:
        print(
            f"Dataset valid; selected {len(scenarios)} scenario(s); "
            f"entry={dataset['entry_contract']['mode']}; "
            f"simulator={dataset['entry_contract']['simulator_model']}."
        )
        return 0
    api = AgentApiClient(args.api_url, args.token, args.api_timeout)
    bridge = RenderBridgeClient(args.bridge_url, args.render_session, args.api_timeout)
    status = bridge.status()
    if status.get("online") is not True:
        raise RuntimeError(
            f"render session {args.render_session!r} is not online at {args.bridge_url}"
        )

    run_stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    run_dir = args.results_dir.resolve() / run_stamp
    run_dir.mkdir(parents=True, exist_ok=False)
    manifest = {
        "dataset_version": dataset["dataset_version"],
        "rubric_version": dataset["rubric_version"],
        "subset": args.subset if not args.scenario else None,
        "scenario_ids": [scenario["scenario_id"] for scenario in scenarios],
        "started_at": utc_now(),
        "finished_at": None,
        "api_url": args.api_url,
        "bridge_url": args.bridge_url,
        "render_session": args.render_session,
        "simulator_model": DEEPSEEK_SIMULATOR_MODEL,
        "results": [],
    }
    save_json(run_dir / "run_manifest.json", manifest)

    simulator = DeepSeekOutcomeSimulator(args.simulator_timeout)
    try:
        for index, scenario in enumerate(scenarios, start=1):
            print(f"[{index}/{len(scenarios)}] {scenario['scenario_id']}", flush=True)
            case_dir = run_dir / scenario["scenario_id"]
            result = run_scenario(
                dataset=dataset,
                scenario=scenario,
                api=api,
                bridge=bridge,
                simulator=simulator,
                case_dir=case_dir,
            )
            manifest["results"].append(
                {
                    "scenario_id": scenario["scenario_id"],
                    "status": result["status"],
                    "stop_reason": result["stop_reason"],
                    "error": result["error"],
                    "tool_call_count": result["tool_call_count"],
                    "render_evidence_count": result["render_evidence_count"],
                }
            )
            save_json(run_dir / "run_manifest.json", manifest)
    finally:
        simulator.close()

    manifest["finished_at"] = utc_now()
    save_json(run_dir / "run_manifest.json", manifest)
    print(str(run_dir), flush=True)
    return 0 if all(item["status"] == "pending_subagent_grade" for item in manifest["results"]) else 1


if __name__ == "__main__":
    raise SystemExit(main())
