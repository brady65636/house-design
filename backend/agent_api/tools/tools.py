"""共享工具层：agentloop（CLI 入口）与 agent_graph（LangGraph 编排）都从这里取工具。

依赖方向：agentloop -> agent_graph -> tools。工具定义、SYSTEM_PROMPT 和
当前 Scheme 状态只存在这里，避免第二事实源。

生产 API 通过对话上下文把工具解析到对应 Design Run 的 VersionedSchemeStore；
CLI 与旧测试仍可通过 get_scheme_store() / set_scheme_store() 使用单文件存储。
"""

import base64
import json
from dataclasses import dataclass
from pathlib import Path
from typing import Literal

import httpx
from pydantic import BaseModel, ConfigDict, Field, ValidationError

from ..config import PROJECT_ROOT, settings
from ..design_runs.runtime import (
    get_current_design_run_id,
    get_design_run_manager,
)
from ..prompt_context import build_design_context, build_skill_context, build_system_prompt
from ..prompt_context import build_house_context
from ..retrieval.asset_filter import AssetFilterError, filter_assets, load_filter_profiles
from ..scheme.schema import Scheme
from ..scheme.store import SchemeStore, read_json
from ..scheme.validator import validate_scheme
from ..telemetry import langsmith_tool_span
from .visual_evidence import compact_render_evidence


ACTIVE_SCENE_MANIFEST = read_json(settings.scene_manifest_path)
ACTIVE_ASSET_MANIFEST = read_json(settings.asset_manifest_path)
DESIGN_CONTEXT = build_design_context(settings.design_md_path)
DESIGN_SKILL_CONTEXT = build_skill_context(settings.design_skill_path)

SYSTEM_PROMPT = build_system_prompt(
    ACTIVE_SCENE_MANIFEST,
    ACTIVE_ASSET_MANIFEST,
)

_scheme_store: SchemeStore | None = None


def get_scheme_store() -> SchemeStore:
    """Resolve the current Design Run store; fall back to legacy/test storage."""
    manager = get_design_run_manager()
    run_id = get_current_design_run_id()
    if manager is not None and run_id is not None:
        return manager.get_store(run_id)
    global _scheme_store
    if _scheme_store is None:
        _scheme_store = SchemeStore(
            settings.scheme_path,
            ACTIVE_SCENE_MANIFEST,
            ACTIVE_ASSET_MANIFEST,
        )
    return _scheme_store


def set_scheme_store(store: SchemeStore | None) -> SchemeStore | None:
    """注入自定义 SchemeStore（测试用临时目录、API lifespan 注入生产实例），返回旧值。"""
    global _scheme_store
    previous = _scheme_store
    _scheme_store = store
    return previous


def load_current_scheme() -> dict:
    """启动时把当前 Scheme 读入 SchemeStore 内存（工具共享同一份状态）。"""
    return get_scheme_store().load()


class WhetherInput(BaseModel):
    year: str = Field(description="今天的年份")
    month: str = Field(description="今天的月份")
    day: str = Field(description="今天的日子")


def get_today_whether(year: str, month: str, day: str):
    return "今天的温度是30度"


class RoomInput(BaseModel):
    room_id: str = Field(description="要查询的房间id")


def get_room_by_id(room_id: str):
    scene = read_json(settings.scene_manifest_path)
    for room in scene["rooms"]:
        if room["id"] == room_id:
            return json.dumps(room, ensure_ascii=False)
    return "该房间不存在，请检查输入"


class FilterAssetsInput(BaseModel):
    model_config = ConfigDict(extra="forbid")

    target_id: str = Field(min_length=1, description="准备设计的真实 target_id")
    category: str = Field(description="候选资产类别")
    role: str = Field(description="该候选在当前组合中的关系角色：anchor、support 或 quiet")
    anchor_asset_id: str | None = Field(
        default=None,
        description="已有视觉锚点的真实 Asset ID；设计 anchor 本身时可不传",
    )
    color_intent: Literal["open", "harmonious", "contrasting"] = Field(
        default="open",
        description="候选与已有 anchor 的颜色关系：open=不限定颜色关系、harmonious=与 anchor 和谐协调、contrasting=有意形成对比。这是关系意图，不是色温（不要填 warm/cool 等色温词）。",
    )


def filter_asset_candidates(
    target_id: str,
    category: str,
    role: str,
    anchor_asset_id: str | None = None,
    color_intent: str = "open",
):
    """Filter obvious mismatches and return a diverse visual-comparison set."""

    try:
        result = filter_assets(
            scene_manifest=read_json(settings.scene_manifest_path),
            asset_manifest=read_json(settings.asset_manifest_path),
            asset_cards=read_json(settings.asset_cards_path),
            profile_data=load_filter_profiles(settings.asset_filter_profiles_path),
            target_id=target_id,
            category=category,
            role=role,
            anchor_asset_id=anchor_asset_id,
            color_intent=color_intent,
        )
    except AssetFilterError as error:
        return json.dumps({"error": "INVALID_FILTER_QUERY", "message": str(error)}, ensure_ascii=False)
    return json.dumps(result, ensure_ascii=False)


class AssetCardInput(BaseModel):
    model_config = ConfigDict(extra="forbid")

    asset_id: str = Field(min_length=1, description="要读取详细资产卡的真实资产 id")


def get_asset_card_by_id(asset_id: str):
    """Return one detailed card together with its authoritative preview image."""

    cards = read_json(settings.asset_cards_path).get("cards", {})
    card = cards.get(asset_id) if isinstance(cards, dict) else None
    if not isinstance(card, dict):
        return "该资产卡不存在，请先通过 filter_assets 查询真实 asset_id"
    preview = card.get("preview_image")
    if not isinstance(preview, dict):
        return "该资产卡缺少 preview_image，不能只把文字描述当成视觉依据"
    relative_path = preview.get("path")
    media_type = preview.get("media_type")
    if not isinstance(relative_path, str) or not isinstance(media_type, str):
        return "该资产卡的 preview_image 契约无效"
    project_root = PROJECT_ROOT.resolve()
    image_path = (project_root / relative_path).resolve()
    if not image_path.is_relative_to(project_root):
        return "资产预览路径越出项目目录，已拒绝读取"
    if media_type not in {"image/webp", "image/jpeg", "image/png"}:
        return "资产预览图片格式不受支持"
    if not image_path.is_file():
        return f"资产卡预览图不存在：{relative_path}"
    image_bytes = image_path.read_bytes()
    if len(image_bytes) > 4 * 1024 * 1024:
        return "资产卡预览图超过 4MB 上限，请先生成轻量缩略图"
    image_url = f"data:{media_type};base64,{base64.b64encode(image_bytes).decode('ascii')}"
    return VisualToolOutput(
        summary=json.dumps(card, ensure_ascii=False),
        images=[(str(preview.get("alt") or card.get("name_zh") or asset_id), image_url)],
        kind="asset_reference",
    )


class GetCurrentSchemeInput(BaseModel):
    model_config = ConfigDict(extra="forbid")


def load_scheme():
    """返回当前内存中的完整 Scheme JSON 字符串。"""
    return json.dumps(get_scheme_store().get(), ensure_ascii=False)


class ObserveRoomInput(BaseModel):
    model_config = ConfigDict(extra="forbid")

    room_id: str = Field(min_length=1, description="需要渲染观察的真实房间 ID")
    focus_target_ids: list[str] = Field(
        default_factory=list,
        max_length=8,
        description="需要重点取证的真实 target_id 列表（该房间的墙/地/顶），最多 8 个；缺省则观察整个房间",
    )


class ObserveHomeHarmonyInput(BaseModel):
    model_config = ConfigDict(extra="forbid")


@dataclass
class VisualToolOutput:
    """Tool metadata plus images which must be passed back as image inputs."""

    summary: str
    images: list[tuple[str, str]]
    kind: str = "render_observation"


def _request_render_evidence(tool: str, args: dict) -> VisualToolOutput | str:
    """Ask the backend render bridge; the Agent never calls browser JavaScript."""

    bridge_url = settings.render_bridge_url.rstrip("/")
    session_id = settings.render_session_id
    try:
        command_args = dict(args)
        design_run_id = get_current_design_run_id()
        if design_run_id:
            command_args["design_run_id"] = design_run_id
        # Whole-home capture is optimized in the viewer, but software WebGL or
        # a cold texture cache can still exceed two minutes.  Keep the bridge
        # and HTTP budgets aligned so a valid late result is not turned into a
        # spurious 504 by the caller five seconds after the bridge deadline.
        render_timeout_ms = 180_000
        response = httpx.post(
            f"{bridge_url}/v1/render-sessions/{session_id}/commands",
            json={"tool": tool, "args": command_args, "timeout_ms": render_timeout_ms},
            timeout=(render_timeout_ms / 1000) + 10,
            trust_env=False,
        )
    except httpx.HTTPError as error:
        return f"渲染会话不可达：{error}。请启动 render_bridge.py 并打开绑定该 session 的实时场景。"

    if response.status_code != 200:
        detail = response.text
        if response.status_code == 503:
            return "渲染器未在线：不能把文本当作视觉证据。请先打开实时场景并等待它注册当前 render session。"
        return f"渲染观察失败（HTTP {response.status_code}）：{detail}"

    payload = response.json().get("result", {})
    if not isinstance(payload, dict):
        return "渲染观察失败：render bridge 返回了无效结果结构。"
    summary, images = compact_render_evidence(tool, payload)
    return VisualToolOutput(
        summary=json.dumps(summary, ensure_ascii=False),
        images=images,
    )


def observe_room(room_id: str, focus_target_ids: list[str] | None = None):
    return _request_render_evidence(
        "observe_room",
        {"room_id": room_id, "focus_target_ids": focus_target_ids or []},
    )


def observe_home_harmony():
    return _request_render_evidence("observe_home_harmony", {})


class UpdateInput(BaseModel):
    target_id: str = Field(min_length=1, description="要修改的目标id")
    asset_id: str = Field(min_length=1, description="要分配给目标的资产id")
    parameters: dict | None = Field(
        default=None,
        description="仅参数化综合色墙漆使用：{lightness: light|mid|deep, saturation: 0.35~1.25, finish: matte|eggshell}",
    )


class DesignWorkTypeInput(BaseModel):
    model_config = ConfigDict(extra="forbid")

    work_type: Literal["LIGHT", "HEAVY"]
    reason: str = Field(
        min_length=8,
        max_length=500,
        description="为什么当前获批工作属于轻度修改或完整设计",
    )


def set_design_work_type(work_type: str, reason: str):
    """Request a graph-owned work-type transition before Scheme mutation."""

    return json.dumps(
        {
            "status": "WORK_TYPE_REQUEST_VALID",
            "requested_work_type": work_type,
            "reason": reason,
        },
        ensure_ascii=False,
    )


def update_scheme(target_id: str, asset_id: str, parameters: dict | None = None):
    """修改 SchemeStore 中一个 target 的 Asset 和可选参数。"""
    return get_scheme_store().update(target_id, asset_id, parameters)


class DesignCriticInput(BaseModel):
    model_config = ConfigDict(extra="forbid")

    review_request: str = Field(
        min_length=1,
        max_length=4_000,
        description="需要 Critic 独立复核的用户目标、设计范围、已知取舍或具体疑问",
    )


def ask_design_critic(review_request: str):
    """Ask the read-only Critic for a delivery-blocking review verdict."""

    from ..agent.critic import run_critic_review

    return run_critic_review(
        review_request,
        design_context=DESIGN_CONTEXT,
        house_context=build_house_context(ACTIVE_SCENE_MANIFEST),
        tool_definitions=critic_tools,
        execute_readonly_tool=execute_tool,
        build_visual_message=visual_evidence_message,
    )


tools = [
    {
        "type": "function",
        "function": {
            "name": "get_today_whether",
            "description": "输入今天的年月日，获取今天的天气",
            "parameters": WhetherInput.model_json_schema(),
        },
    },
    {
        "type": "function",
        "function": {
            "name": "get_room_by_id",
            "description": "输入房间id，从活动 scene_manifest 查询房间真实信息",
            "parameters": RoomInput.model_json_schema(),
        },
    },
    {
        "type": "function",
        "function": {
            "name": "filter_assets",
            "description": "按目标兼容性、ANCHOR/SUPPORT/QUIET 关系和明显视觉冲突过滤候选 Asset；固定至少缩减 70%，返回可视化比较候选、硬否决和预算暂缓及稳定原因码。",
            "parameters": FilterAssetsInput.model_json_schema(),
        },
    },
    {
        "type": "function",
        "function": {
            "name": "get_asset_card_by_id",
            "description": "输入真实 asset_id，同时读取完整设计卡与权威预览图。预览用于理解候选外观，不能替代房间实时渲染。",
            "parameters": AssetCardInput.model_json_schema(),
        },
    },
    {
        "type": "function",
        "function": {
            "name": "load_scheme",
            "description": "读取当前完整设计 Scheme",
            "parameters": GetCurrentSchemeInput.model_json_schema(),
        },
    },
    {
        "type": "function",
        "function": {
            "name": "observe_room",
            "description": "向后端渲染会话请求当前已验证 Scheme 的单屋多视角 JPEG 证据。它不修改 Scheme；只有 status=ready、像素覆盖已验证且单图质量有效时，图片才作为模型视觉输入。不完整观察只返回诊断元数据，不能据此下视觉结论。",
            "parameters": ObserveRoomInput.model_json_schema(),
        },
    },
    {
        "type": "function",
        "function": {
            "name": "observe_home_harmony",
            "description": "向后端渲染会话请求全屋代表视图和真实门洞过渡 JPEG 证据。它不修改 Scheme；只有 status=ready、像素覆盖已验证且单图质量有效时，图片才作为模型视觉输入。不完整观察只返回诊断元数据。",
            "parameters": ObserveHomeHarmonyInput.model_json_schema(),
        },
    },
    {
        "type": "function",
        "function": {
            "name": "set_design_work_type",
            "description": "在开始写入 Scheme 前声明当前已获用户批准的工作类型。LIGHT 仅用于单房间、最多两个不同 target 且不改变跨空间主材关系的轻度修改；HEAVY 用于完整房间、多表面联动、跨空间或整屋设计。规划、询问和等待审批时不得调用。状态只能 NOT_STARTED→LIGHT/HEAVY 或 LIGHT→HEAVY，不能降级；本工具必须与 update_scheme 分开在不同 Agent 工具轮次调用。",
            "parameters": DesignWorkTypeInput.model_json_schema(),
        },
    },
    {
        "type": "function",
        "function": {
            "name": "update_scheme",
            "description": "基于当前完整 Scheme 修改一个目标并执行 Validator。LangGraph 工作类型为 NOT_STARTED 时写入会被代码拒绝；必须先在独立工具轮次成功设置 LIGHT 或 HEAVY。",
            "parameters": UpdateInput.model_json_schema(),
        },
    },
    {
        "type": "function",
        "function": {
            "name": "ask_design_critic",
            "description": "让独立只读 Critic Agent 自主读取 Scheme、资产和真实渲染并给出交付门禁结论。完整设计在取得真实渲染后、交付前必须使用；只有 PASS 才能交付。REVISE 或 UNABLE_TO_JUDGE 时必须继续修改或补证并重新复审；复审通过后再次修改 Scheme 会使 PASS 失效。轻度修改不使用，除非用户明确要求独立审查。Critic 不修改方案。",
            "parameters": DesignCriticInput.model_json_schema(),
        },
    },
]


_CRITIC_READ_ONLY_TOOL_NAMES = {
    "get_room_by_id",
    "get_asset_card_by_id",
    "load_scheme",
    "observe_room",
    "observe_home_harmony",
}
critic_tools = [
    definition
    for definition in tools
    if definition["function"]["name"] in _CRITIC_READ_ONLY_TOOL_NAMES
]


tool_map = {
    "get_today_whether": (WhetherInput, get_today_whether),
    "get_room_by_id": (RoomInput, get_room_by_id),
    "filter_assets": (FilterAssetsInput, filter_asset_candidates),
    "get_asset_card_by_id": (AssetCardInput, get_asset_card_by_id),
    "load_scheme": (GetCurrentSchemeInput, load_scheme),
    "observe_room": (ObserveRoomInput, observe_room),
    "observe_home_harmony": (ObserveHomeHarmonyInput, observe_home_harmony),
    "set_design_work_type": (DesignWorkTypeInput, set_design_work_type),
    "update_scheme": (UpdateInput, update_scheme),
    "ask_design_critic": (DesignCriticInput, ask_design_critic),
}


def _trace_tool_output(result) -> dict:
    """Keep visual evidence out of trace JSON while preserving its receipt."""
    if isinstance(result, VisualToolOutput):
        return {
            "result_type": "visual",
            "kind": result.kind,
            "summary": result.summary,
            "image_count": len(result.images),
            "image_labels": [label for label, _ in result.images],
        }
    return {"result_type": "text", "content": str(result)}


def execute_tool(tool_name: str, args: dict, tool_call_id: str | None = None):
    """按名称执行一个工具：参数验证 + 调用，返回字符串或 VisualToolOutput。

    LangGraph 的 tools_node 直接复用这份共享执行逻辑。tool_call_id 用于把
    该工具执行在 LangSmith 里打出的 run 与评估证据包里的 tool_calls 对齐。
    """
    with langsmith_tool_span(tool_name, args, tool_call_id) as span:
        if tool_name not in tool_map:
            result = "该工具不存在"
        else:
            input_model, function = tool_map[tool_name]
            try:
                validated = input_model.model_validate(args)
            except ValidationError as error:
                result = str(error.errors())
            else:
                result = function(**validated.model_dump())

        if span is not None:
            span.end(outputs=_trace_tool_output(result))
        return result


def tool_execute(tool_call):
    """兼容 OpenAI 风格的 tool_call 对象（.function.name / .function.arguments）。"""
    tool_name = tool_call.function.name
    args = json.loads(tool_call.function.arguments)
    return execute_tool(tool_name, args, getattr(tool_call, "id", None))


def visual_evidence_message(outputs: list[VisualToolOutput]) -> dict:
    """Put tool visuals in a new model message as image blocks, never URL text."""

    content: list[dict[str, object]] = [
        {
            "type": "text",
            "text": "以下是工具返回的视觉输入。资产卡预览用于理解候选外观；只有 observe_* 中通过 status=ready、pixel_verified_coverage 和单图质量门禁后实际附带的图片，才是当前 Scheme 的实时渲染证据。不完整观察的诊断元数据不是视觉证据。不要把两者混淆。",
        }
    ]
    for output in outputs:
        content.append({"type": "text", "text": f"视觉类型：{output.kind}"})
        for label, image_url in output.images:
            content.append({"type": "text", "text": label})
            content.append({"type": "image_url", "image_url": {"url": image_url}})
    return {"role": "user", "content": content}
