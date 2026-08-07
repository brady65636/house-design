# 实时渲染视觉观察工具

这两个工具是 Agent 的视觉传感器，不是审美裁判，也不会修改 Scheme、网格或资产库。模型必须先调用既有的读取、检索、修改与 Validator 链路；只有在 Scheme 已应用、PBR 已就绪后，才能调用这里的观察工具。

## 1. `observe_room`

### 解决的问题

一个透视画面无法证明模型看见了房间的全部墙面。`observe_room` 从版本化的房间摄像机轨迹中确定性选择 3–6 个机位，返回真实 Three.js 渲染 JPEG 和对应的稳定目标 ID。

### 输入

```ts
observeRoom(roomId: string, focusTargetIds?: string[])
```

- `roomId` 必须是活动 `scene_manifest.json` 中的设计空间。
- `focusTargetIds` 只能是该房间的墙、地或顶目标；它请求额外重点，不允许模型传任意 3D 坐标。

### 输出

```ts
{
  tool: "observe_room",
  status: "ready" | "incomplete_observation",
  evidenceLevel: "declared_track_coverage",
  scheme: { schemeId, title },
  room: { id, label },
  views: [{
    viewId, label, purpose, focusTargetIds,
    imageDataUrl // JPEG data URL；适配器必须把它作为图片输入传给视觉模型
  }],
  declaredCoverage: { [targetId]: viewIds[] },
  uncoveredTargetIds: []
}
```

`declared_track_coverage` 的含义很重要：当前覆盖来自经过人工验收的轨迹关键帧及其 `focusTargetIds`，并不伪称已经完成像素级 ID Pass 统计。后续可在不改变工具契约的情况下将该字段升级为 `id_pass_verified`。

### 运行边界

- 固定使用同一个 Three.js renderer、ACES、HDR、阴影和当前 Scheme；
- 等待活动材质 PBR Promise 和两个动画帧稳定后再截图；
- 截图时隐藏 `reference_only` 家具，保证本轮硬装审查不被家具干扰；
- 截图限定为 1280px 宽 JPEG，防止工具结果无限膨胀；
- 仅返回证据和状态，绝不声称“设计已协调”。

## 2. `observe_home_harmony`

### 解决的问题

单屋看起来成立，不代表从玄关走进客厅、从卧室进入衣帽间或跨过厨房玻璃门时仍属于一套设计。`observe_home_harmony` 只在所有房间都完成单屋声明覆盖后生成全屋证据包。

### 输入

```ts
observeHomeHarmony()
```

它没有“自定义相机坐标”或“任意房间连接”参数。所有跨空间关系必须来自已命名的真实门洞；未建模的动线不能被工具虚构。

### 输出

```ts
{
  tool: "observe_home_harmony",
  status: "ready" | "incomplete_observation",
  evidenceLevel: "declared_track_coverage",
  scheme: { schemeId, title },
  roomContactSheet, // 11 个空间的统一光照代表图
  transitionPairs: [{
    id, openingId, rationale,
    from: { imageDataUrl, focusTargetIds },
    to: { imageDataUrl, focusTargetIds }
  }],
  incompleteRooms: []
}
```

当前过渡对只覆盖带稳定 `openingId` 的门洞：两间次卧/主卧与公共区、主卧—衣帽间—主卫、厨房玻璃移门与公共区。它们由 `viewer/app/data/visualObservation.ts` 维护，并在变更户型或门洞时与 `scene_manifest.json` 同步验证。

## 后端 Agent 调用

`observe_room` 与 `observe_home_harmony` 已注册在 `agentloop.py`。后端通过 `render_bridge.py` 给指定渲染会话下发命令，浏览器仅执行切镜头、稳定渲染和截图回传；它不再暴露浏览器全局工具。

`agentloop.py` 会将工具元数据作为 tool result，并把每个 `imageDataUrl` 转为模型 API 的真正图像输入块；绝不能只把 data URL、磁盘路径或截图文件名作为普通文本发送。启动与会话配置见 `docs/RENDER_BRIDGE.md`。

## 验收

- 单屋工具始终返回 3–6 张按稳定轨迹生成的图片；
- 每个房间的所有设计目标在 `declaredCoverage` 中有证据机位；
- 全屋工具若发现单屋未覆盖，必须返回 `incomplete_observation`，不得生成“全屋协调”证据；
- 全屋过渡对引用真实 `openingId` 和活动住宅房间 ID；
- 两个工具不修改 Scheme、GLB、资产目录或任何用户偏好。
