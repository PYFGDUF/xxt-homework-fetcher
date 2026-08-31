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

# 引擎所配 Playwright 版本：直接从 requirements.txt 解析为单一事实来源
# （无需在此重复维护版本号）。该版本对应固定的 chromium revision，
# 升级时仍需同步修改 build_and_run.sh 内嵌的浏览器目录
# （chromium_headless_shell-<revision>），否则浏览器失配。
PW_PIN="$(sed -n 's/^playwright[[:space:]]*==[[:space:]]*//p' "$PROJECT_DIR/requirements.txt" | head -n1 | tr -d '[:space:]')"
if [ -z "$PW_PIN" ]; then
    echo "[error] 未能从 requirements.txt 解析出 playwright 版本（应形如 playwright==x.y.z）" >&2
    exit 1
fi

echo "==> 项目根: $PROJECT_DIR"
echo "==> playwright 版本（来自 requirements.txt）: $PW_PIN"

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
# 引擎只需 headless shell（内嵌版本），无需完整 Chromium——
# 加载完整 chromium 会在联网环境下多下载 160MiB+ 且网络不稳时反复重试导致构建卡死。
echo "==> 确保 Chromium headless shell 浏览器就位（网络缺失时可忽略此步）"
(cd "$PROJECT_DIR" && "$VENV_PY" -m playwright install chromium-headless-shell) || true

# ---- 4. 用 spec 打包引擎 ----
echo "==> PyInstaller 打包引擎 (engine_xxt.spec)"
(cd "$PROJECT_DIR" && "$VENV_PY" -m PyInstaller engine_xxt.spec \
    --distpath "$DIST" --workpath "$WORK" --noconfirm)

# ---- 4.1 交付瘦身：裁剪 babel 多余 locale 数据 ----
# babel（docxcompose 的依赖）自带的 locale-data 约 31M，本引擎合并路径并不使用
# （docxcompose 仅在 Composer.__init__ 构造 CustomProperties，不调用 update_all()，
#  合并的文档自身也不含 DOCPROPERTY 字段，实测删掉后合并单测全部通过）。
# 采取确定性删除（产物层面硬删，不受 PyInstaller 内部 datas 归并影响），
# 仅保留 root/en/zh 三个最小 locale 作为日期格式化兜底（约几百 KB）。
LOCALE_DIR="$DIST/engine_xxt/_internal/babel/locale-data"
if [ -d "$LOCALE_DIR" ]; then
    find "$LOCALE_DIR" -type f \
        ! -name 'root.dat' ! -name 'en.dat' ! -name 'zh.dat' \
        ! -name 'LICENSE.unicode' -delete
    find "$LOCALE_DIR" -type d -empty -delete
    echo "==> 已裁剪 babel 多余 locale 数据，剩余:"
    du -sh "$LOCALE_DIR"
fi

echo "==> 完成: $DIST/engine_xxt"
du -sh "$DIST/engine_xxt"
echo "  下一步: 运行 ./xxt-swift/script/build_and_run.sh 将新引擎内嵌进 App bundle"