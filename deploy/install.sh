#!/usr/bin/env bash
# deploy/install.sh — 首次安装脚本（Linux / macOS）
# 用法：bash deploy/install.sh [--skip-docker] [--skip-python] [--skip-node]
set -euo pipefail
# shellcheck source=lib/common.sh
source "$(dirname "$0")/lib/common.sh"

# ── 参数 ──────────────────────────────────────────────────────────
SKIP_DOCKER=false; SKIP_PYTHON=false; SKIP_NODE=false
for arg in "$@"; do
    case $arg in
        --skip-docker) SKIP_DOCKER=true ;;
        --skip-python) SKIP_PYTHON=true ;;
        --skip-node)   SKIP_NODE=true ;;
    esac
done

echo -e "${BOLD}"
echo "╔══════════════════════════════════════╗"
echo "║   Soulprout Agent — 环境安装脚本     ║"
echo "╚══════════════════════════════════════╝"
echo -e "${RESET}"

# ────────────────────────────────────────────────────────────────
# Step 1  检查基础依赖
# ────────────────────────────────────────────────────────────────
section "Step 1 · 检查基础依赖"

require_cmd curl
require_cmd git

# Python
PY_BIN=""
for py in python3.12 python3.11 python3.10 python3 python; do
    if command -v "$py" &>/dev/null; then
        PY_VER=$("$py" -c "import sys; print(f'{sys.version_info.major}.{sys.version_info.minor}')")
        IFS='.' read -r MAJ MIN <<< "$PY_VER"
        if [[ $MAJ -eq 3 && $MIN -ge 10 ]]; then
            PY_BIN="$py"; break
        fi
    fi
done
[[ -z "$PY_BIN" ]] && die "未找到 Python 3.10+，请先安装：https://python.org"
ok "Python: $($PY_BIN --version)"

# Node
if ! command -v node &>/dev/null; then
    die "未找到 Node.js，请先安装 18+：https://nodejs.org"
fi
NODE_VER=$(node -e "process.stdout.write(process.versions.node)")
NODE_MAJ="${NODE_VER%%.*}"
[[ $NODE_MAJ -lt 18 ]] && die "Node.js 版本过低（当前 $NODE_VER），需要 18+"
ok "Node.js: v$NODE_VER"
require_cmd npm

# ────────────────────────────────────────────────────────────────
# Step 2  Docker + 基础设施镜像
# ────────────────────────────────────────────────────────────────
section "Step 2 · Docker 基础设施"

if $SKIP_DOCKER; then
    warn "跳过 Docker 步骤（--skip-docker）"
else
    check_docker

    # 2-a  MongoDB
    info "拉取 MongoDB 镜像（mongo:latest）..."
    docker pull mongo:latest
    ok "MongoDB 镜像就绪"

    # 2-b  创建 Mongo 数据目录
    MONGO_DATA="$DATA_DIR/mongo/data"
    mkdir -p "$MONGO_DATA"
    ok "Mongo 数据目录：$MONGO_DATA"

    # 2-c  检查 Milvus standalone 脚本
    MILVUS_SCRIPT="$MILVUS_DIR/standalone_embed.sh"
    if [[ -f "$MILVUS_SCRIPT" ]]; then
        ok "Milvus 脚本就绪：$MILVUS_SCRIPT"
    else
        die "未找到 vdb/standalone_embed.sh，请确认文件已放置在 vdb/ 目录下"
    fi
fi

# ────────────────────────────────────────────────────────────────
# Step 3  Python 虚拟环境 & 依赖
# ────────────────────────────────────────────────────────────────
section "Step 3 · Python 依赖"

if $SKIP_PYTHON; then
    warn "跳过 Python 安装（--skip-python）"
else
    # 创建 / 复用 venv
    if [[ ! -d "$VENV_DIR" ]]; then
        info "创建虚拟环境 (.venv)..."
        "$PY_BIN" -m venv "$VENV_DIR"
        ok "虚拟环境已创建：$VENV_DIR"
    else
        ok "复用已有虚拟环境：$VENV_DIR"
    fi

    source "$VENV_DIR/bin/activate"
    pip install --upgrade pip -q

    info "安装 agent 依赖..."
    pip install -r "$PROJECT_ROOT/agent/requirements.txt" -q
    ok "agent 依赖安装完成"

    info "安装 vdb 依赖..."
    pip install -r "$PROJECT_ROOT/vdb/requirements.txt" -q
    ok "vdb 依赖安装完成"

    if [[ -f "$PROJECT_ROOT/gateway/requirements.txt" ]]; then
        info "安装 gateway 依赖..."
        pip install -r "$PROJECT_ROOT/gateway/requirements.txt" -q
        ok "gateway 依赖安装完成"
    fi
fi

# ────────────────────────────────────────────────────────────────
# Step 4  Web 前端依赖
# ────────────────────────────────────────────────────────────────
section "Step 4 · Web 前端依赖"

if $SKIP_NODE; then
    warn "跳过 npm install（--skip-node）"
else
    info "npm install（web/）..."
    npm install --prefix "$PROJECT_ROOT/web" --silent
    ok "Web 前端依赖安装完成"
fi

# ────────────────────────────────────────────────────────────────
# Step 5  配置文件初始化（仅复制模板，已存在则跳过）
# ────────────────────────────────────────────────────────────────
section "Step 5 · 初始化配置文件"

copy_if_missing() {
    local src=$1 dst=$2
    if [[ -f "$dst" ]]; then
        warn "已存在，跳过：$dst"
    else
        cp "$src" "$dst"
        ok "已生成：$dst（请按需填写密钥）"
    fi
}

copy_if_missing "$PROJECT_ROOT/agent/.env.example"          "$PROJECT_ROOT/agent/.env"
copy_if_missing "$PROJECT_ROOT/agent/.model.json.example"   "$PROJECT_ROOT/agent/.model.json"
copy_if_missing "$PROJECT_ROOT/vdb/.env.example"            "$PROJECT_ROOT/vdb/.env"
if [[ -f "$PROJECT_ROOT/gateway/.env.example" ]]; then
    copy_if_missing "$PROJECT_ROOT/gateway/.env.example"    "$PROJECT_ROOT/gateway/.env"
fi

# 创建日志目录
mkdir -p "$LOG_DIR"

# ────────────────────────────────────────────────────────────────
# 完成
# ────────────────────────────────────────────────────────────────
echo ""
echo -e "${GREEN}${BOLD}✓ 安装完成！${RESET}"
echo ""
echo -e "  ${BOLD}接下来请完成以下配置（必须）：${RESET}"
echo ""
echo -e "  1. 编辑  ${CYAN}agent/.env${RESET}          填写 API 密钥（DashScope、ZAI_KEY 等）"
echo -e "  2. 编辑  ${CYAN}agent/.model.json${RESET}   填写大模型 API Key"
echo -e "  3. 编辑  ${CYAN}vdb/.env${RESET}            填写 DashScope embedding key"
echo ""
echo -e "  配置完成后，运行："
echo -e "  ${BOLD}  bash deploy/start.sh${RESET}"
echo ""
