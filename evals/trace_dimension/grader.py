"""维度三判定器：硬门禁代码判 + 软 rubric 纯 LLM grader（DeepSeek v4 pro）。

分工（据真实召回率讨论收敛）：
- 硬门禁（5 条）：纯代码判。它们是结构性错误（编造 ID、被拦写入、读 A 写 B、改后不取证），
  代码能 100% 判准，precision 与 recall 都可靠，保留代码判定。
- 软 rubric（8 条）：纯 LLM grader。反模式是开放集合，代码提取的召回率不可达 100%，
  因此把完整 trace（工具调用 + 每步思考摘要 + 耗时 + token）整体喂给 DeepSeek v4 pro，
  由 LLM 逐条判 PASS/WARN/FAIL。百万上下文窗口足以容纳完整轨迹。

pass 规则：5 条硬门禁全 PASS 且 8 条软 rubric 无 FAIL。
"""

from __future__ import annotations

import json
import os
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

PROJECT_ROOT = Path(__file__).resolve().parents[2]
RUBRIC_PATH = Path(__file__).resolve().parent / "rubric_v1.json"

DEEPSEEK_BASE_URL = "https://api.deepseek.com"
DEFAULT_GRADER_MODEL = "deepseek-v4-pro"
GRADER_MAX_TOKENS = 8000


# ---------------------------------------------------------------------------
# 业务语义文档：喂给 grader，让它理解「任务在干什么、工具怎么用、反模式为什么错」
# ---------------------------------------------------------------------------

BUSINESS_SEMANTICS = """# 业务语义（评审前必须理解）

## 项目边界
本项目只设计 5 类硬装表面：墙漆、墙纸、地板、瓷砖、吊顶。家具只是中性参照，不是设计对象。Agent 只能通过 update_scheme 修改这些表面（改 target 的 asset + 参数），不能改 3D 网格，不能编造资产 ID。当前固定住宅有 11 个可设计空间（横厅客厅、餐厅、厨房、主卧、次卧×2、公卫、主卫、玄关、衣帽间、阳台）。

## 核心概念
- target：一个可设计表面。墙面 target_id 形如 wall_face_real4_XXX；地面/顶面形如 surface_real4_floor_XXX / surface_real4_ceiling_XXX。
- asset：可选材质/预设，asset_id 形如 floor_xxx / paint_xxx / wallpaper_xxx / tile_xxx / ceiling_xxx。
- Scheme：当前设计方案，记录每个 target 分配了什么 asset + 参数（如墙漆的 lightness/saturation/finish）。
- 角色：anchor=视觉主角（通常是地板），support=陪衬（墙漆/墙纸），quiet=安静背景（吊顶）。
- 「anchor 已落地」的精确定义：该 asset 已经被 update_scheme 成功写入某个 target（返回「修改scheme成功」）。只有已落地的 asset 才能作为后续 support/quiet 筛选时的 anchor_asset_id 参数。若 filter_assets 的 role=support/quiet 却传了一个「尚未落地」的 anchor_asset_id，等于拿一个还没选定的东西当参照，筛选结果不可信——这是错误。

## 工具语义与成本
1. get_room_by_id(room_id)：查房间信息（面积、墙地顶 target 列表）。只读，便宜。
2. load_scheme()：读当前完整 Scheme。只读，便宜。
3. filter_assets(target_id, category, role, anchor_asset_id, color_intent)：按目标+类别+角色过滤候选资产，至少缩减 70%。role∈{anchor,support,quiet}；color_intent∈{open,harmonious,contrasting}。anchor_asset_id 是「当前组合的视觉锚点」，support/quiet 的过滤用它检查关系冲突。便宜。
4. get_asset_card_by_id(asset_id)：读资产卡 + 权威预览图。注意：预览图只是资产目录缩略图，不是房间实景，不能当成交付验证证据。便宜（几百 token）。
5. set_design_work_type(work_type, reason)：声明工作类型。LIGHT=单房间最多 2 个 target 的轻改；HEAVY=完整设计。必须先声明才能 update_scheme。便宜。
6. update_scheme(target_id, asset_id, parameters)：把一个 target 改成指定 asset。返回「修改scheme成功」表示写入成功。便宜（毫秒）。
7. observe_room(room_id, focus_target_ids)：渲染单房间多视角真实图 + 像素验证。贵（一次约 3 万 token + 几十秒）。用于验证单房间，可 focus 指定 target。
8. observe_home_harmony()：渲染全屋代表图 + 12 个门洞过渡（共 13 张图）。最贵之一。用于验证跨房间连续性；单点改动不该用这个。
9. ask_design_critic(review_request)：调独立 Critic 审查，返回 PASS/REVISE/UNABLE_TO_JUDGE。最贵（嵌套独立 Agent 循环，一次约 40-65 秒）。HEAVY 交付前必须调用一次并取得 PASS；LIGHT 不调用。

## 合理流程参照
- 完整设计（HEAVY）：澄清需求 → 交付实施前规划 → 用户批准 → set_design_work_type(HEAVY) → filter_assets（先定 anchor 再筛 support/quiet）→ get_asset_card_by_id 读候选卡 → update_scheme → observe_room → ask_design_critic → PASS → 交付。
- 轻改（LIGHT）：set_design_work_type(LIGHT) → update_scheme（1-2 个 target）→ observe_room → 交付，不调 Critic。

## 关键区分（判 evidence 类指标必须用）
- 「资产卡预览图」≠「房间实景渲染」。前者来自 get_asset_card_by_id，后者来自 observe_room/observe_home_harmony 返回的像素验证图（status=ready）。只有后者能作为「已视觉验证」的证据。若 Agent 只读了资产卡、没调 observe，却宣称「已看效果/已验证」，就是拿预览冒充实景——这是错误。
- 「改完不取证」也是错误：最后一次成功 update_scheme 之后没有 observe 就宣称完成。"""


# ---------------------------------------------------------------------------
# 输入数据结构
# ---------------------------------------------------------------------------

@dataclass
class ToolCall:
    sequence: int
    name: str
    args: dict[str, Any]
    result: str


@dataclass
class LlmCall:
    sequence: int
    latency_ms: float
    reasoning: str
    tool_calls: list[ToolCall] = field(default_factory=list)
    usage: dict[str, Any] | None = None


@dataclass
class Trace:
    design_run_id: str
    tool_calls: list[ToolCall]
    llm_calls: list[LlmCall]


@dataclass
class GateResult:
    gate_id: str
    passed: bool
    detail: str


# ---------------------------------------------------------------------------
# 工具分类辅助
# ---------------------------------------------------------------------------

ID_PARAM_TO_MANIFEST = {
    "room_id": "rooms",
    "target_id": "design_targets",
    "asset_id": "assets",
}

OBSERVE_TOOLS = {"observe_room", "observe_home_harmony"}


def load_manifest(kind: str) -> dict[str, Any]:
    if kind == "scene":
        return json.loads((PROJECT_ROOT / "scene_manifest.json").read_text(encoding="utf-8"))
    if kind == "asset":
        return json.loads((PROJECT_ROOT / "asset_manifest.json").read_text(encoding="utf-8"))
    raise ValueError(f"unknown manifest kind: {kind}")


def load_rubric() -> dict[str, Any]:
    return json.loads(RUBRIC_PATH.read_text(encoding="utf-8"))


def _valid_ids(scene: dict, assets: dict) -> tuple[set[str], set[str], set[str]]:
    room_ids = {r.get("id") for r in scene.get("rooms", []) if r.get("id")}
    room_ids |= {b.get("id") for b in scene.get("balconies", []) if b.get("id")}
    target_ids = {t.get("id") for t in scene.get("design_targets", []) if t.get("id")}
    asset_ids = {a.get("id") for a in assets.get("assets", []) if a.get("id")}
    return room_ids, target_ids, asset_ids


# ---------------------------------------------------------------------------
# 1. 硬门禁（纯代码，precision/recall 都可靠）
# ---------------------------------------------------------------------------

def check_hard_gates(trace: Trace, scene: dict, assets: dict) -> list[GateResult]:
    room_ids, target_ids, asset_ids = _valid_ids(scene, assets)
    gates: list[GateResult] = []

    fabricated: list[str] = []
    for call in trace.tool_calls:
        for param, manifest_key in ID_PARAM_TO_MANIFEST.items():
            if param in call.args:
                value = call.args[param]
                valid_set = {
                    "rooms": room_ids, "design_targets": target_ids, "assets": asset_ids,
                }[manifest_key]
                if isinstance(value, str) and value and value not in valid_set:
                    fabricated.append(f"{call.name}.{param}={value}")
                elif isinstance(value, list):
                    for item in value:
                        if item not in valid_set:
                            fabricated.append(f"{call.name}.{param}[]={item}")
    gates.append(GateResult("no_fabricated_ids", not fabricated, "; ".join(fabricated) or "无编造 ID"))

    blocked = [
        call.sequence for call in trace.tool_calls
        if call.name == "update_scheme" and "SCHEME_WRITE_BLOCKED" in call.result
    ]
    gates.append(GateResult("no_blocked_write_attempts", not blocked, f"被拦写入序号={blocked}" if blocked else "无"))

    last_write = -1
    last_observe = -1
    for call in trace.tool_calls:
        if call.name == "update_scheme" and call.result.startswith("修改scheme成功"):
            last_write = call.sequence
        if call.name in OBSERVE_TOOLS:
            last_observe = call.sequence
    passed = last_write == -1 or last_observe > last_write
    gates.append(GateResult("evidence_after_final_write", passed, "改后有取证" if passed else f"最后写入={last_write}, 最后取证={last_observe}"))

    read_cards: set[str] = set()
    mismatches: list[str] = []
    for call in trace.tool_calls:
        if call.name == "get_asset_card_by_id":
            read_cards.add(call.args.get("asset_id", ""))
        elif call.name == "update_scheme" and call.result.startswith("修改scheme成功"):
            asset_id = call.args.get("asset_id", "")
            if asset_id and asset_id not in read_cards:
                mismatches.append(f"写 {asset_id} 前未读其卡")
    gates.append(GateResult("card_read_before_write", not mismatches, "; ".join(mismatches) or "读 A 写 A"))

    irrelevant = [call.name for call in trace.tool_calls if call.name == "get_today_whether"]
    gates.append(GateResult("no_irrelevant_tool_calls", not irrelevant, "无" if not irrelevant else f"无关工具={irrelevant}"))

    return gates


# ---------------------------------------------------------------------------
# 2. 完整 trace -> 文本（喂给 LLM grader）
# ---------------------------------------------------------------------------

def _truncate(text: str, limit: int = 600) -> str:
    text = text or ""
    return text if len(text) <= limit else text[:limit] + "…(截断)"


def _usage_brief(usage: dict[str, Any] | None) -> str:
    if not isinstance(usage, dict):
        return ""
    cached = usage.get("input_tokens_details", {}).get("cached_tokens", 0)
    return f"input={usage.get('input_tokens')} cached={cached} output={usage.get('output_tokens')}"


def build_trace_text(
    trace: Trace,
    scenario: dict | None = None,
    conversation: list[tuple[str, str]] | None = None,
) -> str:
    """把完整轨迹转成 LLM 可读文本：任务场景 + 完整对话 + 按时间序的「推理→工具调用→结果」。"""
    lines: list[str] = []
    if scenario:
        lines.append(f"【任务场景】{scenario.get('title', '')}")
        lines.append(f"用户需求：{scenario.get('initial_message', '')}")
        lines.append("")

    if conversation:
        lines.append("【完整对话（用户与 Agent 的全部轮次）】")
        for role, content in conversation:
            lines.append(f"{role}：{_truncate(content, 800)}")
        lines.append("")

    lines.append("【工具调用轨迹（按时间序，含每步模型思考摘要 / 耗时 / token）】")
    tool_by_seq = {c.sequence: c for c in trace.tool_calls}

    # 关联：每个 llm 调用，其后紧跟的 tool 调用（用 tool_calls 字段已关联）
    for llm in trace.llm_calls:
        usage = _usage_brief(llm.usage)
        lat = f"{llm.latency_ms / 1000:.1f}s"
        reasoning = _truncate(llm.reasoning, 1200)
        lines.append(f"\n[模型推理 #{llm.sequence}，耗时 {lat}，{usage}]")
        if reasoning:
            lines.append(f"  思考摘要：{reasoning}")
        for tc in llm.tool_calls:
            args_brief = _truncate(json.dumps(tc.args, ensure_ascii=False), 300)
            result_brief = _truncate(tc.result, 400)
            lines.append(f"  → {tc.name}({args_brief})")
            if result_brief:
                lines.append(f"      结果：{result_brief}")
        if not llm.tool_calls:
            lines.append("  （本轮未调用工具，直接回复）")

    # 兜底：tool_calls 里未被任何 llm 关联的（时间戳关联失败的）
    associated = {id(tc) for llm in trace.llm_calls for tc in llm.tool_calls}
    orphans = [tc for tc in trace.tool_calls if id(tc) not in associated]
    if orphans:
        lines.append("\n[未关联到推理轮次的工具调用]")
        for tc in orphans:
            lines.append(f"  → {tc.name}({_truncate(json.dumps(tc.args, ensure_ascii=False), 300)})")
            lines.append(f"      结果：{_truncate(tc.result, 400)}")

    return "\n".join(lines)


# ---------------------------------------------------------------------------
# 3. 纯 LLM grader（DeepSeek v4 pro，完整 trace 一次喂入）
# ---------------------------------------------------------------------------

def _build_grader_system_prompt(rubric: dict) -> str:
    rubrics_lines = []
    for domain in rubric["soft_domains"]:
        rubrics_lines.append(f"\n【{domain['title']}】")
        for item in domain["rubrics"]:
            rubrics_lines.append(f"- {item['rubric_id']}：{item['text']}")
    criteria = "\n".join(rubrics_lines)
    ids = [item["rubric_id"] for d in rubric["soft_domains"] for item in d["rubrics"]]
    ids_json = ", ".join(f'"{i}": {{"verdict": "PASS|WARN|FAIL", "reason": "一句话理由"}}' for i in ids)
    return (
        "你是住宅硬装设计 Agent 的工具调用轨迹评审员。你会看到一次完整设计任务的全过程："
        "完整对话（用户需求与澄清）、工具调用轨迹（含每一步模型的思考摘要、耗时、token 用量）。\n\n"
        f"{BUSINESS_SEMANTICS}\n\n"
        "你的任务是逐条评估下面这些软性指标，判断 Agent 的工具调用轨迹是否合理。"
        "判定必须引用轨迹中的具体证据（工具名、target_id、asset_id、思考摘要原文），不得空泛。\n\n"
        "判定口径：\n"
        "- PASS：这一步做对了，没有踩反模式。\n"
        "- WARN：有风险或小瑕疵，但未造成实质错误。\n"
        "- FAIL：明确踩了指标里描述的反模式。\n\n"
        "输出纪律：简短思考，直接给结论，不要把整段推理过程写全；理由一句话即可，不要长篇大论。\n\n"
        "评估标准：\n"
        f"{criteria}\n\n"
        "只输出一个 JSON 对象，不要任何 JSON 之外的文字，格式如下：\n"
        f'{{"soft_rubrics": {{{ids_json}}}}}'
    )


def llm_grade_soft_rubrics(
    trace_text: str,
    rubric: dict,
    *,
    model: str | None = None,
) -> tuple[dict[str, Any], dict[str, Any]]:
    """调 DeepSeek v4 pro 判 8 条软 rubric。

    返回 (soft_verdicts, usage_summary)。usage_summary 汇总本次判定（含重试）的 token 账单，
    供计费探针打印。
    """
    try:
        from openai import OpenAI
    except ImportError:
        raise RuntimeError("openai SDK 未安装")

    api_key = os.getenv("EVAL_DEEPSEEK_API_KEY") or os.getenv("DEEPSEEK_API_KEY", "")
    if not api_key:
        raise RuntimeError("EVAL_DEEPSEEK_API_KEY or DEEPSEEK_API_KEY is required")
    base_url = os.getenv("EVAL_DEEPSEEK_BASE_URL", DEEPSEEK_BASE_URL).rstrip("/")
    if base_url not in {DEEPSEEK_BASE_URL, f"{DEEPSEEK_BASE_URL}/v1"}:
        raise RuntimeError("EVAL_DEEPSEEK_BASE_URL must use the official https://api.deepseek.com endpoint")

    import httpx
    proxy = os.getenv("EVAL_DEEPSEEK_PROXY") or None
    client = OpenAI(
        api_key=api_key,
        base_url=base_url,
        http_client=httpx.Client(proxy=proxy, trust_env=False, timeout=600.0),
        timeout=600.0,
    )

    system_prompt = _build_grader_system_prompt(rubric)
    model = model or DEFAULT_GRADER_MODEL

    usage_summary: dict[str, Any] = {"attempts": 0, "prompt_tokens": 0, "completion_tokens": 0,
                                     "reasoning_tokens": 0, "total_tokens": 0}
    last_error: Exception | None = None
    for attempt in range(2):
        retry_note = "\n上次输出无法解析，请只输出完整 JSON。" if attempt else ""
        try:
            response = client.chat.completions.create(
                model=model,
                messages=[
                    {"role": "system", "content": system_prompt + retry_note},
                    {"role": "user", "content": trace_text},
                ],
                max_tokens=GRADER_MAX_TOKENS,
                response_format={"type": "json_object"},
                extra_body={"thinking": {"type": "enabled"}},
            )
        except Exception as error:  # noqa: BLE001
            last_error = error
            continue

        usage = getattr(response, "usage", None)
        if usage is not None:
            usage_summary["attempts"] += 1
            usage_summary["prompt_tokens"] += int(getattr(usage, "prompt_tokens", 0) or 0)
            usage_summary["completion_tokens"] += int(getattr(usage, "completion_tokens", 0) or 0)
            usage_summary["total_tokens"] += int(getattr(usage, "total_tokens", 0) or 0)
            details = getattr(usage, "completion_tokens_details", None)
            reasoning = getattr(details, "reasoning_tokens", None) if details else None
            if reasoning is not None:
                usage_summary["reasoning_tokens"] += int(reasoning or 0)

        content = response.choices[0].message.content
        if not content:
            last_error = RuntimeError("DeepSeek grader returned no content")
            continue
        try:
            data = json.loads(content)
            soft = data.get("soft_rubrics", data)
            if isinstance(soft, dict) and soft:
                return soft, usage_summary
        except json.JSONDecodeError as error:
            last_error = error
            continue
    raise RuntimeError(f"DeepSeek grader failed: {last_error}")


# ---------------------------------------------------------------------------
# 4. 合并规则
# ---------------------------------------------------------------------------

def finalize(gates: list[GateResult], soft_verdicts: dict[str, Any]) -> dict[str, Any]:
    hard_pass = all(g.passed for g in gates)

    normalized: dict[str, str] = {}
    for rubric_id, item in soft_verdicts.items():
        if isinstance(item, str):
            normalized[rubric_id] = item
        elif isinstance(item, dict):
            normalized[rubric_id] = item.get("verdict", "FAIL")

    any_fail = any(v == "FAIL" for v in normalized.values())
    overall = "PASS" if (hard_pass and not any_fail) else "FAIL"

    return {
        "hard_gates": [{"gate_id": g.gate_id, "passed": g.passed, "detail": g.detail} for g in gates],
        "hard_pass": hard_pass,
        "soft_rubrics": soft_verdicts,
        "any_soft_fail": any_fail,
        "overall_pass": overall,
    }
