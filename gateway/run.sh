#!/usr/bin/env bash
# Soulprout Gateway — Linux 一键部署（配置 + 运行均在本文内完成）
#
# 用法：
#   bash gateway/run.sh          # 交互配置 → 询问是否后台启动（推荐）
#   bash gateway/run.sh start    # 仅后台启动（跳过配置）
#   bash gateway/run.sh stop     # 停止后台进程
#   bash gateway/run.sh status   # 查看运行状态
#
# 再次运行 bash gateway/run.sh 改配置时，会自动停掉当前进程后重新进入配置。
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT"

PID_FILE="${GATEWAY_PID_FILE:-$ROOT/gateway_data/gateway.pid}"
LOG_FILE="${GATEWAY_LOG_FILE:-$ROOT/gateway_data/gateway.log}"

install_deps() {
  python3 -m pip install -q -r gateway/requirements.txt
}

_pid_alive() {
  local pid="$1"
  kill -0 "$pid" 2>/dev/null
}

read_pid() {
  if [[ -f "$PID_FILE" ]]; then
    tr -d '[:space:]' < "$PID_FILE"
  fi
}

gateway_stop() {
  local pid
  pid="$(read_pid || true)"
  if [[ -n "${pid:-}" ]] && _pid_alive "$pid"; then
    echo "正在停止 Gateway (pid=$pid)…"
    kill -TERM "$pid" 2>/dev/null || true
    local i
    for i in $(seq 1 20); do
      if ! _pid_alive "$pid"; then
        break
      fi
      sleep 0.5
    done
    if _pid_alive "$pid"; then
      echo "进程未响应，强制结束…"
      kill -KILL "$pid" 2>/dev/null || true
    fi
    echo "Gateway 已停止。"
  elif [[ -n "${pid:-}" ]]; then
    echo "检测到陈旧 PID 文件，已清理。"
  fi
  rm -f "$PID_FILE"
}

gateway_status() {
  local pid
  pid="$(read_pid || true)"
  if [[ -n "${pid:-}" ]] && _pid_alive "$pid"; then
    echo "Gateway 运行中，pid=$pid"
    echo "日志：$LOG_FILE"
    return 0
  fi
  echo "Gateway 未在后台运行。"
  return 1
}

run_interactive_config() {
  install_deps
  echo ""
  echo "── 第一步：交互配置（邮箱登录、扫码绑定等）──"
  echo "配置完成后在菜单输入 0 退出。"
  echo ""
  python3 gateway/main.py --cli
}

gateway_start() {
  local pid
  pid="$(read_pid || true)"
  if [[ -n "${pid:-}" ]] && _pid_alive "$pid"; then
    echo "Gateway 已在运行 (pid=$pid)。"
    echo "若要修改配置，请再次运行: bash gateway/run.sh"
    exit 1
  fi
  rm -f "$PID_FILE"
  install_deps
  mkdir -p "$(dirname "$PID_FILE")"
  echo ""
  echo "── 第二步：后台启动 Gateway ──"
  nohup python3 gateway/main.py --daemon >> "$LOG_FILE" 2>&1 &
  pid=$!
  echo "$pid" > "$PID_FILE"
  sleep 0.5
  if _pid_alive "$pid"; then
    echo "Gateway 已在后台启动，pid=$pid"
    echo "日志：$LOG_FILE"
    echo "停止：bash gateway/run.sh stop"
    echo "改配置：bash gateway/run.sh（会自动停止当前进程）"
  else
    rm -f "$PID_FILE"
    echo "Gateway 启动失败，请查看日志：$LOG_FILE"
    exit 1
  fi
}

gateway_run() {
  if gateway_status >/dev/null 2>&1; then
    echo "检测到 Gateway 正在运行，将先停止再进入配置…"
    gateway_stop
  fi

  run_interactive_config

  echo ""
  local ans
  if ! read -r -p "是否立即在后台启动 Gateway？(Y/n) " ans; then
    echo ""
    echo "已跳过启动。稍后可运行: bash gateway/run.sh start"
    return 0
  fi
  if [[ "$ans" =~ ^([nN]|否)$ ]]; then
    echo ""
    echo "已跳过启动。稍后可运行: bash gateway/run.sh start"
    return 0
  fi

  gateway_start
}

usage() {
  cat <<EOF
Soulprout Gateway 部署脚本（配置与运行均在本文件内）

  bash gateway/run.sh          交互配置，完成后询问是否后台启动（推荐）
  bash gateway/run.sh start    仅后台启动（已有配置、跳过交互）
  bash gateway/run.sh stop     停止后台进程
  bash gateway/run.sh status   查看状态

改配置：再次运行 bash gateway/run.sh，会自动停掉旧进程后重新配置。
EOF
}

cmd="${1:-run}"
case "$cmd" in
  run|"")
    gateway_run
    ;;
  config)
    gateway_run
    ;;
  start)
    gateway_start
    ;;
  stop)
    gateway_stop
    ;;
  status)
    gateway_status
    ;;
  -h|--help|help)
    usage
    ;;
  *)
    echo "未知命令: $cmd"
    usage
    exit 1
    ;;
esac
