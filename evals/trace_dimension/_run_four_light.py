"""临时脚本：并行跑 4 个轻场景（LLM/对话并行，渲染排队），串行评分。

用法：E:\\python\\python.exe evals/trace_dimension/_run_four_light.py
"""
from __future__ import annotations

import json
import os
import sys
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[2]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

# 从 .env 加载 grader 需要的 key
for line in (PROJECT_ROOT / ".env").read_text(encoding="utf-8").splitlines():
    line = line.strip()
    if line and not line.startswith("#") and "=" in line:
        k, v = line.split("=", 1)
        os.environ.setdefault(k.strip(), v.strip().strip("'").strip('"'))

from evals.trace_dimension.grader import (
    build_trace_text,
    check_hard_gates,
    finalize,
    llm_grade_soft_rubrics,
    load_manifest,
    load_rubric,
)
from evals.trace_dimension.runner import (
    _find_thread_id,
    _load_langsmith_env,
    extract_trace,
    fetch_conversation,
    run_scenario,
)

SCENARIOS = ["trap_retry_08", "norm_room_09", "norm_light_10", "mixed_conflict_12"]
HERE = Path(__file__).resolve().parent


def load_dataset() -> dict:
    return json.loads((HERE / "dataset_v1.json").read_text(encoding="utf-8"))


def main() -> int:
    dataset = load_dataset()
    by_id = {s["scenario_id"]: s for s in dataset["scenarios"]}
    selected = [by_id[sid] for sid in SCENARIOS]

    # 阶段 1：4 个场景并行驱动真实 Agent（各占独立 thread / design_run）
    results: dict[str, str | None] = {}
    print(f"[phase1] 并行驱动 {len(selected)} 个场景…", flush=True)
    with ThreadPoolExecutor(max_workers=4) as ex:
        futures = {ex.submit(run_scenario, s): s["scenario_id"] for s in selected}
        for fut in as_completed(futures):
            sid = futures[fut]
            try:
                dri = fut.result()
                results[sid] = dri
                print(f"  [done] {sid} -> {dri}", flush=True)
            except Exception as error:  # noqa: BLE001
                results[sid] = None
                print(f"  [fail] {sid}: {error}", flush=True)

    # 阶段 2：串行评分（LangSmith 只拉一次）
    from langsmith import Client
    api_key, endpoint = _load_langsmith_env()
    client = Client(api_key=api_key, api_url=endpoint)
    scene = load_manifest("scene")
    assets = load_manifest("asset")
    rubric = load_rubric()

    out = []
    for s in selected:
        sid = s["scenario_id"]
        dri = results.get(sid)
        if not dri:
            out.append({"scenario_id": sid, "overall_pass": "ERROR", "error": "no design_run_id"})
            continue
        trace = extract_trace(client, dri)
        gates = check_hard_gates(trace, scene, assets)
        thread_id = _find_thread_id(client, dri)
        conv = fetch_conversation(thread_id) if thread_id else []
        trace_text = build_trace_text(trace, s, conv)
        soft, usage = llm_grade_soft_rubrics(trace_text, rubric)
        result = finalize(gates, soft)
        result.update(
            design_run_id=dri,
            scenario_id=sid,
            grader_usage=usage,
            tool_call_count=len(trace.tool_calls),
            llm_call_count=len(trace.llm_calls),
            total_llm_latency_ms=sum(c.latency_ms for c in trace.llm_calls),
        )
        out.append(result)
        print(f"  [grade] {sid} -> {result['overall_pass']}", flush=True)

    dest = HERE / "results" / "latest_summary_light4.json"
    dest.parent.mkdir(parents=True, exist_ok=True)
    dest.write_text(json.dumps(out, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"\n结果写入 {dest}", flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
