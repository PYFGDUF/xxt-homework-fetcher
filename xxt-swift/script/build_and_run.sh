#!/bin/bash
# 构建并运行 XxtApp（SwiftPM GUI）。
# 用法: ./script/build_and_run.sh [--verify]
set -eu

PROJECT_DIR="$(cd "$(dirname "$0")/.." && pwd)"
APP_NAME="XxtApp"
DIST_DIR="$PROJECT_DIR/dist"
APP_BUNDLE="$DIST_DIR/$APP_NAME.app"
# 全局可覆盖：调用方显式指定 DEVELOPER_DIR 时优先采用，否则自动探测。
# 自动探测规则：优先选择带 SwiftUIMacros 插件的“完整 Xcode”工具链
# （CommandLineTools 缺少该插件，编译 @State/@Observable 宏直接失败）；
# 找不到完整 Xcode 时才回退到 xcode-select -p。
detect_developer_dir() {
    if [ -n "${DEVELOPER_DIR:-}" ]; then
        echo "$DEVELOPER_DIR"
        return
    fi
    local candidate d
    for candidate in /Applications/Xcode-beta.app /Applications/Xcode.app; do
        d="$candidate/Contents/Developer"
        if [ -x "$d/Toolchains/XcodeDefault.xctoolchain/usr/bin/swift" ] \
           && find "$d" -name 'libSwiftUIMacros.dylib' 2>/dev/null | grep -q .; then
            echo "$d"
            return
        fi
    done
    /usr/bin/xcode-select -p
}
DEVELOPER_DIR="$(detect_developer_dir)"

# 让本脚本内部的 swift 命令统一落到所选工具链
TOOLCHAIN_BIN="$DEVELOPER_DIR/Toolchains/XcodeDefault.xctoolchain/usr/bin"
if [ -d "$TOOLCHAIN_BIN" ] && [[ ":$PATH:" != *":$TOOLCHAIN_BIN:"* ]]; then
    export PATH="$TOOLCHAIN_BIN:$PATH"
fi

echo "==> build $APP_NAME, DEVELOPER_DIR=$DEVELOPER_DIR"
cd "$PROJECT_DIR"
DEVELOPER_DIR="$DEVELOPER_DIR" swift build -c debug --disable-sandbox

BIN_PATH="$(DEVELOPER_DIR="$DEVELOPER_DIR" swift build -c debug --disable-sandbox --show-bin-path)/$APP_NAME"

# ---- 应用图标 ----
# 从仓库根目录 icon.png 生成 .icns。图标内容纳入指纹：图标变更会触发重新组装。
ICON_SRC="$PROJECT_DIR/../icon.png"
ICONSET_DIR="$DIST_DIR/.AppIcon.iconset"
ICONSET_FILE="$DIST_DIR/AppIcon.icns"
build_icns() {
    rm -rf "$ICONSET_DIR"
    mkdir -p "$ICONSET_DIR"
    # 生成 .iconset 所需的标准尺寸（boxed-spec 格式）
    for spec in "16:16" "32:32" "128:128" "256:256" "512:512"; do
        s="${spec%%:*}"
        base="${spec##*:}"
        /usr/bin/sips -z "$s" "$s" "$ICON_SRC" --out "$ICONSET_DIR/icon_${base}x${base}.png" >/dev/null
        d=$((s * 2))
        /usr/bin/sips -z "$d" "$d" "$ICON_SRC" --out "$ICONSET_DIR/icon_${base}x${base}@2x.png" >/dev/null
    done
    /usr/bin/iconutil -c icns "$ICONSET_DIR" -o "$ICONSET_FILE"
}
if [ -f "$ICON_SRC" ]; then
    build_icns
fi

# 让 macOS 的文件访问（TCC）授权“只授权一次”。
# 原理：TCC 授权是绑定代码签名 cdhash 的；每次 ad-hoc 重新签名都会让系统
# 认为应用是“全新的”而重新弹授权框。安装进 .app 的二进制因被签名改造，
# 不能与原始构建产物直接 cmp，因此这里对“原始构建产物”做指纹比对：
# 只要本次构建产物与上次已安装时的指纹一致，就保留现有签名、跳过重新组装/重签。
FINGERPRINT_FILE="$DIST_DIR/.XxtApp-content.fingerprint"
BIN_FP="$(shasum -a 256 "$BIN_PATH" | awk '{print $1}')"
ICON_FP=""
if [ -f "$ICONSET_FILE" ]; then
    ICON_FP="$(shasum -a 256 "$ICONSET_FILE" | awk '{print $1}')"
fi
# 引擎 + 内置浏览器纳入指纹。自包含引擎（PyInstaller 二进制）与 ms-playwright 浏览器是
# 打进 .app 的运行时资源；若不纳入指纹，仅更换引擎/浏览器时二进制未变会导致 SKIP_ASSEMBLE
# 跳过重新组装/重签，分发到其他 Mac 后因缺浏览器而无法抓取。
# 用“引擎可执行哈希 + 各浏览器目录修改时间”作为轻量但可靠的资源指纹。
ENGINE_SRC_ROOT="$PROJECT_DIR/../build/engine-pkg/dist/engine_xxt"
ENGINE_FP=""
if [ -x "$ENGINE_SRC_ROOT/engine_xxt" ]; then
    ENGINE_MARKER="$(shasum -a 256 "$ENGINE_SRC_ROOT/engine_xxt" | awk '{print $1}')"
    MS_MARKER=""
    for b in chromium_headless_shell-1223 ffmpeg-1011; do
        d="$HOME/Library/Caches/ms-playwright/$b"
        if [ -d "$d" ]; then
            MS_MARKER="${MS_MARKER}${b}:$(stat -f %m "$d");"
        fi
    done
    ENGINE_FP="${ENGINE_MARKER}${MS_MARKER}"
fi
# 二进制 + 图标 + 引擎/浏览器 合并指纹；任一发生变化都会触发重新组装/重签
NEW_FP="${BIN_FP}${ICON_FP}${ENGINE_FP}"

SKIP_ASSEMBLE=0
if [ -x "$APP_BUNDLE/Contents/MacOS/$APP_NAME" ] \
   && [ -f "$FINGERPRINT_FILE" ] && [ "$(cat "$FINGERPRINT_FILE")" = "$NEW_FP" ] \
   && codesign --verify --deep "$APP_BUNDLE" >/dev/null 2>&1; then
    echo "==> 构建产物未变化，保留现有签名（一次性授权，不再弹权限框）"
    SKIP_ASSEMBLE=1
fi

if [ "$SKIP_ASSEMBLE" = "1" ]; then
    if [ "$#" -gt 0 ] && [ "$1" = "--verify" ]; then
        /usr/bin/open -n "$APP_BUNDLE"
        sleep 1
        if pgrep -x "$APP_NAME" >/dev/null; then
            echo "==> 已启动（进程存在）"
        else
            echo "==> 未检测到进程"
        fi
    else
        echo "==> 启动 $APP_BUNDLE"
        /usr/bin/open -n "$APP_BUNDLE"
    fi
    exit 0
fi

echo "==> 组装 $APP_BUNDLE"
mkdir -p "$APP_BUNDLE/Contents/MacOS" "$APP_BUNDLE/Contents/Resources"
cp "$BIN_PATH" "$APP_BUNDLE/Contents/MacOS/$APP_NAME"
if [ -f "$ICONSET_FILE" ]; then
    cp "$ICONSET_FILE" "$APP_BUNDLE/Contents/Resources/AppIcon.icns"
fi
# 生成内嵌 HTML 帮助页并打包进 Resources（用浏览器打开，不依赖 Xcode）
HELP_SRC="$PROJECT_DIR/docs/使用帮助.md"
if [ -f "$HELP_SRC" ]; then
    /usr/bin/python3 "$PROJECT_DIR/script/md_to_html.py" "$HELP_SRC" "$APP_BUNDLE/Contents/Resources/Help.html" && echo "  已打包帮助文档 Help.html"
else
    echo "  [warn] 未找到帮助源 $HELP_SRC，跳过打包" >&2
fi
# 内嵌自包含引擎（若已由 PyInstaller 生成）。包含 Python 运行时+依赖+Playwright 驱动与 Chromium 浏览器，
# 使 App 不依赖本机 Python/浏览器，可分发到其他 Mac 离线运行。
ENGINE_SRC="$PROJECT_DIR/../build/engine-pkg/dist/engine_xxt"
if [ -d "$ENGINE_SRC" ]; then
    mkdir -p "$APP_BUNDLE/Contents/Resources/engine_xxt"
    cp -R "$ENGINE_SRC/." "$APP_BUNDLE/Contents/Resources/engine_xxt/"
    # 剔除引擎运行时产物（progress.json / logs），防止残留在 Bundle 内被运行改写的封印破坏
    # 代码签名校验（这些运行时文件在 Application Support 中生成，不该进 Bundle）。
    rm -f "$APP_BUNDLE/Contents/Resources/engine_xxt/_internal/progress.json"
    rm -rf "$APP_BUNDLE/Contents/Resources/engine_xxt/_internal/logs"
    MS_DIR="$APP_BUNDLE/Contents/Resources/ms-playwright"
    rm -rf "$MS_DIR"
    mkdir -p "$MS_DIR"
    # 轻量化：只内嵌无头浏览器 + ffmpeg（日常默认 headless 抓取离线可用）；
    # 完整 Chromium（登录组件）不在分发包内，需要时由引擎按需下载到用户目录。
    for b in chromium_headless_shell-1223 ffmpeg-1011; do
        if [ -d "$HOME/Library/Caches/ms-playwright/$b" ]; then
            cp -R "$HOME/Library/Caches/ms-playwright/$b" "$MS_DIR/"
        fi
    done
    echo "  已内嵌自包含引擎 + 无头浏览器（轻量）"
else
    echo "  [warn] 未找到内置引擎 $ENGINE_SRC，App 将回退开发环境解释器" >&2
fi

cat > "$APP_BUNDLE/Contents/Info.plist" <<PLIST
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0">
<dict>
    <key>CFBundleName</key>
    <string>学习通作业爬取工具</string>
    <key>CFBundleDisplayName</key>
    <string>学习通作业爬取工具</string>
    <key>CFBundleIdentifier</key>
    <string>com.local.xxt.app</string>
    <!-- 若某次强杀后 launchd 拒绝重生（RBS error 162），可临时改为新 id 绕过 -->
    <key>CFBundleSignature</key>
    <string>????</string>
    <key>CFBundleExecutable</key>
    <string>$APP_NAME</string>
    <key>CFBundlePackageType</key>
    <string>APPL</string>
    <key>CFBundleIconFile</key>
    <string>AppIcon</string>
    <key>CFBundleIconName</key>
    <string>AppIcon</string>
    <!-- 声明中文本地化：让系统默认菜单（文件/编辑/窗口/退出等）随系统语言显示中文 -->
    <key>CFBundleDevelopmentRegion</key>
    <string>zh-Hans</string>
    <key>CFBundleLocalizations</key>
    <array>
        <string>zh-Hans</string>
        <string>en</string>
    </array>
    <key>CFBundleShortVersionString</key>
    <string>2.1</string>
        <key>CFBundleVersion</key>
        <string>2.1</string>
        <key>CFBundleGetInfoString</key>
        <string>学习通作业爬取工具 v2.1 beta</string>
    <key>LSMinimumSystemVersion</key>
    <string>14.0</string>
    <key>NSPrincipalClass</key>
    <string>NSApplication</string>
    <key>NSHighResolutionCapable</key>
    <true/>
    <key>NSHumanReadableCopyright</key>
    <string></string>
</dict>
</plist>
PLIST

# 关键：组装完成后必须对整个 .app 重新签名（ad-hoc），
# 否则二进制在 build 时生成的签名不覆盖后写入的 Info.plist，
# 会出现 Info.plist=not bound，被 taskgated 判定为 Invalid Signature 而 SIGKILL。
echo "==> 对 $APP_BUNDLE 进行 ad-hoc 签名"
codesign --force --deep --sign - "$APP_BUNDLE"

# 签名后校验是否已正确绑定 Info.plist
codesign --verify --deep "$APP_BUNDLE"

# 记录本次已安装的构建产物指纹，供下次构建比对以决定是否保留签名
echo "$NEW_FP" > "$FINGERPRINT_FILE"

if [ "$#" -gt 0 ] && [ "$1" = "--verify" ]; then
    /usr/bin/open -n "$APP_BUNDLE"
    sleep 1
    if pgrep -x "$APP_NAME" >/dev/null; then
        echo "==> 已启动（进程存在）"
    else
        echo "==> 未检测到进程"
    fi
else
    echo "==> 启动 $APP_BUNDLE"
    /usr/bin/open -n "$APP_BUNDLE"
fi