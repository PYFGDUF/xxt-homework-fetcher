#!/bin/bash
# 重新打包「自包含引擎」（PyInstaller），产出:
#   build/engine-pkg/dist/engine_xxt/   -- 包含 Python 运行时 + 全部依赖 + Playwright 驱动
# 该引擎随后由 xxt-swift/script/build_and_run.sh 连同 Chromium 浏览器一起内嵌进 App bundle，
# 使 App 不依赖本机 Python/浏览器，可分发到其他 Mac 离线运行。
#
# 用法: ./script/build_engine.sh
# 可选: PYTHON=/path/to/python3 指定用于创建虚拟环境的解释器（默认 anaconda python3 = Python 3.9）
set -euo pipefail

PROJECT_DIR="$(cd "$(dirname "$0")/.." && pwd)"   # xxt 项目根（bridge.py / core / spider / engine_xxt.spec 所在）
PYTHON_BIN="${PYTHON:-/Users/pengyufeng/opt/anaconda3/bin/python3}"
VENV_DIR="$PROJECT_DIR/build/engine-venv"
VENV_PY="$VENV_DIR/bin/python"
DIST="$PROJECT_DIR/build/engine-pkg/dist"
WORK="$PROJECT_DIR/build/engine-pkg/work"

# 引擎所配 Playwright 版本（其 browsers.json 对应 chromium revision 1223）。
# 必须与 build_and_run.sh 内嵌的浏览器目录保持一致；升/降版本后请同步两处。
PW_PIN="1.60.0"

echo "==> 项目根: $PROJECT_DIR"

# ---- 1. 准备干净虚拟环境 ----
if [ ! -x "$VENV_PY" ]; then
    if [ ! -x "$PYTHON_BIN" ]; then
        echo "[error] 未找到解释器: $PYTHON_BIN (可用 PYTHON=/path/to/python3 覆盖)" >&2
        exit 1
    fi
    echo "==> 创建虚拟环境: $VENV_DIR"
    "$PYTHON_BIN" -m venv "$VENV_DIR"
    "$VENV_PY" -m pip install --upgrade pip
else
    echo "==> 复用已有虚拟环境: $VENV_DIR"
fi

# ---- 2. 安装/对齐依赖（固定 playwright 版本，避免浏览器 revision 失配） ----
echo "==> 安装依赖 (requirements.txt + PyInstaller + playwright==${PW_PIN})"
"$VENV_PY" -m pip install -r "$PROJECT_DIR/requirements.txt" pyinstaller "playwright==${PW_PIN}"

# ---- 3. 确保对应 Playwright 的 Chromium 浏览器已就位 ----
# 默认装入 ~/Library/Caches/ms-playwright（build_and_run.sh 内嵌时也从这里读取）。
echo "==> 确保 Chromium 浏览器就位（网络缺失时可忽略此步）"
(cd "$PROJECT_DIR" && "$VENV_PY" -m playwright install chromium chromium-headless-shell) || true

# ---- 4. 用 spec 打包引擎 ----
echo "==> PyInstaller 打包引擎 (engine_xxt.spec)"
(cd "$PROJECT_DIR" && "$VENV_PY" -m PyInstaller engine_xxt.spec \
    --distpath "$DIST" --workpath "$WORK" --noconfirm)

echo "==> 完成: $DIST/engine_xxt"
du -sh "$DIST/engine_xxt"
echo "  下一步: 运行 ./xxt-swift/script/build_and_run.sh 将新引擎内嵌进 App bundle"