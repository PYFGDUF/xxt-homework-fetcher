#!/bin/bash
# 定位具备所需依赖的 Python 解释器并启动 bridge.py（NDJSON 桥接进程）。
# SwiftUI 通过此脚本作为子进程，与 bridge.py 通过 stdin/stdout 通信。
set -u

APP_DIR="$(cd "$(dirname "$0")"  2>/dev/null && pwd)"
if [ ! -f "$APP_DIR/bridge.py" ]; then
    echo '[error] 找不到 bridge.py' >&2
    exit 1
fi
cd "$APP_DIR" || exit 1

# 桥接进程为无头（headless）脚本，优先选择 python3 而非 pythonw（pythonw 在 GUI 容器下可能挂起）
CANDIDATES=(
    "$HOME/opt/anaconda3/bin/python3"
    "$HOME/opt/anaconda3/bin/pythonw"
    "$HOME/opt/miniconda3/bin/python3"
    "$HOME/opt/miniconda3/bin/pythonw"
    "$HOME/anaconda3/bin/python3"
    "$HOME/anaconda3/bin/pythonw"
    "$HOME/miniconda3/bin/python3"
    "$HOME/miniconda3/bin/pythonw"
    "/opt/anaconda3/bin/python3"
    "/opt/anaconda3/bin/pythonw"
    "/opt/miniconda3/bin/python3"
    "/opt/miniconda3/bin/pythonw"
    "/usr/local/bin/python3"
    "/usr/bin/python3"
)

for conda_base in "$HOME/opt/anaconda3" "$HOME/opt/miniconda3" "$HOME/anaconda3" "$HOME/miniconda3" "/opt/anaconda3" "/opt/miniconda3"; do
    if [ -d "$conda_base/envs" ]; then
        for env_python in "$conda_base/envs"/*/bin/python3 "$conda_base/envs"/*/bin/pythonw; do
            [ -x "$env_python" ] && CANDIDATES+=("$env_python")
        done
    fi
done

for cmd in pythonw python3; do
    if command -v "$cmd" >/dev/null 2>&1; then
        CANDIDATES+=("$(command -v "$cmd")")
    fi
done

REQUIRED_MODULES="requests,PIL,docx,docxcompose,playwright"
PYTHON=""
for candidate in "${CANDIDATES[@]}"; do
    [ -z "$candidate" ] && continue
    [ -x "$candidate" ] || continue
    if "$candidate" -c "import requests, PIL, docx, docxcompose, playwright" >/dev/null 2>&1; then
        PYTHON="$candidate"
        break
    fi
done

if [ -z "$PYTHON" ]; then
    echo '[error] 未找到具备所需依赖的 Python 解释器' >&2
    exit 1
fi

PYTHON_BIN_DIR="$(dirname "$PYTHON")"
export PATH="$PYTHON_BIN_DIR:$PATH"
export PYTHONIOENCODING=utf-8

exec "$PYTHON" "$APP_DIR/bridge.py"