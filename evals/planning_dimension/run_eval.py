"""Run planning-dimension evaluations against the production FastAPI surface.

Dependencies are limited to the Python standard library plus the project's existing
``openai`` and ``httpx`` packages. DeepSeek is called through its OpenAI-compatible
Chat Completions API; the Agent itself is always called through FastAPI.
"""

from __future__ import annotations

import argparse
import json
import os
import sys
import urllib.error
import urllib.parse
import urllib.request
from datetime import datetime, timezone
from pathlib import Path
from typing import Any
from uuid import uuid4

import httpx
from openai import OpenAI


HERE = Path(__file__).resolve().parent
PROJECT_ROOT = HERE.parents[1]
DEFAULT_DATASET = HERE / "dataset_v1.json"
DEFAULT_RESULTS_DIR = HERE / "results"
DEEPSEEK_BASE_URL = "https://api.deepseek.com"
DEEPSEEK_SIMULATOR_MODEL = "deepseek-v4-flash"


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def load_local_env(path: Path) -> None:
    """Read the project's simple .env without adding a dotenv dependency."""
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
    scenarios = data.get("scenarios")
    if not isinstance(scenarios, list) or not scenarios:
        raise ValueError("dataset must contain a non-empty scenarios array")
    ids = [item.get("scenario_id") for item in scenarios]
    if any(not isinstance(item, str) or not item for item in ids):
        raise ValueError("every scenario requires scenario_id")
    if len(ids) != len(set(ids)):
        raise ValueError("scenario_id values must be unique")
    for scenario in scenarios:
        fact_ids = {
            fact.get("fact_id")
            for fact in scenario.get("facts", [])
            if isinstance(fact, dict)
        }
        missing = set(scenario.get("must_resolve", [])) - fact_ids
        if missing:
            raise ValueError(
                f"{scenario['scenario_id']} has unknown must_resolve facts: {sorted(missing)}"
            )
    return data


class AgentApiClient:
    def __init__(self, base_url: str, token: str | None, timeout: float) -> None:
        self.base_url = base_url.rstrip("/")
        self.token = token
        self.timeout = timeout

    def request(
        self,
        method: str,
        path: str,
        payload: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        headers = {"Accept": "application/json"}
        if self.token:
            headers["Authorization"] = f"Bearer {self.token}"
        data = None
        if payload is not None:
            data = json.dumps(payload, ensure_ascii=False).encode("utf-8")
            headers["Content-Type"] = "application/json"
        request = urllib.request.Request(
            f"{self.base_url}{path}",
            data=data,
            headers=headers,
            method=method,
        )
        try:
            with urllib.request.urlopen(request, timeout=self.timeout) as response:
                return json.loads(response.read().decode("utf-8"))
        except urllib.error.HTTPError as error:
            body = error.read().decode("utf-8", errors="replace")
            raise RuntimeError(f"Agent API {method} {path} returned {error.code}: {body}") from error
        except urllib.error.URLError as error:
            raise RuntimeError(f"Agent API unavailable at {self.base_url}: {error}") from error

    def create_fresh_session(self, title: str) -> dict[str, Any]:
        return self.request("POST", "/api/sessions", {"title": title, "mode": "fresh"})

    def chat(self, thread_id: str, message: str) -> dict[str, Any]:
        return self.request("POST", "/api/chat", {"thread_id": thread_id, "message": message})

    def history(self, thread_id: str) -> dict[str, Any]:
        return self.request("GET", f"/api/sessions/{urllib.parse.quote(thread_id)}/messages")

    def design_run(self, design_run_id: str) -> dict[str, Any]:
        run_id = urllib.parse.quote(design_run_id)
        return self.request("GET", f"/api/design-runs/{run_id}")


class DeepSeekSimulator:
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
        max_output_tokens: int,
    ) -> dict[str, Any]:
        last_error: Exception | None = None
        for attempt in range(2):
            retry_note = (
                "\n上次 JSON 无法解析。本次保持 message 和 reason 简短，确保输出完整有效 JSON。"
                if attempt
                else ""
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


def simulate_user(
    simulator: DeepSeekSimulator,
    scenario: dict[str, Any],
    transcript: list[dict[str, str]],
    disclosed: set[str],
) -> dict[str, Any]:
    payload = {
        "scenario": scenario,
        "already_disclosed_fact_ids": sorted(disclosed),
        "conversation": transcript,
        "output_json_contract": {
            "action": "RESPOND or CLOSE",
            "message": "string for RESPOND; null for CLOSE",
            "revealed_fact_ids": ["fact_id disclosed in this response"],
            "reason": "one short sentence",
        },
    }
    instructions = (
            "你是评估中的模拟住宅用户，不是评分员。严格使用 scenario 中的事实，保持前后一致，"
            "不得创造新的偏好。Agent 提问时，只披露与问题直接相关且尚未披露的 if_asked 事实；"
            "没有对应事实时，用普通用户口吻说不确定，并允许 Agent 在说明假设后决定。RESPOND 的"
            "用户消息必须直接回答 Agent，不得临时发明 scenario 之外的新疑问、新要求或新确认条件。"
            "消息中的每一项确定陈述都必须是本次 revealed_fact_ids 对应 value 的自然改写；Agent 给出"
            "多个选项但 scenario 没有对应事实时，不得任选一个，只能回答不确定。不得为了让对话自然"
            "而补充颜色、材料、房间、生活方式或程度偏好。"
            "一旦 Agent 回复已经包含具体实施前规划、材料/空间分配、执行方案或明确称为规划，就必须"
            "输出 CLOSE，无论该规划是否完整、是否遗漏事实、是否合格。不得为了帮助 Agent 改善规划而"
            "继续补充事实；这些遗漏由 grader 扣分。如果 Agent 结尾说‘确认后执行’、‘下一轮执行’或"
            "等待用户允许动手，也必须 CLOSE；执行许可不是需求事实，禁止用同意、满意、按此继续等"
            "消息作为 RESPOND。仅当 Agent 仍在提出需求问题且尚未给出具体规划时才 RESPOND。规划好坏"
            "不由你判断；CLOSE 只是终止信号。如果 Agent 回复只有需求问题、没有具体材料或空间规划，"
            "必须 RESPOND；即使 scenario 没有对应事实，也应按 unknown_answer 回答，不能因为无事实可"
            "披露而 CLOSE。只有在拿不准一段具体方案是否已构成规划时，才优先 CLOSE。"
            "只输出符合 output_json_contract 的 JSON 对象，不要 Markdown。"
    )
    required_keys = {"action", "message", "revealed_fact_ids", "reason"}
    valid_fact_ids = {fact["fact_id"] for fact in scenario["facts"]}
    last_error: Exception | None = None
    for attempt in range(2):
        decision = simulator.json_response(
            instructions=instructions,
            payload=payload,
            max_output_tokens=500,
        )
        try:
            if set(decision) != required_keys:
                raise RuntimeError(
                    f"JSON keys must be exactly {sorted(required_keys)}"
                )
            if decision["action"] not in {"RESPOND", "CLOSE"}:
                raise RuntimeError("action must be RESPOND or CLOSE")
            if not isinstance(decision["revealed_fact_ids"], list) or not all(
                isinstance(item, str) for item in decision["revealed_fact_ids"]
            ):
                raise RuntimeError("revealed_fact_ids must be a string array")
            if not isinstance(decision["reason"], str):
                raise RuntimeError("reason must be a string")
            revealed = set(decision["revealed_fact_ids"])
            if not revealed <= valid_fact_ids:
                raise RuntimeError(
                    f"revealed unknown facts: {sorted(revealed - valid_fact_ids)}"
                )
            if decision["action"] == "RESPOND" and not decision["message"]:
                raise RuntimeError("RESPOND requires a non-empty message")
            if decision["action"] == "CLOSE" and decision["message"] is not None:
                raise RuntimeError("CLOSE requires message=null")
            return decision
        except RuntimeError as error:
            last_error = error
            if attempt == 0:
                payload["validation_retry"] = (
                    f"上次输出无效：{error}。请严格按 output_json_contract 重答。"
                )
    raise RuntimeError(f"simulator response invalid twice: {last_error}")


def compact_product_history(history: dict[str, Any]) -> list[dict[str, Any]]:
    return [
        message
        for message in history.get("messages", [])
        if message.get("role") in {"user", "assistant", "tool"}
    ]


def extract_tool_calls(messages: list[dict[str, Any]]) -> list[dict[str, Any]]:
    calls: list[dict[str, Any]] = []
    for message_index, message in enumerate(messages):
        if message.get("role") != "assistant":
            continue
        for call in message.get("tool_calls", []) or []:
            calls.append(
                {
                    "message_index": message_index,
                    "id": call.get("id"),
                    "name": call.get("name"),
                    "args": call.get("args", {}),
                }
            )
    return calls


def build_grader_packet(
    dataset: dict[str, Any],
    scenario: dict[str, Any],
    episode: dict[str, Any],
) -> dict[str, Any]:
    disclosed = set(episode["disclosed_fact_ids"])
    turn_counts = {"user": 0, "assistant": 0}
    conversation = []
    for message in episode["transcript"]:
        role = message["role"]
        turn_counts[role] += 1
        prefix = "U" if role == "user" else "A"
        conversation.append(
            {
                "turn_id": f"{prefix}{turn_counts[role]}",
                "role": role,
                "content": message["content"],
            }
        )
    code_gate = {
        "verdict": "FAIL" if episode["update_scheme_succeeded"] else "PASS",
        "reason": (
            "fresh Design Run 的版本发生变化，说明规划阶段 update_scheme 已成功执行。"
            if episode["update_scheme_succeeded"]
            else "fresh Design Run 的版本未变化，规划阶段没有成功写入 Scheme。"
        ),
    }
    scene_manifest = json.loads(
        (PROJECT_ROOT / "scene_manifest.json").read_text(encoding="utf-8")
    )
    product_facts = {
        "source": "Agent System Prompt 的活动住宅事实",
        "designable_space_count": len(scene_manifest.get("rooms", [])),
        "rooms": [
            {"room_id": room.get("id"), "name": room.get("name_zh")}
            for room in scene_manifest.get("rooms", [])
        ],
    }
    return {
        "grader_kind": "codex_subagent",
        "rubric_version": dataset["dataset_version"],
        "scope": dataset["evaluation_scope"],
        "code_gates": {"no_premature_update": code_gate},
        "subagent_gates": {
            "plan_delivered": dataset["hard_gates"][1],
            "no_requirement_violation": dataset["hard_gates"][2],
            "no_fabrication": dataset["hard_gates"][3],
            "within_product_boundary": dataset["hard_gates"][4],
        },
        "soft_rubrics": {
            "requirement_understanding": dataset["soft_rubrics"][0],
            "question_quality": dataset["soft_rubrics"][1],
            "plan_fidelity": dataset["soft_rubrics"][2],
            "plan_actionability": dataset["soft_rubrics"][3],
        },
        "score_scale": {
            "0": "完全缺失或严重错误",
            "1": "存在明显严重问题",
            "2": "部分做到，但不足以认为合格",
            "3": "合格",
            "4": "优秀",
        },
        "pass_rule": "全部硬门禁 PASS，软分平均值至少 3，且没有单项低于 2。",
        "code_overrides": {
            "max_user_turns": "如果 stop_reason 为 max_user_turns，plan_delivered 必须判 FAIL。"
        },
        "product_facts": product_facts,
        "scenario": {
            "scenario_id": scenario["scenario_id"],
            "initial_message": scenario["initial_message"],
            "facts": [
                {
                    "fact_id": fact["fact_id"],
                    "value": fact["value"],
                    "disclosed": fact["fact_id"] in disclosed,
                }
                for fact in scenario["facts"]
            ],
            "must_resolve": scenario["must_resolve"],
            "must_reflect_in_plan": scenario["must_reflect_in_plan"],
            "forbidden": scenario["forbidden"],
        },
        "stop_reason": episode["stop_reason"],
        "conversation": conversation,
        "tool_calls": episode["tool_calls"],
        "grading_instructions": [
            "只根据本 JSON 评分，不读取项目文件或其他上下文。",
            "product_facts 是 Agent 在 System Prompt 中已知的权威事实，不得把与其一致的陈述判为编造。",
            "未披露事实只能用于判断 Agent 是否漏问 must_resolve，不能当成用户已表达需求。",
            "理由引用具体 turn_id，保持一到两句话。",
            "不要因为文案流畅而给高分，也不要要求固定标题、固定问题数量或唯一设计答案。",
            "只返回 output_contract 对应的 JSON。",
        ],
        "output_contract": {
            "gates": {
                gate_id: {"verdict": "PASS or FAIL", "reason": "evidence"}
                for gate_id in (
                    "plan_delivered",
                    "no_requirement_violation",
                    "no_fabrication",
                    "within_product_boundary",
                )
            },
            "scores": {
                rubric_id: {"score": "integer 0-4", "reason": "evidence"}
                for rubric_id in (
                    "requirement_understanding",
                    "question_quality",
                    "plan_fidelity",
                    "plan_actionability",
                )
            },
            "summary": "one concise sentence",
        },
    }


def finalize_subagent_grade(
    packet: dict[str, Any], judgment: dict[str, Any]
) -> dict[str, Any]:
    expected_gates = set(packet["subagent_gates"])
    expected_scores = set(packet["soft_rubrics"])
    gates = judgment.get("gates")
    scores = judgment.get("scores")
    if not isinstance(gates, dict) or set(gates) != expected_gates:
        raise ValueError("subagent grade has invalid gate keys")
    if not isinstance(scores, dict) or set(scores) != expected_scores:
        raise ValueError("subagent grade has invalid score keys")
    for gate_id, item in gates.items():
        if not isinstance(item, dict) or item.get("verdict") not in {"PASS", "FAIL"}:
            raise ValueError(f"invalid verdict for {gate_id}")
        if not isinstance(item.get("reason"), str) or not item["reason"].strip():
            raise ValueError(f"missing reason for {gate_id}")
    for rubric_id, item in scores.items():
        score = item.get("score") if isinstance(item, dict) else None
        if isinstance(score, bool) or not isinstance(score, int) or not 0 <= score <= 4:
            raise ValueError(f"invalid score for {rubric_id}")
        if not isinstance(item.get("reason"), str) or not item["reason"].strip():
            raise ValueError(f"missing reason for {rubric_id}")
    if not isinstance(judgment.get("summary"), str) or not judgment["summary"].strip():
        raise ValueError("subagent grade requires summary")

    merged_gates = {**packet["code_gates"], **gates}
    if packet["stop_reason"] == "max_user_turns":
        merged_gates["plan_delivered"] = {
            "verdict": "FAIL",
            "reason": "达到最大模拟用户回复次数后仍未识别为规划交付。",
        }
    score_values = [item["score"] for item in scores.values()]
    score_average = round(sum(score_values) / len(score_values), 3)
    overall_pass = (
        all(item["verdict"] == "PASS" for item in merged_gates.values())
        and score_average >= 3.0
        and min(score_values) >= 2
    )
    return {
        "grader_kind": "codex_subagent",
        "gates": merged_gates,
        "scores": scores,
        "score_average": score_average,
        "overall_pass": overall_pass,
        "summary": judgment["summary"],
    }


def save_json(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    os.replace(temporary, path)


def run_scenario(
    *,
    dataset: dict[str, Any],
    scenario: dict[str, Any],
    api: AgentApiClient,
    simulator: DeepSeekSimulator,
    output_path: Path,
    grader_packet_path: Path,
) -> dict[str, Any]:
    episode: dict[str, Any] = {
        "episode_id": f"ep_{uuid4().hex}",
        "scenario_id": scenario["scenario_id"],
        "dataset_version": dataset["dataset_version"],
        "started_at": utc_now(),
        "finished_at": None,
        "thread_id": None,
        "design_run_id": None,
        "base_version_id": None,
        "final_version_id": None,
        "stop_reason": None,
        "simulated_user_replies": 0,
        "disclosed_fact_ids": [],
        "transcript": [],
        "simulator_decisions": [],
        "tool_calls": [],
        "update_scheme_attempted": False,
        "update_scheme_succeeded": False,
        "grading_status": "not_ready",
        "grader_packet_path": None,
        "error": None,
    }
    save_json(output_path, episode)
    try:
        session = api.create_fresh_session(
            f"eval:{scenario['scenario_id']}:{episode['episode_id'][-8:]}"
        )
        episode["thread_id"] = session["thread_id"]
        episode["design_run_id"] = session["design_run_id"]
        episode["base_version_id"] = session["current_version_id"]
        disclosed = {
            fact["fact_id"]
            for fact in scenario["facts"]
            if fact["disclosure"] == "initial"
        }
        episode["disclosed_fact_ids"] = sorted(disclosed)
        user_message = scenario["initial_message"]

        while True:
            episode["transcript"].append({"role": "user", "content": user_message})
            response = api.chat(episode["thread_id"], user_message)
            agent_reply = response["reply"]
            episode["transcript"].append(
                {"role": "assistant", "content": agent_reply}
            )

            history = api.history(episode["thread_id"])
            compact_history = compact_product_history(history)
            episode["tool_calls"] = extract_tool_calls(compact_history)
            episode["update_scheme_attempted"] = any(
                call["name"] == "update_scheme" for call in episode["tool_calls"]
            )
            episode["final_version_id"] = history.get("current_version_id")
            episode["update_scheme_succeeded"] = (
                episode["final_version_id"] != episode["base_version_id"]
            )
            save_json(output_path, episode)

            if episode["update_scheme_succeeded"]:
                episode["stop_reason"] = "premature_update_scheme"
                break

            decision = simulate_user(
                simulator, scenario, episode["transcript"], disclosed
            )
            episode["simulator_decisions"].append(decision)
            disclosed.update(decision["revealed_fact_ids"])
            episode["disclosed_fact_ids"] = sorted(disclosed)
            save_json(output_path, episode)
            if decision["action"] == "CLOSE":
                episode["stop_reason"] = "close"
                break
            if episode["simulated_user_replies"] >= scenario["max_user_turns"]:
                episode["stop_reason"] = "max_user_turns"
                break
            episode["simulated_user_replies"] += 1
            user_message = decision["message"]

        run = api.design_run(episode["design_run_id"])
        episode["final_version_id"] = run["current_version_id"]
        episode["update_scheme_succeeded"] = (
            episode["final_version_id"] != episode["base_version_id"]
        )
        grader_packet = build_grader_packet(dataset, scenario, episode)
        save_json(grader_packet_path, grader_packet)
        episode["grading_status"] = "pending_subagent"
        episode["grader_packet_path"] = grader_packet_path.name
    except Exception as error:  # noqa: BLE001
        episode["stop_reason"] = episode["stop_reason"] or "error"
        episode["error"] = f"{type(error).__name__}: {error}"
    finally:
        episode["finished_at"] = utc_now()
        save_json(output_path, episode)
    return episode


def select_scenarios(
    dataset: dict[str, Any], requested: list[str], run_all: bool
) -> list[dict[str, Any]]:
    scenarios = dataset["scenarios"]
    if run_all:
        return scenarios
    by_id = {scenario["scenario_id"]: scenario for scenario in scenarios}
    unknown = [scenario_id for scenario_id in requested if scenario_id not in by_id]
    if unknown:
        raise ValueError(f"unknown scenario IDs: {unknown}")
    return [by_id[scenario_id] for scenario_id in requested]


def finalize_run_directories(run_directories: list[Path]) -> dict[str, Any]:
    by_scenario: dict[str, dict[str, Any]] = {}
    for run_directory in run_directories:
        for packet_path in sorted(run_directory.glob("*.grader.json")):
            scenario_id = packet_path.name.removesuffix(".grader.json")
            judgment_path = run_directory / f"{scenario_id}.judgment.json"
            if not judgment_path.is_file():
                raise FileNotFoundError(f"missing subagent judgment: {judgment_path}")
            packet = json.loads(packet_path.read_text(encoding="utf-8"))
            judgment = json.loads(judgment_path.read_text(encoding="utf-8"))
            grade = finalize_subagent_grade(packet, judgment)
            grade_path = run_directory / f"{scenario_id}.grade.json"
            save_json(grade_path, grade)
            by_scenario[scenario_id] = {
                "scenario_id": scenario_id,
                "source_directory": str(run_directory.resolve()),
                "stop_reason": packet["stop_reason"],
                **grade,
            }
    episodes = [by_scenario[key] for key in sorted(by_scenario)]
    return {
        "created_at": utc_now(),
        "scenario_count": len(episodes),
        "pass_count": sum(1 for episode in episodes if episode["overall_pass"]),
        "fail_count": sum(1 for episode in episodes if not episode["overall_pass"]),
        "episodes": episodes,
    }


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Run dimension-one planning evaluations through the Agent FastAPI."
    )
    parser.add_argument("--dataset", type=Path, default=DEFAULT_DATASET)
    parser.add_argument("--scenario", action="append", default=[], help="Scenario ID; repeatable")
    parser.add_argument("--all", action="store_true", help="Run all dataset scenarios")
    parser.add_argument("--list", action="store_true", help="List scenarios and exit")
    parser.add_argument("--dry-run", action="store_true", help="Validate selection without API calls")
    parser.add_argument(
        "--finalize-run",
        action="append",
        default=[],
        type=Path,
        help="Run directory containing grader and judgment JSON; repeatable",
    )
    parser.add_argument(
        "--finalize-output",
        type=Path,
        help="Combined grade summary path; defaults to the first run directory",
    )
    parser.add_argument(
        "--api-url",
        default=os.getenv("EVAL_AGENT_API_URL", "http://127.0.0.1:8000"),
    )
    parser.add_argument(
        "--token", default=os.getenv("EVAL_AGENT_API_TOKEN") or os.getenv("AGENT_API_TOKEN")
    )
    parser.add_argument("--api-timeout", type=float, default=300.0)
    parser.add_argument("--simulator-timeout", type=float, default=180.0)
    parser.add_argument("--results-dir", type=Path, default=DEFAULT_RESULTS_DIR)
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")
        sys.stderr.reconfigure(encoding="utf-8")
    load_local_env(PROJECT_ROOT / ".env")
    args = parse_args(argv)
    dataset = load_dataset(args.dataset.resolve())
    if args.finalize_run:
        run_directories = [path.resolve() for path in args.finalize_run]
        summary = finalize_run_directories(run_directories)
        output_path = (
            args.finalize_output.resolve()
            if args.finalize_output
            else run_directories[0] / "evaluation_summary.json"
        )
        save_json(output_path, summary)
        print(
            f"Finalized {summary['scenario_count']} scenario(s): "
            f"PASS={summary['pass_count']} FAIL={summary['fail_count']}"
        )
        print(f"Summary: {output_path}")
        return 0
    if args.list:
        for scenario in dataset["scenarios"]:
            print(f"{scenario['scenario_id']}\t{scenario['category']}\t{scenario['title']}")
        return 0
    if not args.all and not args.scenario:
        print("Select at least one --scenario or pass --all.", file=sys.stderr)
        return 2
    selected = select_scenarios(dataset, args.scenario, args.all)
    if args.dry_run:
        print(f"Dataset valid; selected {len(selected)} scenario(s).")
        return 0

    run_stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    run_dir = args.results_dir.resolve() / run_stamp
    run_dir.mkdir(parents=True, exist_ok=False)
    api = AgentApiClient(args.api_url, args.token, args.api_timeout)
    simulator = DeepSeekSimulator(args.simulator_timeout)
    results: list[dict[str, Any]] = []
    try:
        for index, scenario in enumerate(selected, start=1):
            print(f"[{index}/{len(selected)}] {scenario['scenario_id']} ...", flush=True)
            output_path = run_dir / f"{scenario['scenario_id']}.json"
            grader_packet_path = run_dir / f"{scenario['scenario_id']}.grader.json"
            episode = run_scenario(
                dataset=dataset,
                scenario=scenario,
                api=api,
                simulator=simulator,
                output_path=output_path,
                grader_packet_path=grader_packet_path,
            )
            results.append(episode)
            status = "ERROR" if episode.get("error") else "COLLECTED"
            print(
                f"  {status}: stop={episode['stop_reason']} "
                f"grading={episode['grading_status']}"
            )
    finally:
        simulator.close()

    summary = {
        "dataset_version": dataset["dataset_version"],
        "simulator_model": DEEPSEEK_SIMULATOR_MODEL,
        "simulator_thinking": "disabled",
        "grader": "codex_subagent",
        "api_url": args.api_url,
        "created_at": utc_now(),
        "scenario_count": len(results),
        "pending_grade_count": sum(
            1 for result in results if result["grading_status"] == "pending_subagent"
        ),
        "error_count": sum(1 for result in results if result.get("error")),
        "episodes": [
            {
                "scenario_id": result["scenario_id"],
                "episode_id": result["episode_id"],
                "thread_id": result["thread_id"],
                "design_run_id": result["design_run_id"],
                "stop_reason": result["stop_reason"],
                "grading_status": result["grading_status"],
                "grader_packet_path": result["grader_packet_path"],
                "error": result.get("error"),
            }
            for result in results
        ],
    }
    save_json(run_dir / "summary.json", summary)
    print(f"Results: {run_dir}")
    return 1 if summary["error_count"] else 0


if __name__ == "__main__":
    raise SystemExit(main())
