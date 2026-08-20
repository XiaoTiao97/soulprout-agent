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
MILVUS_COMPOSE_DIR="$DEPLOY_DIR/milvus"
MILVUS_VOLUME_DIR="$DATA_DIR/milvus"

# ── 端口检测 ─────────────────────────────────────────────────────
port_open() {
    # port_open <port>   返回 0=开放 1=未开放
    local port=$1
    if command -v nc &>/dev/null; then
        # -w 1：避免无监听时 nc 卡住（部分发行版 nc -z 无超时）
        nc -z -w 1 127.0.0.1 "$port" >/dev/null 2>&1 || return 1
        return 0
    fi
    # bash 内置探测，不依赖 nc
    (echo >/dev/tcp/127.0.0.1/"$port") >/dev/null 2>&1 || return 1
    return 0
}

dump_log() {
    local f=$1
    if [[ -f "$f" ]]; then
        error "日志 $f 最后 40 行："
        tail -n 40 "$f" | sed 's/^/        /' >&2 || true
    else
        error "日志文件不存在：$f"
    fi
}

wait_port() {
    # wait_port <port> <service_name> [timeout_secs=60] [logfile]
    local port=$1 name=$2 timeout=${3:-60} logfile=${4:-} elapsed=0 pid
    info "等待 $name 就绪（:$port）..."
    while ! port_open "$port"; do
        pid=$(read_pid "$name" 2>/dev/null || true)
        if [[ -n "$pid" ]] && ! kill -0 "$pid" 2>/dev/null; then
            error "$name 进程已退出（pid=$pid），端口 $port 不会再就绪"
            [[ -n "$logfile" ]] && dump_log "$logfile"
            die "请根据上方日志排查（常见原因：选错 Python、缺少依赖、.env 未加载）"
        fi
        sleep 2; elapsed=$((elapsed + 2))
        if [[ $elapsed -ge $timeout ]]; then
            [[ -n "$logfile" ]] && dump_log "$logfile"
            die "$name 在 ${timeout}s 内未就绪（端口 $port），请查看 ${logfile:-日志}"
        fi
    done
    ok "$name 已就绪（:$port）"
}

# 后台启动本地 Python 服务（工作目录固定为仓库根，保证能 import 顶层包）
start_python_svc() {
    # start_python_svc <name> <port> <timeout> <script_path>
    local name=$1 port=$2 timeout=$3 script=$4
    local logfile="$LOG_DIR/$name.log" pid

    if port_open "$port"; then
        warn "$name 端口 $port 仍被占用，先释放再启动，确保加载 git 上的新代码"
        kill_port_listeners "$port"
        if port_open "$port"; then
            die "$name 端口 $port 无法释放，请手动查看：ss -lptn sport = :$port"
        fi
    fi

    info "启动 $name（端口 $port，Python: $PYTHON）..."
    (
        cd "$PROJECT_ROOT"
        export PYTHONPATH="$PROJECT_ROOT${PYTHONPATH:+:$PYTHONPATH}"
        nohup "$PYTHON" "$script" > "$logfile" 2>&1 &
        echo $! > "$PID_DIR/$name.pid"
    )
    pid=$(read_pid "$name")
    sleep 1
    if ! kill -0 "$pid" 2>/dev/null; then
        error "$name 进程启动后立即退出（pid=$pid）"
        dump_log "$logfile"
        die "请根据上方日志排查（常见原因：选错 Python、缺少依赖、.env 未加载）"
    fi
    wait_port "$port" "$name" "$timeout" "$logfile"
}

# ── 检查依赖命令 ──────────────────────────────────────────────────
require_cmd() {
    command -v "$1" &>/dev/null || die "缺少依赖：$1。请先安装后重试。"
}

check_docker() {
    require_cmd docker
    docker info &>/dev/null || die "Docker daemon 未运行，请先启动 Docker。"
}

# 兼容 docker compose 插件与旧版 docker-compose
docker_compose() {
    if docker compose version &>/dev/null; then
        docker compose "$@"
    elif command -v docker-compose &>/dev/null; then
        docker-compose "$@"
    else
        die "缺少 docker compose，请安装 Docker Compose 插件后重试。"
    fi
}

# Milvus compose 封装（etcd + minio + milvus）
milvus_compose() {
    [[ -f "$MILVUS_COMPOSE_DIR/docker-compose.yml" ]] \
        || die "未找到 $MILVUS_COMPOSE_DIR/docker-compose.yml"
    export DOCKER_VOLUME_DIRECTORY="$MILVUS_VOLUME_DIR"
    docker_compose \
        -f "$MILVUS_COMPOSE_DIR/docker-compose.yml" \
        --project-directory "$MILVUS_COMPOSE_DIR" \
        "$@"
}

# 准备 Milvus 数据目录：容器内进程通常非 root，主机目录必须可写
# 否则会 FATAL: mkdir /var/lib/milvus/data/: permission denied，19530 无法对外服务
prepare_milvus_volumes() {
    mkdir -p \
        "$MILVUS_VOLUME_DIR/volumes/etcd" \
        "$MILVUS_VOLUME_DIR/volumes/minio" \
        "$MILVUS_VOLUME_DIR/volumes/milvus/data"
    # 官方常见做法：放宽 volumes 写权限，避免容器内非 root 用户无法建目录
    chmod -R a+rwX "$MILVUS_VOLUME_DIR/volumes" 2>/dev/null || true
}

# ── Python ───────────────────────────────────────────────────────
PYTHON=""

_python_candidates() {
    [[ -x "$PROJECT_ROOT/.venv/bin/python" ]] && echo "$PROJECT_ROOT/.venv/bin/python"
    [[ -n "${VIRTUAL_ENV:-}" && -x "$VIRTUAL_ENV/bin/python" ]] && echo "$VIRTUAL_ENV/bin/python"
    # `python` 放在 python3.10 之前：Ubuntu 上 python3.10 几乎总存在，
    # 但用户手动 `python main.py` 跑通的往往是 3.12，NumPy ABI 也对 3.12。
    echo python3.12
    echo python3.11
    echo python
    echo python3
    echo python3.10
}

python_has_runtime_deps() {
    "$1" -c "import numpy, pymilvus, fastapi, uvicorn, dotenv" >/dev/null 2>&1
}

resolve_python() {
    # resolve_python [--runtime]
    # --runtime：启动服务用，必须能 import numpy/pymilvus（避开 3.10 解释器 + 3.12 NumPy 混装）
    local require_runtime=false py ver maj min first_ok=""
    [[ "${1:-}" == "--runtime" ]] && require_runtime=true
    [[ -n "$PYTHON" ]] && return

    while IFS= read -r py; do
        [[ -z "$py" ]] && continue
        if command -v "$py" &>/dev/null || [[ -x "$py" ]]; then
            ver=$("$py" -c "import sys; print(f'{sys.version_info.major}.{sys.version_info.minor}')" 2>/dev/null) || continue
            IFS='.' read -r maj min <<< "$ver"
            if [[ $maj -eq 3 && $min -ge 10 ]]; then
                [[ -z "$first_ok" ]] && first_ok="$py"
                if $require_runtime; then
                    if python_has_runtime_deps "$py"; then
                        PYTHON="$py"
                        return
                    fi
                    warn "跳过 $py（Python $ver）：numpy/pymilvus 不可用"
                else
                    PYTHON="$py"
                    return
                fi
            fi
        fi
    done < <(_python_candidates)

    if $require_runtime && [[ -n "$first_ok" ]]; then
        die "找到 $first_ok，但无法 import numpy/pymilvus（常见原因：系统混装了 3.10 与 3.12 的 NumPy）。
请创建独立虚拟环境：
  $first_ok -m venv $PROJECT_ROOT/.venv
  $PROJECT_ROOT/.venv/bin/pip install -r $PROJECT_ROOT/vdb/requirements.txt -r $PROJECT_ROOT/agent/requirements.txt -r $PROJECT_ROOT/gateway/requirements.txt
或执行：bash deploy/install.sh"
    fi
    die "未找到 Python 3.10+，请先安装：https://python.org"
}

# 把依赖装进项目 .venv，避免写入 /usr/lib/python3/dist-packages 导致 ABI 冲突
ensure_project_venv() {
    local bootstrap="$PYTHON"
    local venv_py="$PROJECT_ROOT/.venv/bin/python"
    if [[ ! -x "$venv_py" ]]; then
        info "创建项目虚拟环境 .venv ..."
        if ! "$bootstrap" -m venv "$PROJECT_ROOT/.venv"; then
            warn "创建 venv 失败（可能缺少 python3-venv 包），将安装到 $bootstrap"
            return 0
        fi
        ok "已创建 $PROJECT_ROOT/.venv"
    fi
    PYTHON="$venv_py"
}

# ── 进程 PID 文件 ──────────────────────────────────────────────────
PID_DIR="$DEPLOY_DIR/pids"
mkdir -p "$PID_DIR"

save_pid() { echo "$1" > "$PID_DIR/$2.pid"; }
read_pid() { cat "$PID_DIR/$1.pid" 2>/dev/null; }
clear_pid() { rm -f "$PID_DIR/$1.pid"; }

kill_port_listeners() {
    # 释放占用该端口的监听进程，避免 stop 只杀了过期 pid、旧进程仍占着端口。
    local port=$1
    local pids=""
    if command -v fuser &>/dev/null; then
        fuser -k "${port}/tcp" >/dev/null 2>&1 || true
    elif command -v lsof &>/dev/null; then
        pids=$(lsof -ti tcp:"$port" -sTCP:LISTEN 2>/dev/null || true)
        [[ -n "$pids" ]] && kill $pids 2>/dev/null || true
    elif command -v ss &>/dev/null; then
        pids=$(ss -lptn "sport = :$port" 2>/dev/null | sed -n 's/.*pid=\([0-9]\+\).*/\1/p' | sort -u)
        [[ -n "$pids" ]] && kill $pids 2>/dev/null || true
    fi
    local i=0
    while port_open "$port" && [[ $i -lt 20 ]]; do
        sleep 0.5
        i=$((i + 1))
    done
}

kill_service() {
    local name=$1
    local port=${2:-}
    local pid; pid=$(read_pid "$name")
    if [[ -n "$pid" ]] && kill -0 "$pid" 2>/dev/null; then
        kill "$pid" && ok "已停止 $name（pid=$pid）"
        sleep 0.5
        if kill -0 "$pid" 2>/dev/null; then
            kill -9 "$pid" 2>/dev/null || true
        fi
    else
        warn "$name pid 文件不存在或进程已退出"
    fi
    clear_pid "$name"
    if [[ -n "$port" ]]; then
        if port_open "$port"; then
            warn "$name 端口 $port 仍被占用，强制释放以保证加载新代码"
            kill_port_listeners "$port"
        fi
        if port_open "$port"; then
            error "$name 端口 $port 仍未释放，start 可能会跳过或复用旧进程"
        fi
    fi
}
