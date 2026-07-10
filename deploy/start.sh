#!/usr/bin/env bash
# deploy/start.sh — 一键启动所有服务（Linux / macOS）
# 用法：bash deploy/start.sh [--no-gateway] [--no-web]
set -euo pipefail
source "$(dirname "$0")/lib/common.sh"

START_GATEWAY=true; START_WEB=true
for arg in "$@"; do
    case $arg in
        --no-gateway) START_GATEWAY=false ;;
        --no-web)     START_WEB=false ;;
    esac
done

echo -e "${BOLD}"
echo "╔══════════════════════════════════════╗"
echo "║   Soulprout Agent — 启动脚本         ║"
echo "╚══════════════════════════════════════╝"
echo -e "${RESET}"

resolve_python
mkdir -p "$LOG_DIR" "$PID_DIR"

# ── Step 1: MongoDB ───────────────────────────────────────────────
section "Step 1 · MongoDB"
check_docker

MONGO_DATA="$DATA_DIR/mongo/data"
mkdir -p "$MONGO_DATA"

if docker ps --format '{{.Names}}' | grep -qx "mongo"; then
    ok "MongoDB 容器已在运行"
elif docker ps -a --format '{{.Names}}' | grep -qx "mongo"; then
    info "启动已有 MongoDB 容器..."
    docker start mongo
else
    info "创建并启动 MongoDB 容器..."
    docker run -d \
        --name mongo \
        --restart unless-stopped \
        -v "$MONGO_DATA:/data/db" \
        -p 127.0.0.1:27017:27017 \
        mongo:latest
    ok "MongoDB 容器已创建"
fi
wait_port 27017 "MongoDB" 60

# ── Step 2: Milvus ────────────────────────────────────────────────
section "Step 2 · Milvus"

mkdir -p \
    "$MILVUS_VOLUME_DIR/volumes/etcd" \
    "$MILVUS_VOLUME_DIR/volumes/minio" \
    "$MILVUS_VOLUME_DIR/volumes/milvus"

# 清理旧版单容器（若存在且不是 compose 管理的）
if docker ps -a --format '{{.Names}}' | grep -qx "milvus-standalone"; then
    # compose 管理的容器会带 com.docker.compose.project 标签
    if ! docker inspect -f '{{index .Config.Labels "com.docker.compose.project"}}' milvus-standalone 2>/dev/null | grep -q .; then
        warn "检测到旧版单容器 milvus-standalone，正在移除以便改用 compose..."
        docker rm -f milvus-standalone >/dev/null 2>&1 || true
    fi
fi

if docker ps --format '{{.Names}}' | grep -qx "milvus-standalone" \
    && port_open 19530; then
    ok "Milvus 已在运行（:19530）"
else
    info "启动 Milvus（etcd + minio + milvus）..."
    milvus_compose up -d
fi
wait_port 19530 "Milvus" 180

# ── Step 3: vdb ───────────────────────────────────────────────────
section "Step 3 · VDB 服务"

if port_open 8888; then
    ok "vdb 已在运行（:8888）"
else
    info "启动 vdb（端口 8888）..."
    nohup "$PYTHON" "$PROJECT_ROOT/vdb/main.py" \
        > "$LOG_DIR/vdb.log" 2>&1 &
    save_pid $! "vdb"
    wait_port 8888 "vdb" 30
fi

# ── Step 4: agent ─────────────────────────────────────────────────
section "Step 4 · Agent 服务"
if port_open 8080; then
    ok "agent 已在运行（:8080）"
else
    info "启动 agent（端口 8080）..."
    nohup "$PYTHON" "$PROJECT_ROOT/agent/main.py" \
        > "$LOG_DIR/agent.log" 2>&1 &
    save_pid $! "agent"
    wait_port 8080 "agent" 60
fi

# ── Step 5: gateway（可选）────────────────────────────────────────
if $START_GATEWAY; then
    section "Step 5 · Gateway"
    if port_open 8082; then
        ok "gateway 已在运行（:8082）"
    else
        info "启动 gateway（端口 8082）..."
        nohup "$PYTHON" "$PROJECT_ROOT/gateway/main.py" \
            > "$LOG_DIR/gateway.log" 2>&1 &
        save_pid $! "gateway"
        wait_port 8082 "gateway" 30
    fi
else
    warn "跳过 gateway（--no-gateway）"
fi

# ── Step 6: Web 前端（Vite dev）───────────────────────────────────
if $START_WEB; then
    section "Step 6 · Web 前端"
    if port_open 5173; then
        ok "Web 前端已在运行（:5173）"
    else
        info "启动 Web 前端（端口 5173）..."
        nohup npm run dev --prefix "$PROJECT_ROOT/web" \
            > "$LOG_DIR/web.log" 2>&1 &
        save_pid $! "web"
        wait_port 5173 "Web" 30
    fi
else
    warn "跳过 Web 前端（--no-web）"
fi

# ── 完成 ──────────────────────────────────────────────────────────
echo ""
echo -e "${GREEN}${BOLD}✓ 所有服务已启动！${RESET}"
echo ""
echo -e "  ${BOLD}访问地址：${RESET}"
echo -e "  Web 前端   →  ${CYAN}http://localhost:5173${RESET}"
echo -e "  Agent API  →  ${CYAN}http://localhost:8080${RESET}"
echo -e "  VDB 服务   →  ${CYAN}http://localhost:8888${RESET}"
$START_GATEWAY && echo -e "  Gateway    →  ${CYAN}http://localhost:8082${RESET}"
echo ""
echo -e "  日志目录：${CYAN}$LOG_DIR/${RESET}"
echo -e "  停止所有服务：${BOLD}bash deploy/stop.sh${RESET}"
echo ""
