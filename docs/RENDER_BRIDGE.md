# 后端 Agent 与实时渲染器的边界

`observe_room` 和 `observe_home_harmony` 是后端 Agent 工具；Three.js 页面不是工具服务器。

```text
AgentLoop → POST render bridge → 命令队列 → 当前浏览器渲染会话
AgentLoop ← 图片与元数据 ← 结果回传 ← 切镜头、稳定渲染、截图
```

## 模块职责

- `agentloop.py`：向模型注册两个工具，提交观察任务；收到结果后剥离 data URL 的元数据作为 tool result，并把 JPEG 作为真正的 `image_url` 输入块送回模型。
- `render_bridge.py`：后端任务边界。按 `session_id` 校验任务、等待结果、报告 `renderer_not_online`、超时或渲染失败。
- `viewer/app/components/RoomExperience.tsx`：渲染 worker。轮询自己的 session，执行既有截图函数并回传；不再暴露 `window` 工具，也不拥有 Agent 决策权。

## 本地启动

第一终端：

```powershell
python render_bridge.py
```

第二终端启动 Viewer，并用相同 session 打开页面：

```powershell
cd viewer
npm run dev -- --host 127.0.0.1
# 浏览器： http://localhost:3000/?render_session=local-demo
```

第三终端启动 Agent。默认 session 是 `local-demo`；多人或多浏览器时必须改成唯一值，并让浏览器 URL 与环境变量一致。

```powershell
$env:RENDER_SESSION_ID = "local-demo"
$env:RENDER_BRIDGE_URL = "http://127.0.0.1:8765"
python agentloop.py
```

## 失败与验收

- 浏览器未注册：Agent 收到 `renderer_not_online`，不会把文字描述误当图片。
- 截图或回传失败：任务以 `failed` 返回，并保留错误原因。
- 90 秒内无结果：任务以 `renderer_timeout` 返回。
- 不同 `session_id` 不能回传或窃取彼此的任务。
- 工具不会改动 Scheme；模型仍须经 `update_scheme` 和 Validator 修改方案。

当前 bridge 是本地、进程内队列，目的是把边界、协议和失败模式讲清楚。部署版可将 `RenderTaskBroker` 替换为 Redis/消息队列、将 session 认证替换为签名令牌，而无需改变 Agent 工具契约。
