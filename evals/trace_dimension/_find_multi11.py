"""临时脚本：找 norm_multi_11 的 design_run_id（按时间窗口内最新的 run 分组）。"""
import sys
from collections import Counter
from datetime import datetime, timedelta, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from evals.trace_dimension.runner import _load_langsmith_env
from langsmith import Client

api_key, endpoint = _load_langsmith_env()
client = Client(api_key=api_key, api_url=endpoint)

cutoff = datetime.now(timezone.utc) - timedelta(minutes=60)
runs = list(client.list_runs(project_name="house-design-agent", limit=4000))
runs = [r for r in runs if r.start_time and r.start_time.replace(tzinfo=timezone.utc) > cutoff]

groups: dict[str, dict] = {}
for r in runs:
    md = r.metadata or {}
    dri = md.get("design_run_id") or "NO_DESIGN_RUN_ID"
    g = groups.setdefault(dri, {"llm": 0, "tool": 0, "chain": 0, "tools": Counter(),
                                "start": None, "end": None})
    g[r.run_type] = g.get(r.run_type, 0) + 1
    if r.run_type == "tool":
        g["tools"][(r.name or "?").replace("house-design-tool:", "")] += 1
    if r.start_time:
        st = r.start_time.replace(tzinfo=timezone.utc)
        g["start"] = st if g["start"] is None else min(g["start"], st)
    if r.end_time:
        et = r.end_time.replace(tzinfo=timezone.utc)
        g["end"] = et if g["end"] is None else max(g["end"], et)

rows = []
for dri, g in groups.items():
    dur = (g["end"] - g["start"]).total_seconds() if g["start"] and g["end"] else 0
    rows.append((dur, dri, g))
rows.sort(reverse=True)

print(f"groups in last 60min: {len(rows)}")
for dur, dri, g in rows[:6]:
    print(f"\n### {dri}  | wall={dur/60:.1f} min")
    print(f"  llm={g['llm']} tool={g['tool']} chain={g['chain']}")
    top = g["tools"].most_common(10)
    print("  tools: " + ", ".join(f"{n}×{c}" for n, c in top))
