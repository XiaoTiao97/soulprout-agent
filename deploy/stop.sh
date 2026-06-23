#!/usr/bin/env bash
# deploy/stop.sh — 停止所有应用服务（Linux / macOS）
# 用法：bash deploy/stop.sh [--with-db]
#   --with-db  同时停止 MongoDB 和 Milvus（默认只停应用）
set -euo pipefail
source "$(dirname "$0")/lib/common.sh"

STOP_DB=false
for arg in "$@"; do
    [[ $arg == "--with-db" ]] && STOP_DB=true
done

echo -e "${BOLD}"
echo "╔══════════════════════════════════════╗"
echo "║   Soulprout Agent — 停止脚本         ║"
echo "╚══════════════════════════════════════╝"
echo -e "${RESET}"

# ── 应用进程（逆序停止）──────────────────────────────────────────
section "停止应用进程"
kill_service "web"
kill_service "gateway"
kill_service "agent"
kill_service "vdb"

# ── 数据库（可选）────────────────────────────────────────────────
if $STOP_DB; then
    section "停止数据库"

    MILVUS_SCRIPT="$MILVUS_DIR/standalone_embed.sh"
    if [[ -f "$MILVUS_SCRIPT" ]]; then
        info "停止 Milvus..."
        pushd "$MILVUS_DIR" > /dev/null
        bash standalone_embed.sh stop
        popd > /dev/null
        ok "Milvus 已停止"
    else
        warn "未找到 Milvus 脚本，跳过"
    fi

    if docker ps --format '{{.Names}}' | grep -qx "mongo"; then
        info "停止 MongoDB 容器..."
        docker stop mongo
        ok "MongoDB 已停止"
    else
        warn "MongoDB 容器未在运行，跳过"
    fi
else
    warn "数据库未停止（加 --with-db 可同时停止 MongoDB 和 Milvus）"
fi

echo ""
echo -e "${GREEN}${BOLD}✓ 完成。${RESET}"
echo ""
