#!/usr/bin/env bash
# Build shared Python venv + Node runtime for SaaS bash sandbox (bwrap).
# Usage: sudo bash deploy/sandbox.sh
set -euo pipefail

ROOT="${SAAS_SANDBOX_ROOT:-/opt/soulprout/sandbox}"
NODE_VERSION="${SAAS_NODE_VERSION:-v20.19.0}"
PY_PACKAGES=(
  requests
  httpx
  numpy
  pandas
  pillow
  openpyxl
  python-docx
)
NPM_PACKAGES=(
  lodash
  axios
  dayjs
)

log() { echo "[sandbox] $*"; }

detect_python() {
  if [[ -x /usr/local/python3.12/bin/python3.12 ]]; then
    echo /usr/local/python3.12/bin/python3.12
    return
  fi
  for py in python3.12 python3; do
    if command -v "$py" >/dev/null 2>&1; then
      command -v "$py"
      return
    fi
  done
  echo "error: no python3.12/python3 found" >&2
  exit 1
}

detect_arch() {
  case "$(uname -m)" in
    x86_64|amd64) echo "linux-x64" ;;
    aarch64|arm64) echo "linux-arm64" ;;
    *)
      echo "error: unsupported arch $(uname -m)" >&2
      exit 1
      ;;
  esac
}

setup_python() {
  local py
  py="$(detect_python)"
  log "Python: $py"
  mkdir -p "$ROOT"
  if [[ ! -x "$ROOT/python/bin/python" ]]; then
    log "Creating venv at $ROOT/python"
    "$py" -m venv "$ROOT/python"
  else
    log "venv already exists: $ROOT/python"
  fi
  # shellcheck disable=SC1091
  source "$ROOT/python/bin/activate"
  pip install --upgrade pip
  pip install "${PY_PACKAGES[@]}"
  deactivate || true
  log "Python shared packages installed"
}

setup_node() {
  local arch tarball url tmp
  arch="$(detect_arch)"
  tarball="node-${NODE_VERSION}-${arch}.tar.xz"
  url="https://nodejs.org/dist/${NODE_VERSION}/${tarball}"
  tmp="$(mktemp -d)"

  if [[ -x "$ROOT/node/bin/node" ]]; then
    log "Node already present: $($ROOT/node/bin/node -v)"
  else
    log "Downloading $url"
    curl -fsSL "$url" -o "$tmp/$tarball"
    mkdir -p "$ROOT"
    rm -rf "$ROOT/node"
    tar -xJf "$tmp/$tarball" -C "$tmp"
    mv "$tmp/node-${NODE_VERSION}-${arch}" "$ROOT/node"
    log "Node installed: $($ROOT/node/bin/node -v)"
  fi
  rm -rf "$tmp"

  export PATH="$ROOT/node/bin:$PATH"
  cd "$ROOT"
  if [[ ! -f package.json ]]; then
    cat > package.json <<'EOF'
{
  "name": "soulprout-sandbox-shared",
  "private": true,
  "version": "1.0.0"
}
EOF
  fi
  npm install --prefix "$ROOT" "${NPM_PACKAGES[@]}"
  log "Shared node_modules ready at $ROOT/node_modules"
}

main() {
  log "SAAS_SANDBOX_ROOT=$ROOT"
  setup_python
  setup_node
  log "Done."
  log "Verify with bwrap (example):"
  cat <<EOF
  bwrap \\
    --ro-bind /bin /bin --ro-bind /usr/bin /usr/bin \\
    --ro-bind /usr/lib /usr/lib --ro-bind /lib /lib --ro-bind /lib64 /lib64 \\
    --ro-bind /etc /etc --ro-bind /usr/share /usr/share \\
    --ro-bind /run/systemd/resolve /run/systemd/resolve \\
    --ro-bind $ROOT/python /opt/py --ro-bind $ROOT/node /opt/node \\
    --ro-bind $ROOT/node_modules /opt/node_modules \\
    --dev /dev --proc /proc --tmpfs /tmp --tmpfs /workspace \\
    --unshare-user --unshare-pid --unshare-ipc --unshare-uts \\
    --uid 65534 --gid 65534 --chdir /workspace --clearenv \\
    --setenv PATH /opt/node/bin:/opt/py/bin:/bin:/usr/bin \\
    --setenv PYTHONPATH /opt/py/lib/python3.12/site-packages \\
    --setenv NODE_PATH /opt/node_modules \\
    /bin/sh -c 'cat /etc/resolv.conf && python -c "import requests; print(requests.__version__)" && node -v'
EOF
}

main "$@"
