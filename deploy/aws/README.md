# 1GB 小内存 VPS 部署（t3.micro / t4g.micro 方案）

前端在 Vercel，后端只跑 `agent-api` + `render-bridge` 两个进程（约 400MB）。
**渲染不依赖服务器**：打开 Vercel 页面时你的浏览器自动注册为 `local-demo` 渲染会话，
用 GPU 截图回传给 agent（`canvas.toDataURL`）。服务器零 Chromium、零渲染开销。

```
你的浏览器(Vercel 页面, GPU 渲染截图)
   │  ?render_bridge=https://<域名>/bridge
   ▼
https://<域名> ──nginx──► 127.0.0.1:8000   agent-api    (chat/SSE/scheme)
               └──────► 127.0.0.1:8765   render-bridge (浏览器渲染会话)
Vercel 前端 ──NEXT_PUBLIC_AGENT_API_URL──► https://<域名>/api/scheme
```

> ⚠️ 必须要有**一个域名**：Vercel 页面是 HTTPS，浏览器不允许 HTTPS 页面去 fetch http 的 bridge
> （mixed content）。所以 bridge/agent 必须走 HTTPS，用免费 Let's Encrypt 证书即可。

---

## 一、准备

| 需要 | 说明 |
|---|---|
| AWS 1GB 实例 | 本次已买（t3.micro/t4g.micro），装 Ubuntu 22.04/24.04 |
| 一个域名 | 解析一个 A 记录指向服务器 IP（可以二级域名，如 `agent.xxx.com`） |
| Vercel 项目 | 已有，Root Directory 为 `viewer` |

## 二、服务器初始化（一次性）

```bash
ssh-keygen -t ed25519            # 本机生成密钥（已有可跳过）
ssh-copy-id ubuntu@<服务器IP>

# 服务器上：
ssh ubuntu@<服务器IP>
sudo apt update && sudo apt install -y docker.io docker-compose-v2 nginx certbot python3-certbot-nginx ufw
sudo systemctl enable --now docker
# 本用户免 sudo 跑 docker（重登生效）
sudo usermod -aG docker $USER
exit   # 重连

# 防火墙只开 80/443（8000/8765 只绑 127.0.0.1，不对外开放）
sudo ufw allow 22 && sudo ufw allow 80 && sudo ufw allow 443 && sudo ufw enable
```

## 三、上传代码（本机执行）

```bash
cd deploy/aws
./deploy.sh ubuntu@<服务器IP>
```

脚本会打包（排除 node_modules/output/blender/viewer 等）→ scp → 解压到 `/opt/house-design`，
并生成 `deploy/aws/.env`（若不存在）。

## 四、填环境变量（服务器上）

```bash
ssh ubuntu@<服务器IP>
cd /opt/house-design/deploy/aws
nano .env
```

按 `.env.example` 填：
- `OPENAI_API_KEY`、`OPENAI_MODEL`（与本地一致；服务器直连，不要配 OPENAI_PROXY）
- `CORS_ORIGINS=https://<你的 Vercel 域名>`（如 `https://my-house.vercel.app`）
- `AGENT_API_TOKEN=$(openssl rand -hex 24)`

## 五、启动后端

```bash
cd /opt/house-design
docker compose -f deploy/aws/docker-compose.aws.yml up -d --build
docker compose -f deploy/aws/docker-compose.aws.yml ps    # 两个都 healthy
curl -s http://127.0.0.1:8000/api/health                  # {"status":"ok",...}
```

## 六、nginx + TLS

```bash
sudo cp deploy/aws/nginx.conf.example /etc/nginx/sites-available/house-design
sudo nano /etc/nginx/sites-available/house-design   # 把 server_name 改成你的域名
sudo ln -s /etc/nginx/sites-available/house-design /etc/nginx/sites-enabled/
sudo nginx -t && sudo systemctl reload nginx
sudo certbot --nginx -d <你的域名>   # 免费证书，自动改写配置加 443 + http 跳 https
```

验证（浏览器/外网都能通）：
```bash
curl https://<域名>/api/health
curl https://<域名>/bridge/health
```

## 七、Vercel 环境变量

Vercel → Project Settings → Environment Variables，设：

```
NEXT_PUBLIC_AGENT_API_URL = https://<你的域名>     # 不加 /api，代码会自己拼
```

重新部署一次让变量生效。

## 八、验收

1. `curl https://<域名>/api/health` → `{"status":"ok",...}`
2. 打开 `https://<你的 Vercel 域名>/?render_bridge=https://<域名>/bridge`
   （页面即注册为渲染会话；标签页可最小化，Web Worker 会保持心跳）
3. `curl https://<域名>/bridge/v1/render-sessions/local-demo/status` → `"online":true`
4. 不带 token 调 `/api/chat` → 401（鉴权生效）
5. 让 Agent 走完整流程，确认 observe_room 拿到你浏览器截的图
6. 关掉标签页 → 90 秒后 agent 观察工具返回"渲染器未在线"（降级，不崩溃）——这是预期行为

## 九、日常使用

- **每次都要开一个标签页**当渲染器：打开上面的 Vercel 页面即可（别关）。
- 升级代码：本机改完 → `./deploy.sh` → 服务器上 `docker compose -f deploy/aws/docker-compose.aws.yml up -d --build`。
- 数据：`current_scheme.json` 和会话历史在 Docker 卷 `data` 里，重建容器不丢。

## 故障排查

| 现象 | 原因 | 处理 |
|---|---|---|
| `/api/chat` 401 | 没带 token | 请求带 `Authorization: Bearer <AGENT_API_TOKEN>` |
| 页面截图功能没反应 | 页面没带 `?render_bridge=` 或 bridge 未上线 | 重新用带参数的 URL 打开页面 |
| `online:false` | 标签页关了/浏览器休眠超 90s | 保持一个标签页开着 |
| 观察工具报"渲染器未在线" | 没有浏览器会话消费命令 | 同上一行；这是设计好的降级 |
| 混合内容被浏览器拦 | 用 http 访问 bridge | 确认全部走 `https://` |
