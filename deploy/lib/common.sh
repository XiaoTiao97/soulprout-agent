#!/usr/bin/env bash
# deploy/lib/common.sh — 公共函数库，不可直接执行

# ── 颜色 ────────────────────────────────────────────────────────
RED='\033[0;31m'; GREEN='\033[0;32m'; YELLOW='\033[1;33m'
CYAN='\033[0;36m'; BOLD='\033[1m'; RESET='\033[0m'

info()    { echo -e "${CYAN}[INFO]${RESET}  $*"; }
ok()      { echo -e "${GREEN}[OK]${RESET}    $*"; }
warn()    { echo -e "${YELLOW}[WARN]${RESET}  $*"; }
error()   { echo -e "${RED}[ERROR]${RESET} $*" >&2; }
die()     { error "$*"; exit 1; }
section() { echo -e "\n${BOLD}▶ $*${RESET}"; }

# ── 项目根目录（脚本所在 deploy/ 的上一级）──────────────────────
PROJECT_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
DEPLOY_DIR="$PROJECT_ROOT/deploy"
LOG_DIR="$PROJECT_ROOT/logs"
DATA_DIR="$DEPLOY_DIR/data"
MILVUS_DIR="$PROJECT_ROOT/vdb"

# ── 端口检测 ─────────────────────────────────────────────────────
port_open() {
    # port_open <port>   返回 0=开放 1=未开放
    nc -z 127.0.0.1 "$1" 2>/dev/null
}

wait_port() {
    # wait_port <port> <service_name> [timeout_secs=60]
    local port=$1 name=$2 timeout=${3:-60} elapsed=0
    info "等待 $name 就绪（:$port）..."
    while ! port_open "$port"; do
        sleep 2; elapsed=$((elapsed + 2))
        if [[ $elapsed -ge $timeout ]]; then
            die "$name 在 ${timeout}s 内未就绪（端口 $port），请检查 Docker 日志"
        fi
    done
    ok "$name 已就绪（:$port）"
}

# ── 检查依赖命令 ──────────────────────────────────────────────────
require_cmd() {
    command -v "$1" &>/dev/null || die "缺少依赖：$1。请先安装后重试。"
}

check_docker() {
    require_cmd docker
    docker info &>/dev/null || die "Docker daemon 未运行，请先启动 Docker。"
}

# ── Python ───────────────────────────────────────────────────────
PYTHON=""

resolve_python() {
    [[ -n "$PYTHON" ]] && return
    local py ver maj min
    for py in python3.12 python3.11 python3.10 python3 python; do
        if command -v "$py" &>/dev/null; then
            ver=$("$py" -c "import sys; print(f'{sys.version_info.major}.{sys.version_info.minor}')")
            IFS='.' read -r maj min <<< "$ver"
            if [[ $maj -eq 3 && $min -ge 10 ]]; then
                PYTHON="$py"
                return
            fi
        fi
    done
    die "未找到 Python 3.10+，请先安装：https://python.org"
}

# ── 进程 PID 文件 ──────────────────────────────────────────────────
PID_DIR="$DEPLOY_DIR/pids"
mkdir -p "$PID_DIR"

save_pid() { echo "$1" > "$PID_DIR/$2.pid"; }
read_pid() { cat "$PID_DIR/$1.pid" 2>/dev/null; }
clear_pid() { rm -f "$PID_DIR/$1.pid"; }

kill_service() {
    local name=$1
    local pid; pid=$(read_pid "$name")
    if [[ -n "$pid" ]] && kill -0 "$pid" 2>/dev/null; then
        kill "$pid" && ok "已停止 $name（pid=$pid）"
    else
        warn "$name 未在运行"
    fi
    clear_pid "$name"
}
