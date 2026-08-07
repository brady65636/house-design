"""共享工具层：agentloop（CLI 入口）与 agent_graph（LangGraph 编排）都从这里取工具。

依赖方向：agentloop -> agent_graph -> tools。工具定义、SYSTEM_PROMPT 和
当前 Scheme 状态只存在这里，避免第二事实源。

Scheme 状态不再使用模块级可变单例，改由线程安全的 SchemeStore 持有
（scheme/store.py）；CLI/API/测试通过 get_scheme_store() / set_scheme_store()
共用同一份状态。
"""

import json
from dataclasses import dataclass
from pathlib import Path

import httpx
from pydantic import BaseModel, ConfigDict, Field, ValidationError

from ..config import settings
from ..prompt_context import build_design_context, build_skill_context, build_system_prompt
from ..scheme.schema import Scheme
from ..scheme.store import SchemeStore, read_json
from ..scheme.validator import validate_scheme


ACTIVE_SCENE_MANIFEST = read_json(settings.scene_manifest_path)
ACTIVE_ASSET_MANIFEST = read_json(settings.asset_manifest_path)
DESIGN_CONTEXT = build_design_context(settings.design_md_path)
DESIGN_SKILL_CONTEXT = build_skill_context(settings.design_skill_path)

SYSTEM_PROMPT = build_system_prompt(
    ACTIVE_SCENE_MANIFEST,
    ACTIVE_ASSET_MANIFEST,
    DESIGN_CONTEXT,
    DESIGN_SKILL_CONTEXT,
)

_scheme_store: SchemeStore | None = None


def get_scheme_store() -> SchemeStore:
    """惰性构建并缓存全局 SchemeStore（CLI/API/测试共用一份）。"""
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


class CategoryInput(BaseModel):
    model_config = ConfigDict(extra="forbid")

    category: str = Field(description="要查询的资产类型")


def get_asset_by_category(category: str):
    """Return every compact brief in one asset category, with no pagination."""

    assets = read_json(settings.asset_manifest_path)
    result = [asset for asset in assets["assets"] if asset["category"] == category]
    if not result:
        return "该类型不存在，请检查输入"
    return json.dumps(result, ensure_ascii=False)


class AssetCardInput(BaseModel):
    model_config = ConfigDict(extra="forbid")

    asset_id: str = Field(min_length=1, description="要读取详细资产卡的真实资产 id")


def get_asset_card_by_id(asset_id: str):
    """Return the detailed visual and objective card for one real asset ID."""

    cards = read_json(settings.asset_cards_path).get("cards", {})
    card = cards.get(asset_id) if isinstance(cards, dict) else None
    if not isinstance(card, dict):
        return "该资产卡不存在，请先通过 get_asset_by_category 查询真实 asset_id"
    return json.dumps(card, ensure_ascii=False)


class GetCurrentSchemeInput(BaseModel):
    model_config = ConfigDict(extra="forbid")


def load_scheme():
    """返回当前内存中的完整 Scheme JSON 字符串。"""
    return json.dumps(get_scheme_store().get(), ensure_ascii=False)


class ObserveRoomInput(BaseModel):
    model_config = ConfigDict(extra="forbid")

    room_id: str = Field(min_length=1, description="需要渲染观察的真实房间 ID")
    focus_target_ids: list[str] = Field(default_factory=list, max_length=3)


class ObserveHomeHarmonyInput(BaseModel):
    model_config = ConfigDict(extra="forbid")


@dataclass
class VisualToolOutput:
    """Tool metadata plus images which must be passed back as image inputs."""

    summary: str
    images: list[tuple[str, str]]


def _request_render_evidence(tool: str, args: dict) -> VisualToolOutput | str:
    """Ask the backend render bridge; the Agent never calls browser JavaScript."""

    bridge_url = settings.render_bridge_url.rstrip("/")
    session_id = settings.render_session_id
    try:
        response = httpx.post(
            f"{bridge_url}/v1/render-sessions/{session_id}/commands",
            json={"tool": tool, "args": args, "timeout_ms": 90_000},
            timeout=95,
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
    images: list[tuple[str, str]] = []
    summary = dict(payload)
    if tool == "observe_room":
        views = []
        for view in payload.get("views", []):
            image_url = view.pop("imageDataUrl", None)
            views.append(view)
            if image_url:
                images.append((f"{payload.get('room', {}).get('label', '房间')} · {view.get('label', '观察视图')}", image_url))
        summary["views"] = views
    else:
        contact_sheet = summary.pop("roomContactSheet", None)
        if contact_sheet:
            images.append(("全屋代表视图总览", contact_sheet))
        pairs = []
        for pair in payload.get("transitionPairs", []):
            compact_pair = dict(pair)
            for side in ("from", "to"):
                view = dict(compact_pair.get(side, {}))
                image_url = view.pop("imageDataUrl", None)
                compact_pair[side] = view
                if image_url:
                    images.append((f"过渡 {pair.get('id', '')} · {side}", image_url))
            pairs.append(compact_pair)
        summary["transitionPairs"] = pairs
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


def update_scheme(target_id: str, asset_id: str):
    """修改 SchemeStore 中一个 target 的 asset_id，执行 Validator，写盘并更新内存。"""
    return get_scheme_store().update(target_id, asset_id)


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
            "name": "get_asset_by_category",
            "description": "输入资产类型，从活动 asset_manifest 查询该类别全部真实资产的简短索引；不接受 limit。",
            "parameters": CategoryInput.model_json_schema(),
        },
    },
    {
        "type": "function",
        "function": {
            "name": "get_asset_card_by_id",
            "description": "输入真实 asset_id，从 asset_cards 查询该资产的完整客观信息与审美设计卡。",
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
            "description": "向后端渲染会话请求当前已验证 Scheme 的单屋多视角 JPEG 证据。它不修改 Scheme；结果图片将作为视觉输入提供给模型。",
            "parameters": ObserveRoomInput.model_json_schema(),
        },
    },
    {
        "type": "function",
        "function": {
            "name": "observe_home_harmony",
            "description": "向后端渲染会话请求全屋代表视图和真实门洞过渡 JPEG 证据。它不修改 Scheme。",
            "parameters": ObserveHomeHarmonyInput.model_json_schema(),
        },
    },
    {
        "type": "function",
        "function": {
            "name": "update_scheme",
            "description": "基于当前完整 Scheme 修改一个目标并执行 Validator",
            "parameters": UpdateInput.model_json_schema(),
        },
    },
]


tool_map = {
    "get_today_whether": (WhetherInput, get_today_whether),
    "get_room_by_id": (RoomInput, get_room_by_id),
    "get_asset_by_category": (CategoryInput, get_asset_by_category),
    "get_asset_card_by_id": (AssetCardInput, get_asset_card_by_id),
    "load_scheme": (GetCurrentSchemeInput, load_scheme),
    "observe_room": (ObserveRoomInput, observe_room),
    "observe_home_harmony": (ObserveHomeHarmonyInput, observe_home_harmony),
    "update_scheme": (UpdateInput, update_scheme),
}


def execute_tool(tool_name: str, args: dict):
    """按名称执行一个工具：参数验证 + 调用，返回字符串或 VisualToolOutput。

    LangGraph 的 tools_node 直接复用这份共享执行逻辑。
    """
    if tool_name not in tool_map:
        return "该工具不存在"

    input_model, function = tool_map[tool_name]
    try:
        validated = input_model.model_validate(args)
    except ValidationError as error:
        return str(error.errors())

    return function(**validated.model_dump())


def tool_execute(tool_call):
    """兼容 OpenAI 风格的 tool_call 对象（.function.name / .function.arguments）。"""
    tool_name = tool_call.function.name
    args = json.loads(tool_call.function.arguments)
    return execute_tool(tool_name, args)


def visual_evidence_message(outputs: list[VisualToolOutput]) -> dict:
    """Put JPEGs in a new model message as image blocks, never as URL text."""

    content: list[dict[str, object]] = [
        {
            "type": "text",
            "text": "以下是工具刚刚生成的实时渲染证据。仅根据这些图像和工具元数据做视觉判断；不要假设未显示的墙面。",
        }
    ]
    for output in outputs:
        for label, image_url in output.images:
            content.append({"type": "text", "text": label})
            content.append({"type": "image_url", "image_url": {"url": image_url}})
    return {"role": "user", "content": content}
