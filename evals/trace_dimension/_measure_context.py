"""临时脚本：测量喂给 grader 的上下文规模（字符数 + 估算 token）。"""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from evals.trace_dimension.grader import (
    BUSINESS_SEMANTICS,
    _build_grader_system_prompt,
    build_trace_text,
    load_rubric,
)
from evals.trace_dimension.runner import (
    _find_thread_id,
    _load_langsmith_env,
    extract_trace,
    fetch_conversation,
)

RUNS = {
    "trap_skip_filter_01": "run_20260815T015633326547_6a00d5a1",
    "trap_anchor_order_02": "run_20260815T020037333982_e6d86b86",
    "trap_preview_evidence_03": "run_20260815T020747391652_8066caf5",
    "trap_harmony_single_04": "run_20260815T021108977980_336168b0",
}


def est_tokens(text: str) -> int:
    # 中文约 1 字 ≈ 1 token 偏保守，英文/符号按 4 字符 1 token
    return max(1, len(text) // 2)  # 保守下界：2 字符 1 token


def chars_to_tokens(n_chars: int) -> int:
    return max(1, n_chars // 2)


def main() -> int:
    from langsmith import Client
    api_key, endpoint = _load_langsmith_env()
    client = Client(api_key=api_key, api_url=endpoint)

    rubric = load_rubric()
    system_prompt = _build_grader_system_prompt(rubric)
    print(f"system_prompt: {len(system_prompt)} chars, ~{est_tokens(system_prompt)} tok")
    print(f"  (其中 BUSINESS_SEMANTICS: {len(BUSINESS_SEMANTICS)} chars, ~{est_tokens(BUSINESS_SEMANTICS)} tok)")
    print()

    for name, rid in RUNS.items():
        trace = extract_trace(client, rid)
        thread_id = _find_thread_id(client, rid)
        conv = fetch_conversation(thread_id) if thread_id else []
        conv_chars = sum(len(c) for _, c in conv)
        trace_text = build_trace_text(trace, None, conv)
        total = len(system_prompt) + len(trace_text)
        print(f"[{name}] {rid}")
        print(f"  thread_id: {thread_id}")
        print(f"  conversation: {len(conv)} turns, {conv_chars} chars")
        print(f"  trace_text: {len(trace_text)} chars, ~{est_tokens(trace_text)} tok")
        print(f"  llm_calls={len(trace.llm_calls)} tool_calls={len(trace.tool_calls)}")
        print(f"  TOTAL(含system): {total} chars, ~{chars_to_tokens(total)} tok")
        print()

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
