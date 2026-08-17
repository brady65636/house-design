"""临时脚本：打印 norm_multi_11 run 的完整工具调用序列（含推理摘要），聚焦 observe_home_harmony 与 Critic 的相对顺序。"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from evals.trace_dimension.runner import _load_langsmith_env, _trace_ids
from evals.trace_dimension.grader import build_trace_text, load_rubric
from evals.trace_dimension.runner import _find_thread_id, fetch_conversation, extract_trace

RUN_ID = "run_20260815T062531256343_ea834a16"

api_key, endpoint = _load_langsmith_env()
from langsmith import Client
client = Client(api_key=api_key, api_url=endpoint)

trace = extract_trace(client, RUN_ID)
thread_id = _find_thread_id(client, RUN_ID)
conv = fetch_conversation(thread_id) if thread_id else []
print(f"thread_id={thread_id}  conversation turns={len(conv)}")
print("=" * 100)

# 打印每个 llm 调用及它关联的 tool 调用（含完整 args 摘要与结果首 300 字）
for llm in trace.llm_calls:
    lat = f"{llm.latency_ms/1000:.1f}s"
    print(f"\n[推理 #{llm.sequence}  {lat}] 思考摘要: {(llm.reasoning or '')[:600]}")
    for tc in llm.tool_calls:
        args = str(tc.args)[:250]
        result = (tc.result or "")[:350].replace("\n", " ")
        print(f"   → #{tc.sequence} {tc.name}({args})")
        if result:
            print(f"       结果: {result}")
    if not llm.tool_calls:
        print("   （无工具调用）")
