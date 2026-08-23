#!/bin/bash
# 将 dist/XxtApp.app 封装为 .dmg 安装镜像，并配置带「拖入 Applications」提示的界面
# 用法: ./script/build_dmg.sh   （需先生成 dist/XxtApp.app，即先运行 build_and_run.sh）
set -euo pipefail

cd "$(dirname "$0")/.."   # 切到 xxt-swift 目录

APP="dist/XxtApp.app"
VOLNAME="学习通作业爬取工具"
DMG="dist/学习通作业爬取工具-2.0-beta.dmg"
MOUNT="/Volumes/$VOLNAME"

if [ ! -d "$APP" ]; then
    echo "[error] 未找到 $APP，请先运行 ./script/build_and_run.sh 构建应用" >&2
    exit 1
fi

# ---------- 挂载清理：若该卷已被残留占用，先强制卸载，避免后续 attach/detach 冲突 ----------
if mount | grep -q "$MOUNT "; then
    echo "[warn] 检测到 $MOUNT 仍被挂载（可能是上次失败遗留），先清理…"
    diskutil unmountDisk force "$MOUNT" >/dev/null 2>&1 || \
        hdiutil detach "$MOUNT" -force >/dev/null 2>&1 || true
    sleep 1
fi

STAGE="build/stage"
rm -rf "$STAGE" "$DMG"
mkdir -p "$STAGE/.background"

# 1. 拷贝应用本体 + 生成安装界面背景图（隐藏目录 .background）
cp -R "$APP" "$STAGE/XxtApp.app"
# 箭头几何参数（点，距内容区底部坐标）。若背景预览中箭头偏高/低或偏长，
# 只改这里三个数值即可，无需重写脚本：
#   ARROW_Y 越大箭头越高；ARROW_CX 越大越靠右；ARROW_HALF 越大箭杆越长。
ARROW_Y=300.0
ARROW_CX=425.0
ARROW_HALF=140.0
python3 script/make_dmg_ui.py --out "$STAGE/.background/background.png" \
    --arrow-y-pt "$ARROW_Y" --arrow-cx-pt "$ARROW_CX" --arrow-half-pt "$ARROW_HALF"

# 2. 提供指向 /Applications 的链接，方便用户拖拽安装
ln -s /Applications "$STAGE/Applications"

# 3. 生成临时「可写」镜像（UDRW）。布局（背景+图标位置）需要写入卷内 .DS_Store，
#    这要求 Finder 写在可写卷上；只读压缩镜像（UDZO）挂载后无法回写 .DS_Store，
#    会导致 AppleScript 布局调用"成功"但背景并不固化。
#   所以流程为：可写镜像 → 挂载写布局 → 优雅卸载（.DS_Store 落盘）→ 再转只读压缩。
#   注意：hdiutil 对未知扩展名会自动补 .dmg（如 .udrw -> .udrw.dmg），
#       故临时文件用 .tmp.dmg 结尾以免路径对不上。
DMG_TMP="${DMG%.dmg}.tmp.dmg"
echo "==> 生成临时可写镜像 $DMG_TMP"
rm -f "$DMG_TMP"
hdiutil create \
    -volname "$VOLNAME" \
    -srcfolder "$STAGE" \
    -ov \
    -format UDRW \
    "$DMG_TMP"
rm -rf "$STAGE"

# ---------- Finder 布局写入（Best-effort，失败不中断，DMG 仍可用）----------
BG="$MOUNT/.background/background.png"
# 用 create-dmg 的标准做法：显式 make new Finder window + set target 绑定到挂载卷。
# 背景必须用 (POSIX file ...) as alias 传参（字符串在某些 macOS 上会静默失败），
# 且背景设置不放进 try，确保失败能被检测到。
# 返回格式：AX,AY;BX,BY —— 两个图标的实际 position（左下角原点、点）。
write_layout() {
local osax_out
osax_out=$(osascript 2>&1 <<APPLESCRIPT
tell application "Finder"
    activate
    set dmgWindow to (make new Finder window)
    set target of dmgWindow to (POSIX file "$MOUNT")
    delay 1
    try
        set current view of dmgWindow to icon view
    end try
    try
        set toolbar visible of dmgWindow to false
    end try
    try
        set statusbar visible of dmgWindow to false
    end try
    try
        set the bounds of dmgWindow to {0, 0, 1000, 680}
    end try
    try
        tell icon view options of dmgWindow
            set arrangement to not arranged
            set icon size to 150
            set text size to 14
        end tell
    end try
    tell icon view options of dmgWindow
        set background picture to (POSIX file "$BG") as alias
    end tell
    delay 1
    try
        set position of item "XxtApp.app" of dmgWindow to {175, 175}
    end try
    try
        set position of item "Applications" of dmgWindow to {675, 175}
    end try
    delay 1
    -- 读取两图标「真实渲染边界」bounds{x1,y1,x2,y2}（左上角原点、点），
    -- 比 position 更贴近屏幕实际位置，据此摆放箭头绝不与图标重叠。
    try
        set a to bounds of item "XxtApp.app" of dmgWindow
    on error
        set a to {175, 175, 325, 325}
    end try
    try
        set b to bounds of item "Applications" of dmgWindow
    on error
        set b to {675, 175, 825, 325}
    end try
    return ((item 1 of a) as string) & "," & ((item 2 of a) as string) & "," & ((item 3 of a) as string) & "," & ((item 4 of a) as string) & ";" & ((item 1 of b) as string) & "," & ((item 2 of b) as string) & "," & ((item 3 of b) as string) & "," & ((item 4 of b) as string)
end tell
APPLESCRIPT
)
# 判定：能解析出 AX1,AY1,AX2,AY2;BX1,BY1,BX2,BY2（注意两组之间是分号）即视为布局成功
local pos_re='^-?[0-9.]+,-?[0-9.]+,-?[0-9.]+,-?[0-9.]+;-?[0-9.]+,-?[0-9.]+,-?[0-9.]+,-?[0-9.]+$'
if [[ "$osax_out" =~ $pos_re ]]; then
    echo "$osax_out"
    return 0
else
    echo "[warn] 布局 AppleScript 输出异常：$osax_out" >&2
    # 临时诊断：改用索引方式列出 Finder 当前所有窗口名（避免 repeat-with-in-list 的 -1728）
    osascript 2>&1 <<APPLESCRIPT
tell application "Finder"
    set theWindows to every window
    set lst to ""
    repeat with i from 1 to count of theWindows
        try
            set lst to lst & "[" & (name of item i of theWindows) & "] "
        end try
    end repeat
    return "当前窗口: " & lst
end tell
APPLESCRIPT
    return 1
fi
}

# 4. 挂载（可写临时镜像，以便 Finder 回写 .DS_Store）
echo "==> 挂载 $DMG_TMP"
ATTACH=$(hdiutil attach "$DMG_TMP" -mountpoint "$MOUNT" -nobrowse 2>&1 || true)
echo "$ATTACH"
# 解析真实设备节点（如 /dev/disk6），供卸载使用
DEV=""
while read -r line; do
    if [[ "$line" =~ ^/dev/di(s|sk) ]]; then
        DEV="$(echo "$line" | awk '{print $1}')"
        break
    fi
done <<< "$ATTACH"
[ -n "$DEV" ] || DEV="$MOUNT"

LAYOUT_OK=0
# 第一遍：挂载后先设置图标位置/背景并读取两图标真实边界 AX1,AY1,AX2,AY2;BX1,BY1,BX2,BY2
if ICON_POS=$(write_layout); then
    echo "[info] 已读取图标真实边界：$ICON_POS"
    LAYOUT_OK=1
    # 解析 左图标 LX1,LY1,LX2,LY2；右图标 RX1,RY1,RX2,RY2
    IFS=',' read -r LX1 LY1 LX2 LY2 <<< "${ICON_POS%%;*}"
    IFS=',' read -r RX1 RY1 RX2 RY2 <<< "${ICON_POS#*;}"
    if [[ -n "$LX2" && -n "$RX1" ]]; then
        # 圆心取空隙正中；箭杆收紧到空隙的 45%，保持视觉干练不过长
        GAP_CX=$(python3 -c "print((${LX2}+${RX1})/2)")
        GAP_HALF=$(python3 -c "print(max(((${RX1}-${LX2})/2)*0.45, 30.0))")
        # 垂直：取图标真实边界中心的简单均值（顶原点）。此前每次「偏下」都是因为
        # 现分支因正则漏分号而从未真正重绘，改用占位背景所致；本次先按真实中心对齐。
        GAP_Y=$(python3 -c "print(((${LY1}+${LY2})/2 + (${RY1}+${RY2})/2)/2)")
        echo "==> 按真实空隙精确摆放箭头：中心(${GAP_CX},${GAP_Y}) 半宽 ${GAP_HALF}"
        python3 script/make_dmg_ui.py --out "$BG" \
            --gap-pt "$GAP_CX" "$GAP_Y" "$GAP_HALF"
        # 重设背景让 Finder 加载更新后的箭头（就地刷新，无需重建窗口）
        osascript 2>&1 <<APPLESCRIPT >/dev/null
tell application "Finder"
    activate
    set theWindows to every window
    repeat with i from 1 to count of theWindows
        try
            if (name of item i of theWindows) contains "$VOLNAME" then
                set bounds of item i of theWindows to {0, 0, 1000, 680}
                tell icon view options of item i of theWindows
                    set background picture to (POSIX file "$BG") as alias
                end tell
                exit repeat
            end if
        end try
    end repeat
end tell
APPLESCRIPT
    fi
else
    echo "[warn] Finder 布局写入失败（终端/Finder 未授予 AppleEvent 自动化权限，或位于受限环境）。"
    echo "       若希望显示安装画面，请到\n       「系统设置→隐私与安全→自动化」允许本终端控制 Finder 后重跑。"
fi

# 5. 卸载：保持 DMG 窗口打开，先用「优雅卸载」，让 Finder 把窗口视图设置
#    （背景 + 图标位置）写回卷内的 .DS_Store。（-force 会跳过写盘，导致背景丢失）
#    只有优雅卸载失败时才退回强解挂兜底。
echo "==> 卸载镜像（优雅，期待 .DS_Store 回写）"
if hdiutil detach "$MOUNT" 2>/dev/null || hdiutil detach "$DEV" 2>/dev/null; then
    ejected=true
else
    ejected=false
    for i in 1 2 3 4 5; do
        if hdiutil detach "$DEV" -force 2>/dev/null || hdiutil detach "$MOUNT" -force 2>/dev/null; then
            ejected=true
            break
        fi
        # 强解挂：先杀占用进程，再强制 eject
        (lsof "$MOUNT" 2>/dev/null | awk 'NR>1 {print $2}' | sort -u | xargs kill 2>/dev/null) || true
        diskutil unmountDisk force "$DEV" >/dev/null 2>&1 || diskutil eject force "$DEV" >/dev/null 2>&1 || true
        sleep 2
    done
fi

if ! mount | grep -q "$MOUNT "; then
    echo "[info] 卸载完成"
else
    echo "[warn] 卷仍被占用，卸载未完全成功。可在系统弹窗或访达中手动推出「$VOLNAME」。"
    exit 1
fi

# 6. 布局（.DS_Store）已在可写镜像中固化，现转换为最终只读压缩镜像（UDZO）
echo "==> 压缩为只读镜像 $DMG"
rm -f "$DMG"
hdiutil convert "$DMG_TMP" \
    -format UDZO \
    -imagekey zlib-level=9 \
    -o "$DMG"
rm -f "$DMG_TMP"

echo "==> 完成：$DMG"
ls -lh "$DMG"

# 构建成功后播放系统提示音（Glass 音效），直观告知任务完成
echo "==> 播放完成提示音"
afplay /System/Library/Sounds/Glass.aiff >/dev/null 2>&1 || \
    osascript -e 'beep' >/dev/null 2>&1 || true

if [ "$LAYOUT_OK" = "0" ]; then
    echo ""
    echo "提示：本次 DMG 未固化为带背景的安装画面，但仍可正常拖拽安装。"
    echo "      如需完整安装界面，请授予本终端对 Finder 的自动化权限后重新运行："
    echo "          cd /Users/pengyufeng/Documents/xxt/xxt-swift && ./script/build_dmg.sh"
fi