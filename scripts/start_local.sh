#!/usr/bin/env bash
# =====================================================================
# 本地开发服务启动脚本 (Git Bash / Windows)
#
#   用法:
#     scripts/start_local.sh [start]        幂等启动后端 + 前端 (默认)
#     scripts/start_local.sh status         打印两个服务的健康状态
#     scripts/start_local.sh stop           停止本脚本启动的进程
#     scripts/start_local.sh --open         start 后自动打开浏览器
#
#   环境变量:
#     PYTHON_BIN   指定带 uvicorn/langgraph 的 Python 解释器
#                  (默认自动探测 E:/python/python.exe)
#
#   说明:
#     - 幂等:已运行的服务会被跳过,不会重复启动。
#     - stop 只停止本脚本启动的进程(按 PID 文件),不会误杀他人启动的服务。
#     - 日志与 PID 落在 scripts/.run/ (已 gitignore)。
# =====================================================================
set -u

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
RUN_DIR="${RUN_DIR:-$ROOT/scripts/.run}"
LOG_BACKEND="$RUN_DIR/backend.log"
LOG_VIEWER="$RUN_DIR/viewer.log"
LOG_BRIDGE="$RUN_DIR/bridge.log"
PID_BACKEND="$RUN_DIR/backend.pid"
PID_VIEWER="$RUN_DIR/viewer.pid"
PID_BRIDGE="$RUN_DIR/bridge.pid"

BACKEND_HOST="${BACKEND_HOST:-127.0.0.1}"
BACKEND_PORT="${BACKEND_PORT:-8000}"
BRIDGE_HOST="${BRIDGE_HOST:-127.0.0.1}"
BRIDGE_PORT="${BRIDGE_PORT:-8765}"
VIEWER_HOST="${VIEWER_HOST:-127.0.0.1}"
VIEWER_PORT="${VIEWER_PORT:-3000}"
VIEWER_URL="http://localhost:$VIEWER_PORT/"

# ---- 选择 Python: 本机 E:/python 才有 langgraph,shell 默认 python 可能是空 venv ----
PYTHON_BIN="${PYTHON_BIN:-}"
if [ -z "$PYTHON_BIN" ]; then
  for cand in "E:/python/python.exe" "/e/python/python.exe"; do
    if [ -f "$cand" ]; then PYTHON_BIN="$cand"; break; fi
  done
fi
[ -z "$PYTHON_BIN" ] && PYTHON_BIN="python"

if ! "$PYTHON_BIN" -c "import uvicorn, langgraph" >/dev/null 2>&1; then
  echo "[错误] $PYTHON_BIN 缺少 uvicorn/langgraph。" >&2
  echo "       请用 PYTHON_BIN=/path/to/python 指向正确解释器。" >&2
  exit 1
fi

# ---- 工具函数 ----------------------------------------------------------
# curl -w 在连接失败时本身就会输出 000,别再 || echo 000(会拼成 000000 导致误判)
http_code() {
  local c
  c="$(curl -s -o /dev/null --max-time 3 -w '%{http_code}' "$1" 2>/dev/null)"
  [ -n "$c" ] || c=000
  echo "$c"
}

# 返回监听指定端口的 Windows PID(netstat 第 5 列);Git Bash 的 msys PID 与
# Windows PID 不是一回事,taskkill 必须用这里的 Windows PID。
port_pid() {
  netstat -ano 2>/dev/null | awk -v p="$1" '$1=="TCP" && $4=="LISTENING" && $2 ~ (":" p "$") { print $5 }'
}

# 任意一种回环绑定(127.0.0.1 / [::1])可达即视为服务在运行
is_up() { # 端口
  local p="$1" c1 c2
  c1="$(http_code "http://127.0.0.1:$p/")"
  c2="$(http_code "http://[::1]:$p/")"
  [ "$c1" != "000" ] || [ "$c2" != "000" ]
}

wait_up() { # 描述, 端口
  local desc="$1" p="$2" i
  for i in $(seq 1 60); do
    is_up "$p" && { echo "  ✓ $desc 已就绪"; return 0; }
    sleep 0.5
  done
  echo "  ✗ $desc 启动超时" >&2
  return 1
}

log_tail() { [ -f "$1" ] && tail -n 15 "$1" >&2 || true; }

# ---- 后端 Agent API ----------------------------------------------------
start_backend() {
  if is_up "$BACKEND_PORT"; then
    echo "后端 Agent API: 已在运行 (http://$BACKEND_HOST:$BACKEND_PORT/docs)"
    return 0
  fi
  mkdir -p "$RUN_DIR"
  echo "后端 Agent API: 启动中 (日志 $LOG_BACKEND)..."
  (
    cd "$ROOT" && \
    "$PYTHON_BIN" -m uvicorn backend.agent_api.main:app \
      --host "$BACKEND_HOST" --port "$BACKEND_PORT" \
      >>"$LOG_BACKEND" 2>&1 &
    echo $! > "$PID_BACKEND"
  )
  wait_up "后端" "$BACKEND_PORT" || { log_tail "$LOG_BACKEND"; return 1; }
  echo "  → http://$BACKEND_HOST:$BACKEND_PORT/docs"
}

# ---- 渲染桥 Render Bridge (observe_room / observe_home_harmony 依赖) ---------
start_bridge() {
  if is_up "$BRIDGE_PORT"; then
    echo "渲染桥 Render Bridge: 已在运行 (http://$BRIDGE_HOST:$BRIDGE_PORT/health)"
    return 0
  fi
  mkdir -p "$RUN_DIR"
  echo "渲染桥 Render Bridge: 启动中 (日志 $LOG_BRIDGE)..."
  (
    cd "$ROOT" && \
    "$PYTHON_BIN" -m uvicorn backend.render_bridge.main:app \
      --host "$BRIDGE_HOST" --port "$BRIDGE_PORT" \
      >>"$LOG_BRIDGE" 2>&1 &
    echo $! > "$PID_BRIDGE"
  )
  wait_up "渲染桥" "$BRIDGE_PORT" || { log_tail "$LOG_BRIDGE"; return 1; }
  echo "  → http://$BRIDGE_HOST:$BRIDGE_PORT/health"
}

# ---- 前端 Viewer -------------------------------------------------------
start_viewer() {
  if is_up "$VIEWER_PORT"; then
    echo "前端 Viewer:     已在运行 ($VIEWER_URL)"
    return 0
  fi
  mkdir -p "$RUN_DIR"
  echo "前端 Viewer: 启动中 (日志 $LOG_VIEWER)..."
  (
    cd "$ROOT/viewer" && \
    npm run dev -- --hostname "$VIEWER_HOST" --port "$VIEWER_PORT" \
      >>"$LOG_VIEWER" 2>&1 &
    echo $! > "$PID_VIEWER"
  )
  wait_up "前端" "$VIEWER_PORT" || { log_tail "$LOG_VIEWER"; return 1; }
  echo "  → $VIEWER_URL"
}

# ---- 停止 / 状态 -------------------------------------------------------
stop_one() { # pidfile, 名称, 端口
  local pf="$1" name="$2" port="$3" pid wpid
  if [ ! -f "$pf" ]; then
    echo "$name: 未记录 PID,跳过"
    return
  fi
  pid="$(cat "$pf")"
  if kill -0 "$pid" 2>/dev/null; then
    kill "$pid" 2>/dev/null && echo "已结束 $name (PID $pid)"
  else
    echo "$name: 记录的 PID $pid 已不在(可能已自行退出)"
  fi
  # 关键:msys PID 杀不掉 vinext 子进程,改按端口找 Windows 监听 PID 树杀
  for wpid in $(port_pid "$port"); do
    taskkill //F //T //PID "$wpid" >/dev/null 2>&1 && echo "  已停止 $name 端口 $port 监听 (WinPID $wpid)"
  done
  rm -f "$pf"
}

stop_all() {
  stop_one "$PID_VIEWER" "前端 Viewer" "$VIEWER_PORT"
  stop_one "$PID_BACKEND" "后端 Agent API" "$BACKEND_PORT"
  stop_one "$PID_BRIDGE" "渲染桥 Render Bridge" "$BRIDGE_PORT"
}

status() {
  local b
  b="$(http_code "http://$BACKEND_HOST:$BACKEND_PORT/docs")"
  [ "$b" = "000" ] && b="未运行" || b="运行中 (HTTP $b)"
  echo "后端 Agent API:  http://$BACKEND_HOST:$BACKEND_PORT/docs  $b"
  if is_up "$VIEWER_PORT"; then
    echo "前端 Viewer:      $VIEWER_URL  运行中"
  else
    echo "前端 Viewer:      $VIEWER_URL  未运行"
  fi
  if is_up "$BRIDGE_PORT"; then
    echo "渲染桥 Render Bridge: http://$BRIDGE_HOST:$BRIDGE_PORT/health  运行中"
  else
    echo "渲染桥 Render Bridge: 未运行"
  fi
}

open_browser() {
  cmd //c start "" "$VIEWER_URL" >/dev/null 2>&1 || true
}

# ---- 参数解析 ----------------------------------------------------------
ACTION="start"
OPEN=0
for a in "$@"; do
  case "$a" in
    --open) OPEN=1 ;;
    start|status|stop) ACTION="$a" ;;
    *) echo "未知参数: $a" >&2; exit 1 ;;
  esac
done

case "$ACTION" in
  start)
    start_backend || exit 1
    start_bridge || exit 1
    start_viewer || exit 1
    echo
    echo "✅ 本地服务已就绪:"
    echo "   前端页面: $VIEWER_URL  (对话助手 /chat)"
    echo "   后端文档: http://$BACKEND_HOST:$BACKEND_PORT/docs"
    echo "   渲染桥:   http://$BRIDGE_HOST:$BRIDGE_PORT/health"
    echo "   日志目录: $RUN_DIR"
    if [ "$OPEN" = "1" ]; then open_browser; fi
    exit 0
    ;;
  status) status ;;
  stop) stop_all ;;
esac
