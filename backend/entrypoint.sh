#!/bin/sh
# 单容器同时拉起三个进程(HuggingFace Spaces 等单容器 PaaS 用)。
# docker-compose 场景用三个 service 的 command,不经过本脚本。
set -e

echo "[entrypoint] starting agent-api :8000"
python -m uvicorn backend.agent_api.main:app --host 0.0.0.0 --port 8000 &

echo "[entrypoint] starting render-bridge :8765"
python -m uvicorn backend.render_bridge.main:app --host 0.0.0.0 --port 8765 &

echo "[entrypoint] starting render-worker"
python -m backend.render_worker.main &

trap 'kill 0' TERM INT
wait
