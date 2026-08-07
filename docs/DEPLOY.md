# 部署上线指南

## 架构

```
Vercel(前端 Next.js 静态)  ──HTTPS──►  PaaS 常驻容器(Docker)
                                        ├─ agent-api     FastAPI :8000  (Agent API,对外)
                                        ├─ render-bridge FastAPI :8765  (任务队列,内网)
                                        └─ render-worker playwright 常驻 (无端口,浏览器渲染)
数据卷 /data: current_scheme.json + checkpoints.sqlite
```

- **前端(Vercel)**:展示 3D 场景,轮询 `/api/scheme` 感知方案变化。
- **agent-api**:对话/SSE/会话/Scheme 接口;`RENDER_SESSION_ID=worker` 把视觉命令提交给 worker 渲染会话。
- **render-bridge**:Agent ↔ 浏览器渲染会话的任务队列(进程内 broker,以后可换 Redis)。
- **render-worker**:playwright 无头浏览器(headless + SwiftShader 软件渲染)打开 Vercel 页面,
  页面内 `renderBridgeWorker.ts`(Web Worker)完成心跳→拉命令→渲染→回传;Python 侧只保活/重启。

> 为什么不用 Vercel 承载后端:serverless 函数 10s 超时、无持久进程/可写磁盘,与长任务 + SSE + 无头渲染 worker + SQLite 冲突。前端留 Vercel,后端用常驻容器。

> 💡 **1GB 小内存 VPS 方案（t3.micro/t4g.micro）**：前端在 Vercel 时，后端可只跑
> `agent-api` + `render-bridge`（约 400MB），**不跑 render-worker**——渲染改由用户浏览器
> 注册为 `local-demo` 会话完成（GPU 截图回传），服务器零渲染开销。
> 配套精简镜像 `backend/Dockerfile.lite`（不下载 Chromium）、compose/nginx/脚本/runbook
> 全部在 `deploy/aws/`，按 `deploy/aws/README.md` 部署即可。注意该方案必须给 bridge
> 配 HTTPS（Vercel 页面 mixed-content 限制），且需要一个浏览器标签页常开当渲染器。

---

## 环境变量

| 变量 | 作用 | 示例 |
|---|---|---|
| `OPENAI_API_KEY` | 模型密钥 | `sk-...` |
| `OPENAI_PROXY` | 本机代理;生产**不设**即直连 | `http://127.0.0.1:7892` |
| `OPENAI_MODEL` | 模型名 | `gpt-5.6-luna` |
| `VIEWER_URL` | viewer 生产页面(Vercel 域名) | `https://my-house.vercel.app` |
| `RENDER_SESSION_ID` | agent 提交视觉命令的会话 | `worker` |
| `AGENT_API_TOKEN` | Bearer 鉴权(chat/sessions);`/api/scheme` 匿名 | 随机串 |
| `CORS_ORIGINS` | 逗号分隔白名单,**必含 Vercel 域名** | `https://my-house.vercel.app` |
| `SCHEME_DATA_DIR` | 后端方案数据目录 | `/data` |
| `DATA_DIR` | 会话 checkpoint 目录 | `/data` |

前端(Vercel Project Settings → Environment Variables):
- `NEXT_PUBLIC_AGENT_API_URL=https://<agent-api 域名>`(供 `RoomExperience.tsx` 拉 `/api/scheme`)

---

## 前端部署(Vercel)

1. 项目在 Vercel 建站(Next.js 框架)。
2. 构建命令:仓库里 `viewer/` 是前端,根目录导入或设 Root Directory=`viewer`。
3. 设 `NEXT_PUBLIC_AGENT_API_URL`(agent-api 公网域名)。
4. agent-api 与 render-bridge 的 `CORS_ORIGINS` 必须包含 `https://<你的域名>.vercel.app`(及自定义域名)。

---

## 后端部署

### 方式 A:docker-compose(独立 VPS 或任何跑 Docker 的机器)

```bash
cd backend
export OPENAI_API_KEY='sk-...' \
       VIEWER_URL='https://my-house.vercel.app' \
       AGENT_API_TOKEN='$(openssl rand -hex 24)' \
       CORS_ORIGINS='https://my-house.vercel.app'
docker compose up --build -d
```

- `agent-api:8000` 对外;`render-bridge:8765` 默认也映射(仅本地调试,PaaS 上可去掉)。
- 三服务 healthcheck 就绪后,验证:见下方「验收清单」。

### 方式 B:Fly.io(推荐试水)

```bash
cd backend
fly launch --no-deploy --name <app-name>
```

编辑 `fly.toml` 增加进程与卷:

```toml
[processes]
  api = "python -m uvicorn backend.agent_api.main:app --host 0.0.0.0 --port 8000"
  bridge = "python -m uvicorn backend.render_bridge.main:app --host 0.0.0.0 --port 8765"
  render-worker = "python -m backend.render_worker.main"

[mounts]
  source = "data"
  destination = "/data"

[[services]]
  internal_port = 8000
  protocol = "tcp"
  [[services.ports]]
    handlers = ["http"]
    port = 80
```

设 secrets/env 后 `fly deploy`。CPU 档可跑 SwiftShader 软件渲染。

### 方式 C:Railway

- 同一个 Dockerfile 建 **两个 Service**:`agent-api`(start command 指向 agent-api)、`render-bridge`(指向 bridge)。
- 再建第三个 Service `render-worker`。
- 各 Service 用 Railway **Volume** 挂 `/data`。
- 设 `CORS_ORIGINS`、`OPENAI_API_KEY`、`VIEWER_URL` 等(项目级 Variables)。

### 方式 D:HuggingFace Spaces(Docker,单容器)

- 用 `backend/entrypoint.sh` 同时拉起三个进程:

```dockerfile
FROM python:3.11-slim
WORKDIR /app
COPY backend/requirements.txt backend/requirements.txt
RUN pip install --no-cache-dir -r backend/requirements.txt \
    && python -m playwright install --with-deps chromium
COPY . /app/
ENV PLAYWRIGHT_BROWSERS_PATH=/ms-playwright
CMD ["bash", "backend/entrypoint.sh"]
```

- Spaces 免费档共享 CPU 较弱,observe 可能接近超时;建议升级到 CPU 档或选 Fly/Railway。

---

## 无头渲染 worker 与降级

- worker 起不来时:**既有降级机制自动生效**。agent 调 observe 工具 → render-bridge 返回
  `renderer_not_online` → 工具返回"渲染器未在线,不能把文本当作视觉证据" →
  Agent 按系统提示如实说明缺少视觉证据、不宣布完成。read/update 工具不受影响。
- 该降级路径也是演示脚本的一部分,不要当作故障隐藏。

---

## 验收清单

1. `docker compose up` 三服务 healthy;`curl <agent-api>/api/health` 返回 `{"status":"ok",...}`。
2. 鉴权:`curl -X POST <agent-api>/api/chat -d '{"thread_id":"t","message":"hi"}'` 无 token 返回 401。
3. 会话持久化:两次 POST `/api/chat`(同 thread)后重启容器,`GET /api/sessions/{thread}/messages` 历史仍在。
4. SSE:带 token `curl -N -X POST <agent-api>/api/chat/stream` 可见
   `event: meta / message_delta / tool_call / tool_result / done`。
5. Scheme 链路:Agent 修改方案后,`GET /api/scheme/version` 的 scheme_id 变化,Vercel 页面自动刷新。
6. 视觉门禁:让 Agent 走完整流程(load_scheme → get_room_by_id → get_asset_by_category →
   update_scheme → observe_room → observe_home_harmony → 宣布完成),确认拿到 worker 渲染图。
7. 降级:停掉 render-worker,Agent 明确回复"缺少视觉证据、不宣布完成"。
