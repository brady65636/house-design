"""临时脚本：打印某 design_run 里所有 filter_assets 的原始入参（核实 anchor 落地）。"""
from __future__ import annotations

import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from evals.trace_dimension.runner import _load_langsmith_env, _trace_ids

RUN_ID = "run_20260815T021108977980_336168b0"


def main() -> int:
    from langsmith import Client
    api_key, endpoint = _load_langsmith_env()
    client = Client(api_key=api_key, api_url=endpoint)

    trace_ids = _trace_ids(client, RUN_ID)
    runs = list(client.list_runs(project_name="house-design-agent", limit=800))
    run_set = [r for r in runs if (getattr(r, "trace_id", None) or r.id) in trace_ids]

    # 打印所有 filter_assets / update_scheme / set_design_work_type 的 tool span，按时间序
    tool_runs = [r for r in run_set if r.run_type == "tool" and r.start_time]
    tool_runs.sort(key=lambda r: r.start_time)
    print(f"[info] total tool spans: {len(tool_runs)}")
    for r in tool_runs:
        name = getattr(r, "name", "?")
        start = r.start_time.isoformat(timespec="milliseconds") if r.start_time else "?"
        print(f"\n=== [{name}] @ {start} ===")
        inputs = r.inputs or {}
        print(json.dumps(inputs, ensure_ascii=False, indent=2, default=str))

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
