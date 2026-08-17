"""临时脚本：核实 skip_filter_01 与 harmony_single_04 的 agent 真实行为证据。"""
from __future__ import annotations

import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from evals.trace_dimension.runner import (
    _find_thread_id,
    _load_langsmith_env,
    _trace_ids,
    fetch_conversation,
)

RUNS = {
    "skip_filter_01": "run_20260815T015633326547_6a00d5a1",
    "harmony_single_04": "run_20260815T021108977980_336168b0",
}


def main() -> int:
    from langsmith import Client
    api_key, endpoint = _load_langsmith_env()
    client = Client(api_key=api_key, api_url=endpoint)

    for name, rid in RUNS.items():
        print(f"\n########## {name} ({rid}) ##########")

        # 1) 完整对话（含 Agent 最终回复）
        thread_id = _find_thread_id(client, rid)
        conv = fetch_conversation(thread_id) if thread_id else []
        print(f"\n--- 对话 ({len(conv)} turns) ---")
        for role, content in conv:
            print(f"[{role}] {content}")
            print()

        # 2) 关键 tool 入参
        trace_ids = _trace_ids(client, rid)
        runs = list(client.list_runs(project_name="house-design-agent", limit=800))
        run_set = [r for r in runs if (getattr(r, "trace_id", None) or r.id) in trace_ids]
        tool_runs = [r for r in run_set if r.run_type == "tool" and r.start_time]
        tool_runs.sort(key=lambda r: r.start_time)
        print(f"\n--- 关键工具调用 ({len(tool_runs)} total) ---")
        for r in tool_runs:
            name = (getattr(r, "name", "?") or "").split(":")[-1]
            if name not in {"filter_assets", "update_scheme", "get_asset_card_by_id", "observe_room"}:
                continue
            inputs = r.inputs or {}
            args = inputs.get("args", {})
            t = r.start_time.isoformat(timespec="milliseconds") if r.start_time else "?"
            print(f"[{name}] {t} -> {json.dumps(args, ensure_ascii=False)}")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
