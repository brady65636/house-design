# 1GB 小内存 VPS 部署（最终架构：前后端全上服务器）

所有服务跑在同一台 1GB Lightsail 实例（44.204.200.204），同一域名 `agent.brady-zhang.com`，
**同域** = 无 CORS、无 mixed-content，浏览器渲染天然闭环。

```
你的浏览器打开 https://agent.brady-zhang.com/  （主页 3D 查看 / /chat 对话页）
   │  页面自动注册为 local-demo 渲染会话（GPU + canvas.toDataURL 截图回传）
   ▼
nginx (TLS, certbot)
   ├─ /           → 前端 node 生产服务  (127.0.0.1:3000, systemd: house-viewer)
   │                 └─ /chat-proxy/...  前端服务端代理 → agent-api（注入 token）
   ├─ /api/       → agent-api           (Docker:8000)
   └─ /bridge     → render-bridge       (Docker:8765, 去掉 /bridge 前缀)
```

## 对话页 /chat

`/chat` 是独立的对话页（主页右上角「对话助手」进入）。数据通路：

```
浏览器 → /chat-proxy/chat/stream (同源)
       → house-viewer 服务端注入 Bearer token
       → agent-api :8000 /api/chat/stream (SSE)
```

token 不放进前端 bundle（打进 bundle 形同公开），由 house-viewer 服务端注入，
因此 **house-viewer 进程必须有 AGENT_API_TOKEN**。上服务器前一次性配置：

```bash
# 服务器上执行一次：复用 deploy/aws/.env 里的 AGENT_API_TOKEN
sudo mkdir -p /etc/systemd/system/house-viewer.service.d
printf '[Service]\nEnvironmentFile=/opt/house-design/deploy/aws/.env\n' \
  | sudo tee /etc/systemd/system/house-viewer.service.d/override.conf
sudo systemctl daemon-reload && sudo systemctl restart house-viewer
systemctl show house-viewer -p Environment  # 确认已注入
```

可选：`AGENT_API_UPSTREAM` 覆盖后端地址（默认 `http://127.0.0.1:8000`）。

> 注意：`observe_room` 等视觉工具依赖浏览器渲染会话。`/chat` 页右侧已内嵌 3D 查看器
> （iframe 加载 `/`，默认显示、可隐藏），渲染会话随聊天页在线，无需另开标签页。

## 服务器当前服务清单

| 服务 | 运行方式 | 端口 | 状态 |
|---|---|---|---|
| agent-api | docker compose (aws_data 卷) | 127.0.0.1:8000 | healthy |
| render-bridge | docker compose | 127.0.0.1:8765 | healthy |
| viewer 前端 | systemd `house-viewer` | 127.0.0.1:3000 | active(自启) |
| nginx + TLS | systemd nginx + certbot | 80/443 | active |

## 更新代码

**后端**（本机）：
```bash
cd deploy/aws && ./deploy.sh ubuntu@44.204.200.204 /opt/house-design /path/to/key.pem
# 服务器上：
cd /opt/house-design && docker compose -f deploy/aws/docker-compose.aws.yml up -d --build
```

**前端**（本机构建 → 上传 → 重启）：
```bash
cd viewer && NEXT_PUBLIC_AGENT_API_URL=https://agent.brady-zhang.com npm run build
tar -czf /tmp/dist.tar.gz dist
scp -i /path/to/key.pem /tmp/dist.tar.gz ubuntu@44.204.200.204:/tmp/
ssh -i /path/to/key.pem ubuntu@44.204.200.204 \
  'cd /opt/house-design/viewer && sudo rm -rf dist && sudo tar -xzf /tmp/dist.tar.gz \
   && sudo chown -R ubuntu:ubuntu /opt/house-design/viewer && sudo systemctl restart house-viewer'
```

或服务器端 `git pull` 源码后重新 build/start（1GB 上 build 有 OOM 风险，推荐本机构建）。

## 关键文件位置

- 后端 compose：`/opt/house-design/deploy/aws/docker-compose.aws.yml` + `.env`
- 前端：`/opt/house-design/viewer`（`npm start` = `vinext start`，读 `dist/`）
- nginx：`/etc/nginx/sites-available/house-design`
- 证书：certbot 自动续期（`agent.brady-zhang.com`）
- 数据（方案 + SQLite）：Docker 卷 `aws_data` → `/data`

## 验收清单（上线后）

1. `curl -sk https://agent.brady-zhang.com/api/health` → ok
2. 浏览器打开 `https://agent.brady-zhang.com/` → 页面正常，自动注册渲染会话
3. `curl -sk https://agent.brady-zhang.com/bridge/v1/render-sessions/local-demo/status` → `"online":true`
4. Agent 走完整流程（observe_room）→ 拿到你浏览器截的图
5. 关标签页 90 秒 → agent 观察工具报"渲染器未在线"（设计好的降级）
6. 打开 `https://agent.brady-zhang.com/chat` → 发一条消息，回复流式出现
7. `curl -sk https://agent.brady-zhang.com/chat-proxy/health` → `{"status":"ok",...}`（代理可达）

## 常见问题

- **改了前端没生效**：build 要带 `NEXT_PUBLIC_AGENT_API_URL`，重启 `house-viewer` 服务。
- **/chat 页报 503/401**：house-viewer 没配 `AGENT_API_TOKEN`（或配错），见上面一次性配置。
- **页面不注册渲染会话**：确认地址是 `https://agent.brady-zhang.com/`（默认同域 /bridge），
  或手动加 `?render_bridge=https://agent.brady-zhang.com/bridge`。
- **CRLF 坑**：在 Windows 上生成的 `.env` 会带 `\r`，导致密钥/HTTP 畸形。用 `sed -i 's/\r$//'` 转 LF。
- **npm ci 报 lock 不同步**：本地 `cd viewer && npm install` 同步 lock 后提交。
