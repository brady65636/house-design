"""维度三评估 runner：驱动真实 Agent 跑场景 -> 从 LangSmith 提取轨迹 -> 用 grader 判定。

用法：
    E:\\python\\python.exe evals/trace_dimension/runner.py --scenario trap_skip_filter_01

轨迹提取依赖 LangSmith（需 .env 配好 HOUSE_DESIGN_LANGSMITH_*，且后端 tracing 开启）。
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[2]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

import httpx

from evals.trace_dimension.grader import (
    LlmCall,
    ToolCall,
    Trace,
    build_trace_text,
    check_hard_gates,
    finalize,
    llm_grade_soft_rubrics,
    load_manifest,
    load_rubric,
)

BASE_URL = "http://127.0.0.1:8000"
DATASET_PATH = Path(__file__).resolve().parent / "dataset_v1.json"


def load_dataset() -> dict:
    return json.loads(DATASET_PATH.read_text(encoding="utf-8"))


# ---------------------------------------------------------------------------
# 场景驱动：创建 fresh session，发任务，用简单规则扮演用户
# ---------------------------------------------------------------------------

def _answer_from_facts(scenario: dict) -> str:
    facts = [f for f in scenario.get("user_facts", []) if f.get("disclosure") == "if_asked"]
    if not facts:
        return "按你的判断来，确认后开始执行。"
    parts = [f["value"] for f in facts]
    return "；".join(parts) + "。就按这个执行。"


def run_scenario(scenario: dict, base_url: str = BASE_URL) -> str:
    """驱动一个场景，返回 design_run_id。简单规则模拟用户，不依赖 DeepSeek 模拟器。"""
    sess = httpx.post(
        f"{base_url}/api/sessions",
        json={"title": scenario["scenario_id"], "mode": "fresh"},
        timeout=60,
    ).json()
    thread = sess["thread_id"]
    design_run_id = sess["design_run_id"]

    max_turns = scenario.get("max_user_turns", 5)
    reply = scenario["initial_message"]
    for turn in range(max_turns):
        chat = httpx.post(
            f"{base_url}/api/chat",
            json={"thread_id": thread, "message": reply},
            timeout=1800,
        ).json()
        assistant_reply = chat.get("reply", "")
        # 简单启发式：如果回复在提问（含问号），用 facts 回答；否则视为已给规划/执行，发确认。
        if "？" in assistant_reply or "?" in assistant_reply:
            reply = _answer_from_facts(scenario)
        else:
            reply = "确认，开始执行。"
    return design_run_id


# ---------------------------------------------------------------------------
# 轨迹提取：从 LangSmith 拉 llm span（reasoning/latency/usage）+ tool span
# ---------------------------------------------------------------------------

def _load_langsmith_env() -> tuple[str, str]:
    env = {}
    for line in (PROJECT_ROOT / ".env").read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if line and not line.startswith("#") and "=" in line:
            k, v = line.split("=", 1)
            env[k.strip()] = v.strip().strip("'").strip('"')
    return env["HOUSE_DESIGN_LANGSMITH_API_KEY"], env.get("HOUSE_DESIGN_LANGSMITH_ENDPOINT", "https://api.smith.langchain.com")


def _trace_ids(client, design_run_id: str) -> set:
    runs = list(client.list_runs(project_name="house-design-agent", limit=800))
    ids = set()
    for r in runs:
        if (r.metadata or {}).get("design_run_id") == design_run_id:
            ids.add(getattr(r, "trace_id", None) or r.id)
    return ids


def _find_thread_id(client, design_run_id: str) -> str | None:
    runs = list(client.list_runs(project_name="house-design-agent", limit=800))
    for r in runs:
        md = r.metadata or {}
        if md.get("design_run_id") == design_run_id and md.get("thread_id"):
            return md["thread_id"]
    return None


def _content_to_text(content) -> str:
    """把 API 返回的 content（str 或 block 列表）压成纯文本。"""
    if isinstance(content, str):
        return content
    if isinstance(content, list):
        parts = []
        for block in content:
            if isinstance(block, dict):
                text = block.get("text") or block.get("content")
                if text:
                    parts.append(str(text))
            else:
                parts.append(str(block))
        return "\n".join(parts)
    return str(content or "")


def fetch_conversation(thread_id: str, base_url: str = BASE_URL) -> list[tuple[str, str]]:
    """从后端消息历史拿完整对话（user + assistant 轮次，按序）。"""
    try:
        hist = httpx.get(f"{base_url}/api/sessions/{thread_id}/messages", timeout=60).json()
    except Exception:
        return []
    turns: list[tuple[str, str]] = []
    for m in hist.get("messages", []):
        role = m.get("role")
        if role == "user":
            text = _content_to_text(m.get("content", ""))
            if text.strip():
                turns.append(("用户", text))
        elif role == "assistant":
            text = _content_to_text(m.get("content", ""))
            if text.strip():
                turns.append(("Agent", text))
    return turns


def extract_trace(client, design_run_id: str) -> Trace:
    """从 LangSmith 提取一次跑盘的 Trace（tool_calls + llm_calls，按时间序关联）。"""
    runs = list(client.list_runs(project_name="house-design-agent", limit=800))
    trace_ids = _trace_ids(client, design_run_id)
    run_set = [r for r in runs if (getattr(r, "trace_id", None) or r.id) in trace_ids]

    llm_runs = [r for r in run_set if r.run_type == "llm" and r.start_time]
    tool_runs = [r for r in run_set if r.run_type == "tool" and r.start_time]

    # 按时间排序，把 tool span 归属到它之前最近的 llm span
    events = []
    for r in llm_runs:
        events.append((r.start_time, "llm", r))
    for r in tool_runs:
        events.append((r.start_time, "tool", r))
    events.sort(key=lambda e: e[0])

    tool_calls: list[ToolCall] = []
    llm_calls: list[LlmCall] = []
    tool_seq = 0
    llm_seq = 0
    current_llm: LlmCall | None = None

    for _, kind, r in events:
        if kind == "llm":
            lat = (r.end_time - r.start_time).total_seconds() * 1000 if r.end_time else 0
            reasoning = (r.outputs or {}).get("reasoning_summary", "")
            usage = (r.outputs or {}).get("usage")
            llm_seq += 1
            current_llm = LlmCall(sequence=llm_seq, latency_ms=lat, reasoning=reasoning, usage=usage)
            llm_calls.append(current_llm)
        elif kind == "tool":
            tool_seq += 1
            name = (r.name or "").replace("house-design-tool:", "")
            args = (r.inputs or {}).get("args") or {}
            result = _tool_result_text(r.outputs)
            call = ToolCall(sequence=tool_seq, name=name, args=args, result=result)
            tool_calls.append(call)
            if current_llm is not None:
                current_llm.tool_calls.append(call)

    return Trace(design_run_id=design_run_id, tool_calls=tool_calls, llm_calls=llm_calls)


def _tool_result_text(outputs) -> str:
    if not isinstance(outputs, dict):
        return str(outputs)
    # execute_tool 里 span.end(outputs=_trace_tool_output(result))：result_type=text -> content；visual -> summary
    if outputs.get("result_type") == "text":
        return str(outputs.get("content", ""))
    if outputs.get("result_type") == "visual":
        return str(outputs.get("summary", ""))
    return json.dumps(outputs, ensure_ascii=False)


# ---------------------------------------------------------------------------
# 判定
# ---------------------------------------------------------------------------

def grade_design_run(client, design_run_id: str, scenario: dict | None = None) -> dict:
    trace = extract_trace(client, design_run_id)
    scene = load_manifest("scene")
    assets = load_manifest("asset")
    gates = check_hard_gates(trace, scene, assets)
    thread_id = _find_thread_id(client, design_run_id)
    conversation = fetch_conversation(thread_id) if thread_id else []
    trace_text = build_trace_text(trace, scenario, conversation)
    rubric = load_rubric()
    soft_verdicts, usage_summary = llm_grade_soft_rubrics(trace_text, rubric)
    result = finalize(gates, soft_verdicts)
    result["design_run_id"] = design_run_id
    result["grader_usage"] = usage_summary
    result["tool_call_count"] = len(trace.tool_calls)
    result["llm_call_count"] = len(trace.llm_calls)
    result["total_llm_latency_ms"] = sum(c.latency_ms for c in trace.llm_calls)
    return result


# ---------------------------------------------------------------------------
# main
# ---------------------------------------------------------------------------

def main() -> int:
    parser = argparse.ArgumentParser(description="维度三评估 runner")
    parser.add_argument("--scenario", action="append", default=[], help="只跑指定场景，可重复")
    parser.add_argument("--subset", default=None, help="smoke_6 / traps_8 / full_12 / all")
    parser.add_argument("--grade-only", default=None, help="只对已跑过的 design_run_id 判定")
    args = parser.parse_args()

    dataset = load_dataset()
    scenarios = dataset["scenarios"]

    # 选场景
    if args.scenario:
        selected = [s for s in scenarios if s["scenario_id"] in args.scenario]
    elif args.subset == "smoke_6":
        selected = [s for s in scenarios if s["trap_category"] != "control"][:6]
    elif args.subset == "traps_8":
        selected = [s for s in scenarios if s["trap_category"] != "control"]
    elif args.subset in (None, "all", "full_12"):
        selected = scenarios
    else:
        raise SystemExit(f"unknown subset: {args.subset}")

    # LangSmith client
    from langsmith import Client
    api_key, endpoint = _load_langsmith_env()
    client = Client(api_key=api_key, api_url=endpoint)

    # 只判定已跑的
    if args.grade_only:
        result = grade_design_run(client, args.grade_only)
        print(json.dumps(result, ensure_ascii=False, indent=2))
        return 0

    results = []
    for scenario in selected:
        print(f"[run] {scenario['scenario_id']} ({scenario['title']})", flush=True)
        try:
            design_run_id = run_scenario(scenario)
        except Exception as error:  # noqa: BLE001
            print(f"  !! 场景执行失败：{error}", flush=True)
            results.append({
                "scenario_id": scenario["scenario_id"],
                "expected_anti_patterns": scenario["anti_patterns"],
                "error": str(error),
                "overall_pass": "ERROR",
            })
            continue
        print(f"  design_run_id={design_run_id}", flush=True)
        result = grade_design_run(client, design_run_id, scenario)
        result["scenario_id"] = scenario["scenario_id"]
        result["expected_anti_patterns"] = scenario["anti_patterns"]
        results.append(result)
        soft_fails = [k for k, v in result.get("soft_rubrics", {}).items() if isinstance(v, dict) and v.get("verdict") == "FAIL"]
        print(f"  -> 硬门禁通过={result['hard_pass']}, 软rubric FAIL={soft_fails}, 整体={result['overall_pass']}", flush=True)

    out = PROJECT_ROOT / "evals" / "trace_dimension" / "results" / "latest_summary.json"
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(results, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"\n结果写入 {out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
