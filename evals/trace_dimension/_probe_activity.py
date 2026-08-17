"""临时脚本：检查最近 25 分钟 LangSmith 是否有新 span（Agent 是否在推进）。"""
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from evals.trace_dimension.runner import _load_langsmith_env
from langsmith import Client

api_key, endpoint = _load_langsmith_env()
client = Client(api_key=api_key, api_url=endpoint)
cutoff = datetime.now(timezone.utc) - timedelta(minutes=25)
runs = list(client.list_runs(project_name="house-design-agent", limit=400))
recent = [r for r in runs if r.start_time and r.start_time.replace(tzinfo=timezone.utc) > cutoff]
print("runs newer than 25min:", len(recent))
by_type: dict[str, int] = {}
for r in recent:
    by_type[r.run_type] = by_type.get(r.run_type, 0) + 1
print("by type:", by_type)
recent.sort(key=lambda r: r.start_time, reverse=True)
for r in recent[:15]:
    name = (r.name or "?").replace("house-design-tool:", "")
    ts = str(r.start_time)[11:19] if r.start_time else "?"
    print(f"  {ts} {r.run_type:5s} {name}")
