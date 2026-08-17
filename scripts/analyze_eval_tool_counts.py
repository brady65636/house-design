import json, glob, os, statistics

files = glob.glob("evals/outcome_dimension/results/**/episode.json", recursive=True)

# 只看 20260814_152601 和 20260814_162714 两个成功批次（都是 close 完成）
success_runs = {"20260814_152601", "20260814_162714"}
rows = []
for f in sorted(files):
    parts = f.split(os.sep)
    run_dir = parts[-3]
    if run_dir not in success_runs:
        continue
    try:
        d = json.load(open(f, encoding="utf-8"))
    except Exception:
        continue
    if d.get("stop_reason") != "close":
        continue
    rows.append({
        "scenario": d.get("scenario_id"),
        "tools": d.get("tool_call_count"),
        "turns": d.get("conversation_turn_count"),
        "evidence": d.get("render_evidence_count"),
    })

print("=== successful closed episodes (20260814 权威批次) ===")
for r in sorted(rows, key=lambda x: x["tools"]):
    print(f"  {r['scenario']:<32} tools={r['tools']:<3} turns={r['turns']:<2} render_evidence={r['evidence']}")

tools = sorted(r["tools"] for r in rows)
turns = sorted(r["turns"] for r in rows)
evidence = sorted(r["evidence"] for r in rows if isinstance(r["evidence"], int))

def stats(name, data):
    print(f"\n{name}: n={len(data)}")
    print(f"  min={min(data)} max={max(data)} mean={round(statistics.mean(data),1)} median={statistics.median(data)} p90={data[int(len(data)*0.9)-1] if len(data)>=10 else 'n/a'}")
    print(f"  sorted={data}")

stats("tool_call_count", tools)
stats("conversation_turn_count", turns)
stats("render_evidence_count", evidence)

# 划分：整屋综合 vs 单点轻改
print("\n=== 按任务复杂度分组 ===")
whole = [r for r in rows if r["scenario"] in ("whole_home_warm_cohesive_12", "master_suite_continuity_08", "public_dining_continuity_06", "kitchen_public_transition_07")]
light = [r for r in rows if r not in whole]
for name, group in [("跨空间/整屋/联动", whole), ("单房间/单点", light)]:
    t = sorted(r["tools"] for r in group)
    print(f"{name}: n={len(t)} tools min={min(t)} max={max(t)} mean={round(statistics.mean(t),1)}")
