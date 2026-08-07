#!/usr/bin/env bash
# 本地打包 → 上传到 1GB VPS → 解压到 /opt/house-design。
#
# 用法：
#   ./deploy.sh <user>@<server-ip> [远程目录] [密钥文件]
#   # 或用环境变量指定密钥：
#   SSH_KEY="/path/to/key.pem" ./deploy.sh ubuntu@1.2.3.4
#
# 前置：本机已配置 SSH 登录（默认 ~/.ssh/id_*，或传入密钥文件）
# 本脚本只负责「传代码」，不启动服务 —— 启动前你要在服务器上填好 .env。

set -euo pipefail

SERVER="$1"
REMOTE_DIR="${2:-/opt/house-design}"
SSH_KEY="${3:-${SSH_KEY:-}}"

if [ -z "$SERVER" ]; then
  echo "用法: $0 <user>@<server-ip> [远程目录] [密钥文件]"
  exit 1
fi

SSH_OPTS=""
[ -n "$SSH_KEY" ] && SSH_OPTS="-i $SSH_KEY"
SSH() { ssh -o StrictHostKeyChecking=accept-new $SSH_OPTS "$SERVER" "$@"; }

# 项目根目录（脚本位于 deploy/aws/）
ROOT="$(cd "$(dirname "$0")/../.." && pwd)"
cd "$ROOT"

TARBALL="/tmp/house-design-deploy.tar.gz"
echo "==> 打包项目(排除 node_modules/output/blender/viewer 等大文件)…"
tar \
  --exclude='node_modules' \
  --exclude='output' \
  --exclude='blender' \
  --exclude='docs' \
  --exclude='scripts' \
  --exclude='tests' \
  --exclude='backend/tests' \
  --exclude='__pycache__' \
  --exclude='.pytest_cache' \
  --exclude='.git' \
  --exclude='*.log' \
  --exclude='.env' \
  --exclude='viewer/node_modules' \
  --exclude='viewer/dist' \
  --exclude='viewer/build' \
  --exclude='viewer/.next' \
  --exclude='viewer/db' \
  --exclude='viewer/dev.stderr.log' \
  --exclude='viewer/dev.stdout.log' \
  --exclude='viewer/public/models' \
  --exclude='viewer/public/assets' \
  -czf "$TARBALL" .

echo "==> 上传到 $SERVER …"
scp $SSH_OPTS "$TARBALL" "$SERVER:/tmp/house-design-deploy.tar.gz"

echo "==> 服务器端解压到 $REMOTE_DIR …"
SSH "
  set -e
  sudo mkdir -p '$REMOTE_DIR'
  sudo tar -xzf /tmp/house-design-deploy.tar.gz -C '$REMOTE_DIR'
  sudo rm -f /tmp/house-design-deploy.tar.gz
  if [ ! -f '$REMOTE_DIR/deploy/aws/.env' ]; then
    sudo cp '$REMOTE_DIR/deploy/aws/.env.example' '$REMOTE_DIR/deploy/aws/.env'
    echo '>>> 已生成 deploy/aws/.env，请先编辑它填好密钥再继续'
  fi
  echo '>>> 代码已就位: $REMOTE_DIR'
"

echo
echo "接下来在服务器上执行："
echo "  1) ssh $SERVER"
echo "  2) 编辑 deploy/aws/.env，填 OPENAI_API_KEY / CORS_ORIGINS(你的 Vercel 域名) / AGENT_API_TOKEN"
echo "  3) cd $REMOTE_DIR && docker compose -f deploy/aws/docker-compose.aws.yml up -d --build"
echo "  4) 配置 nginx + TLS（见 deploy/aws/nginx.conf.example 与 README.md）"
echo "  5) 验证: curl https://<你的域名>/api/health"
