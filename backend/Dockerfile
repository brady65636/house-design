# Agent 后端镜像:一个镜像承载三个进程(agent-api / render-bridge / render-worker)。
# 构建上下文为项目根目录(需包含 backend/、scene_manifest.json、asset_manifest.json、
# asset_cards.json、design.md、skills/);前端资产由 VIEWER_URL(Vercel)提供,不进镜像。

FROM python:3.11-slim

WORKDIR /app

# 先装依赖再拷代码,利用层缓存
COPY backend/requirements.txt /app/backend/requirements.txt
RUN pip install --no-cache-dir -r /app/backend/requirements.txt \
    && python -m playwright install --with-deps chromium

ENV PLAYWRIGHT_BROWSERS_PATH=/ms-playwright \
    PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1

COPY . /app/

EXPOSE 8000 8765

# 默认启动 agent-api;docker-compose / PaaS 用 command 覆盖为 render-bridge / render-worker
CMD ["python", "-m", "uvicorn", "backend.agent_api.main:app", "--host", "0.0.0.0", "--port", "8000"]
