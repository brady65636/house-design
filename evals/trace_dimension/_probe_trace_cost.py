"""临时脚本：统计某时间段内各 design_run 的真实成本构成（工具/LLM/耗时/token）。"""
import sys
from collections import Counter
from datetime import datetime, timedelta, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from evals.trace_dimension.runner import _load_langsmith_env
from langsmith import Client

api_key, endpoint = _load_langsmith_env()
client = Client(api_key=api_key, api_url=endpoint)

# 覆盖今天 04:40 之后的所有 run（serial_06 和 batch_07 都在这之后）
cutoff = datetime.now(timezone.utc) - timedelta(hours=4)
runs = list(client.list_runs(project_name="house-design-agent", limit=4000))
runs = [r for r in runs if r.start_time and r.start_time.replace(tzinfo=timezone.utc) > cutoff]

groups: dict[str, dict] = {}
for r in runs:
    md = r.metadata or {}
    dri = md.get("design_run_id") or "NO_DESIGN_RUN_ID"
    g = groups.setdefault(dri, {"llm": 0, "tool": 0, "chain": 0, "tools": Counter(),
                                "start": None, "end": None, "usage_in": 0, "usage_out": 0, "usage_cached": 0})
    g[r.run_type] = g.get(r.run_type, 0) + 1
    if r.run_type == "tool":
        name = (r.name or "?").replace("house-design-tool:", "")
        g["tools"][name] += 1
    if r.start_time:
        st = r.start_time.replace(tzinfo=timezone.utc)
        g["start"] = st if g["start"] is None else min(g["start"], st)
    if r.end_time:
        et = r.end_time.replace(tzinfo=timezone.utc)
        g["end"] = et if g["end"] is None else max(g["end"], et)
    if r.run_type == "llm":
        out = r.outputs or {}
        u = out.get("usage") or {}
        g["usage_in"] += int(u.get("input_tokens") or 0)
        g["usage_out"] += int(u.get("output_tokens") or 0)
        det = u.get("input_tokens_details") or {}
        g["usage_cached"] += int(det.get("cached_tokens") or 0)

rows = []
for dri, g in groups.items():
    dur = (g["end"] - g["start"]).total_seconds() if g["start"] and g["end"] else 0
    rows.append((dur, dri, g))
rows.sort(reverse=True)

print(f"runs in window: {len(runs)} spans, groups: {len(rows)}")
print("=" * 100)
for dur, dri, g in rows[:12]:
    print(f"\n### {dri}  |  wall={dur/60:.1f} min")
    print(f"  llm={g['llm']} tool={g['tool']} chain={g['chain']}")
    print(f"  usage: in={g['usage_in']:,} cached={g['usage_cached']:,} out={g['usage_out']:,}")
    top = g["tools"].most_common(12)
    print("  tools: " + ", ".join(f"{n}×{c}" for n, c in top))
