"""Dimension-two multimodal grader backed by Doubao Seed 2.1 Turbo (Volcengine Ark).

Replaces the Codex-subagent grading step. For each case directory the runner
produced, this script reads ``evidence_packet.json`` plus the saved visual
evidence images, sends them to a multimodal model, and writes
``grader_judgment.json``. The existing ``run_eval.py --finalize-run`` then
finalizes deterministically exactly as before — the deterministic ``code``
gates (scheme_render_version_alignment / scope_integrity /
visual_claim_has_evidence) are overwritten there, so this grader only needs to
produce sensible values for them.

Usage:
    E:\\python\\python.exe evals/outcome_dimension/grader.py <run_dir> [--scenario id] [--model ...]

Credentials (in priority order):
    --api-key  >  EVAL_DOUBAO_API_KEY  >  ARK_API_KEY
"""

from __future__ import annotations

import argparse
import base64
import json
import mimetypes
import os
import sys
import time
import urllib.error
import urllib.request
from pathlib import Path
from typing import Any

HERE = Path(__file__).resolve().parent
PROJECT_ROOT = HERE.parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

RUBRIC_PATH = HERE / "rubric_v1.json"

DEFAULT_BASE_URL = "https://ark.cn-beijing.volces.com/api/v3"
DEFAULT_MODEL = "doubao-seed-2-1-turbo-260628"
MAX_TOOL_RESULT_CHARS = 400
MAX_RETRIES = 3
RETRY_BASE_DELAY = 5.0
# Doubao Seed 2.1 is a slow reasoning model (a text-only full grading reply took
# ~97s). Keep evidence images readable but small so one image-grounded reply
# finishes inside the per-attempt timeout.
EVIDENCE_IMAGE_MAX_WIDTH = 768
EVIDENCE_IMAGE_QUALITY = 82


def load_rubric() -> dict[str, Any]:
    return json.loads(RUBRIC_PATH.read_text(encoding="utf-8"))


def image_data_url(path: str) -> str:
    media_type = mimetypes.guess_type(path)[0] or "image/jpeg"
    if media_type not in {"image/jpeg", "image/png", "image/webp"}:
        media_type = "image/jpeg"
    image_bytes = _read_image_for_evidence(path)
    encoded = base64.b64encode(image_bytes).decode("ascii")
    return f"data:{media_type};base64,{encoded}"


def _read_image_for_evidence(path: str) -> bytes:
    """Read an evidence image, downscaling with PIL when too wide."""
    raw = Path(path).read_bytes()
    try:
        from PIL import Image
        import io

        image = Image.open(path)
        if image.width <= EVIDENCE_IMAGE_MAX_WIDTH:
            return raw
        image = image.convert("RGB")
        height = max(1, round(image.height * EVIDENCE_IMAGE_MAX_WIDTH / image.width))
        image = image.resize((EVIDENCE_IMAGE_MAX_WIDTH, height), Image.LANCZOS)
        buffer = io.BytesIO()
        image.save(buffer, "JPEG", quality=EVIDENCE_IMAGE_QUALITY)
        return buffer.getvalue()
    except Exception:
        return raw


def _compact_scheme(scheme: dict[str, Any]) -> list[str]:
    lines: list[str] = []
    for assignment in scheme.get("assignments", []):
        target = assignment.get("target") or {}
        target_id = target.get("id", "?") if isinstance(target, dict) else "?"
        asset_id = assignment.get("asset_id", "?")
        parameters = assignment.get("parameters")
        suffix = f" parameters={parameters}" if parameters else ""
        lines.append(f"{target_id} -> {asset_id}{suffix}")
    return lines


def _compact_tool_calls(tool_calls: list[dict[str, Any]]) -> list[str]:
    lines: list[str] = []
    for call in tool_calls:
        name = call.get("name", "?")
        sequence = call.get("sequence", "?")
        args = call.get("args") or {}
        if isinstance(args, dict):
            args_brief = ", ".join(
                f"{key}={value}" for key, value in args.items()
                if key in {"target_id", "asset_id", "room_id", "category", "role"}
            )
        else:
            args_brief = str(args)
        result = call.get("result")
        if isinstance(result, str):
            result = result if len(result) <= MAX_TOOL_RESULT_CHARS else result[:MAX_TOOL_RESULT_CHARS] + "…"
        elif result is not None:
            result = json.dumps(result, ensure_ascii=False)
            if len(result) > MAX_TOOL_RESULT_CHARS:
                result = result[:MAX_TOOL_RESULT_CHARS] + "…"
        lines.append(f"sequence_{sequence}: {name}({args_brief})")
        if result:
            lines.append(f"  result: {result}")
    return lines


def _compact_diff(scheme_diff: list[dict[str, Any]]) -> list[str]:
    lines: list[str] = []
    for change in scheme_diff:
        target_id = change.get("target_id", "?")
        before = change.get("before") or {}
        after = change.get("after") or {}
        before_asset = before.get("asset_id", "—") if isinstance(before, dict) else "—"
        after_asset = after.get("asset_id", "—") if isinstance(after, dict) else "—"
        lines.append(f"{target_id}: {before_asset} -> {after_asset}")
    return lines


def _numbered_dialogue_lines(conversation: list[dict[str, Any]]) -> list[str]:
    lines: list[str] = []
    for turn in conversation:
        turn_id = turn.get("turn_id", "?")
        role = turn.get("role", "?")
        content = turn.get("content", "")
        if not isinstance(content, str):
            content = json.dumps(content, ensure_ascii=False)
        if len(content) > 2_000:
            content = content[:2_000] + "…"
        lines.append(f"[turn_{turn_id}] {role}: {content}")
    return lines


def build_text_context(packet: dict[str, Any], rubric: dict[str, Any]) -> str:
    visual_criteria = rubric["visual_criteria"]
    gates = rubric["consistency_gates"]

    criteria_text = "\n".join(
        f"- {item['criterion_id']}: {item['text']}" for item in visual_criteria
    )
    gates_text = "\n".join(
        f"- {item['gate_id']} [owner={item['owner']}]: {item['text']}" for item in gates
    )

    final_state = packet["final_state"]
    final_scheme_lines = _compact_scheme(final_state["scheme"])
    tool_lines = _compact_tool_calls(packet.get("tool_calls", []))
    diff_lines = _compact_diff(packet.get("scheme_diff", []))
    critic = packet.get("critic_review") or "（本场景未调用 Critic）"
    dialogue_lines = _numbered_dialogue_lines(packet.get("conversation", []))

    required = ", ".join(packet["required_visual_criteria"])

    return f"""[评估标准 · 视觉质量 Rubric]
{criteria_text}

[评估标准 · 言行一致性门禁]
{gates_text}

[本场景信息]
scenario_id: {packet['scenario_id']}
允许修改的目标(allowed_target_ids): {', '.join(packet['allowed_target_ids'])}
本场景必须判断的视觉标准(required_visual_criteria): {required}

[完整编号对话(用户需求、审批、替代与实施前规划的唯一语义依据,没有独立 approved_plan 摘要)]
{chr(10).join(dialogue_lines) if dialogue_lines else '（无对话记录）'}

[最终 Scheme 分配]
{chr(10).join(final_scheme_lines) if final_scheme_lines else '（无）'}

[Scheme 差异(相对初始方案)]
{chr(10).join(diff_lines) if diff_lines else '（无变化）'}

[工具轨迹]
{chr(10).join(tool_lines) if tool_lines else '（无）'}

[Critic 审查]
{critic}

[最终汇报(final_report)]
{packet['final_report']}
"""


SYSTEM_PROMPT = """你是住宅硬装设计最终成果的验收评审员(Grader)。你的任务是把渲染图片证据与设计过程数据放在一起,对场景做视觉质量与言行一致性验收。

你必须严格输出一个 JSON 对象——不要用 markdown 代码块包裹,不要输出任何 JSON 之外的文字。JSON 结构如下:
{
  "visual_results": [
    {"criterion_id": "<标准ID>", "verdict": "PASS|FAIL|UNABLE_TO_JUDGE", "reason": "<一句话中文理由>", "evidence_ids": ["<引用的证据图片ID,形如 capture_id:view_id>"]}
  ],
  "consistency_gates": {
    "<gate_id>": {"verdict": "PASS|FAIL", "reason": "<一句话中文理由>", "evidence_refs": ["<引用的证据,形如 conversation.turn_N / tool_calls.sequence_N / final_state.scheme.assignments.XXX / render_evidence / final_report>"]}
  },
  "prioritized_findings": ["<按优先级排列的发现,最重要在前>"],
  "unverified_items": ["<现有证据无法确认的事项>"],
  "summary": "<一段中文总结,说明是否通过及核心原因>"
}

判分规则:
- 视觉标准:只对 required_visual_criteria 里列出的标准输出 visual_results 条目。每项必须为 PASS 才算该场景视觉通过;UNABLE_TO_JUDGE 表示缺少必需视觉证据,同样视为不通过。
- 一致性门禁:7 项门禁必须全部输出且全部 PASS 才算通过。其中 scheme_render_version_alignment 由代码确定性判定,你只需给 PASS 与理由"由代码判定",它会被覆盖。
- 需求、审批、替代与实施前规划一律以[完整编号对话]为准(没有独立 approved_plan 摘要);plan_scheme_alignment、scope_integrity、deviation_disclosed 都要对照对话中的实施前规划与最终 Scheme/汇报判断。
- evidence_ids 必须引用实际提供的证据图片 ID;evidence_refs 必须引用实际提供的文本证据。不要编造不存在的引用。
- 判断视觉标准时,只依据实际提供的渲染图片,不要假设未显示的墙面/地面/顶面。

单侧采光容错(重要):
- 同一房间内,朝向窗的墙面通常更亮、背光墙面更暗,这是真实光照下的正常物理现象,不是墙面颜色或材质差异。
- 判断 same_room_wall_family、single_wall_temperature_consistency、wall_floor_color_relation、small_room_complexity 等墙面/颜色标准时,应看墙面本身的色相与色温是否属于同一套搭配,而不是比较明度高低。
- 只要可见墙面在色相与色温上同属一套(例如都是暖白/Greige),即使明度因采光明显不同,也应判 PASS,并可在 reason 里说明"明度差异源于单侧采光光照,非色差"。
- 不要因为"某个视角画面整体较暗/背光"就把同色墙判成颜色不统一;也不要因为在某个视角看不到某一面墙就把整项判为 UNABLE_TO_JUDGE——只要证据中至少有足够墙面能判断色相同族,即可给出判断。"""


def build_user_content(text_context: str, packet: dict[str, Any]) -> list[dict[str, Any]]:
    content: list[dict[str, Any]] = [{"type": "text", "text": text_context}]
    evidence = [
        item for item in packet.get("render_evidence", [])
        if item.get("evidence_valid", False)
    ]
    if not evidence:
        content.append(
            {
                "type": "text",
                "text": "\n[渲染证据图片]\n本场景没有任何渲染证据图片。所有需要视觉判断的标准都应判为 UNABLE_TO_JUDGE。",
            }
        )
        return content
    content.append(
        {
            "type": "text",
            "text": "\n[渲染证据图片]\n以下是最终版本的渲染证据图片。每张图片后面紧跟一行标注其 evidence_id、房间与视角。请据此判断视觉标准。",
        }
    )
    for item in evidence:
        path = item.get("image_path")
        if not path or not Path(path).is_file():
            continue
        content.append(
            {
                "type": "image_url",
                "image_url": {"url": image_data_url(path)},
            }
        )
        content.append(
            {
                "type": "text",
                "text": (
                    f"evidence_id: {item.get('evidence_id')} | "
                    f"room: {item.get('room_id')} | label: {item.get('view_label')} | "
                    f"quality: {item.get('quality')} | target_visibility: {item.get('target_visibility')} | "
                    f"mask_quality: {item.get('mask_quality')}"
                ),
            }
        )
    return content


def _post_json(url: str, payload: dict[str, Any], api_key: str, timeout: float) -> dict[str, Any]:
    body = json.dumps(payload, ensure_ascii=False).encode("utf-8")
    request = urllib.request.Request(
        url,
        data=body,
        headers={
            "Authorization": f"Bearer {api_key}",
            "Content-Type": "application/json",
        },
        method="POST",
    )
    # Never route Doubao (a mainland-China service) through the machine's
    # global 7892 proxy, which is configured for DeepSeek/OpenAI and would
    # intermittently drop the connection. Build a proxy-less opener to go
    # direct, matching how the backend calls its own model endpoints.
    opener = urllib.request.build_opener(urllib.request.ProxyHandler({}))
    try:
        with opener.open(request, timeout=timeout) as response:
            raw = response.read().decode("utf-8")
            return json.loads(raw) if raw else {}
    except urllib.error.HTTPError as error:
        detail = error.read().decode("utf-8", errors="replace")
        raise RuntimeError(f"Ark returned {error.code}: {detail}") from error
    except urllib.error.URLError as error:
        raise RuntimeError(f"Ark unreachable: {error}") from error
    except OSError as error:
        # http.client.RemoteDisconnected and friends are OSError, not URLError.
        raise RuntimeError(f"Ark connection error: {error}") from error


def call_ark(messages: list[dict[str, Any]], api_key: str, model: str, base_url: str) -> str:
    url = f"{base_url.rstrip('/')}/chat/completions"
    # Doubao Seed 2.1 is a reasoning model: it drops the connection when given
    # `temperature` or `response_format`, so keep the payload minimal and parse
    # the JSON reply ourselves via extract_json().
    payload = {
        "model": model,
        "messages": messages,
        "max_tokens": 8192,
    }
    last_error: Exception | None = None
    for attempt in range(1, MAX_RETRIES + 1):
        try:
            response = _post_json(url, payload, api_key, timeout=600)
            choice = (response.get("choices") or [{}])[0]
            message = choice.get("message") or {}
            content = message.get("content")
            if isinstance(content, str) and content.strip():
                return content
            raise RuntimeError(f"empty content in response: {str(response)[:200]}")
        except RuntimeError as error:
            last_error = error
            if attempt == MAX_RETRIES:
                break
            # Exponential backoff + jitter: Ark intermittently drops the
            # connection on large multimodal requests, so spread retries wide.
            delay = RETRY_BASE_DELAY * (2 ** (attempt - 1))
            time.sleep(delay)
    raise RuntimeError(f"Ark call failed after {MAX_RETRIES} attempts: {last_error}")


def extract_json(content: str) -> dict[str, Any]:
    """Robustly pull the first JSON object out of a model reply."""
    content = content.strip()
    try:
        return json.loads(content)
    except json.JSONDecodeError:
        pass
    # Strip a markdown code fence if present.
    fence = re_json_fence(content)
    if fence is not None:
        try:
            return json.loads(fence)
        except json.JSONDecodeError:
            pass
    # Fall back to first balanced { ... } span.
    start = content.find("{")
    if start == -1:
        raise ValueError("no JSON object found in model reply")
    depth = 0
    for index in range(start, len(content)):
        char = content[index]
        if char == "{":
            depth += 1
        elif char == "}":
            depth -= 1
            if depth == 0:
                return json.loads(content[start : index + 1])
    raise ValueError("unbalanced JSON in model reply")


def re_json_fence(content: str) -> str | None:
    import re

    match = re.search(r"```(?:json)?\s*(\{.*\})\s*```", content, flags=re.DOTALL)
    return match.group(1) if match else None


def grade_case(
    case_dir: Path,
    api_key: str,
    model: str,
    base_url: str,
    rubric: dict[str, Any],
) -> dict[str, Any]:
    packet = json.loads((case_dir / "evidence_packet.json").read_text(encoding="utf-8"))
    text_context = build_text_context(packet, rubric)
    content = build_user_content(text_context, packet)
    messages = [
        {"role": "system", "content": SYSTEM_PROMPT},
        {"role": "user", "content": content},
    ]
    reply = call_ark(messages, api_key, model, base_url)
    judgment = extract_json(reply)
    save_json(case_dir / "grader_judgment.json", judgment)
    return judgment


def save_json(path: Path, payload: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    os.replace(temporary, path)


def iter_cases(run_dir: Path, requested: list[str]) -> list[Path]:
    case_dirs: list[Path] = []
    for case_dir in sorted(run_dir.iterdir()):
        if not case_dir.is_dir():
            continue
        if not (case_dir / "evidence_packet.json").exists():
            continue
        if requested and case_dir.name not in requested:
            continue
        case_dirs.append(case_dir)
    return case_dirs


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("run_dir", type=Path, help="run 目录(含各场景子目录)")
    parser.add_argument("--scenario", action="append", default=[], help="只评指定场景,可重复")
    parser.add_argument("--api-key", default=None, help="覆盖环境变量中的豆包 API key")
    parser.add_argument(
        "--model", default=None, help=f"默认 {DEFAULT_MODEL}"
    )
    parser.add_argument("--base-url", default=None, help=f"默认 {DEFAULT_BASE_URL}")
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    api_key = args.api_key or os.getenv("EVAL_DOUBAO_API_KEY") or os.getenv("ARK_API_KEY")
    if not api_key:
        raise SystemExit("缺少豆包 API key:请用 --api-key 或 EVAL_DOUBAO_API_KEY / ARK_API_KEY")
    model = args.model or os.getenv("EVAL_DOUBAO_MODEL") or DEFAULT_MODEL
    base_url = args.base_url or os.getenv("EVAL_DOUBAO_BASE_URL") or DEFAULT_BASE_URL

    run_dir = args.run_dir.resolve()
    case_dirs = iter_cases(run_dir, args.scenario)
    if not case_dirs:
        raise SystemExit(f"{run_dir} 下没有可评分的场景(缺少 evidence_packet.json)")

    rubric = load_rubric()
    print(f"grader: model={model} cases={len(case_dirs)}", flush=True)
    for index, case_dir in enumerate(case_dirs, start=1):
        print(f"[{index}/{len(case_dirs)}] {case_dir.name}", flush=True)
        try:
            grade_case(case_dir, api_key, model, base_url, rubric)
            print(f"  -> 已写入 {case_dir.name}/grader_judgment.json", flush=True)
        except Exception as error:  # noqa: BLE001
            print(f"  !! {case_dir.name} 评分失败: {type(error).__name__}: {error}", flush=True)
            continue
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
