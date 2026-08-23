#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""生成 DMG 安装界面的背景图，并打印 Finder 需要设置的图标位置。

坐标约定：背景按 2x Retina 绘制；Finder 的图标位置使用"点"坐标（从内容区左下角
开始），本脚本通过 --find-pos 直接输出脚本调用方需要的 {x,y} 点坐标。
"""
import argparse
import os

from PIL import Image, ImageDraw, ImageFont

# ---------- 布局常量（单位：点，图片按 2x 渲染）----------
WIN_W = 1000          # 窗口内容区宽（点）
CONTENT_H = 680       # 窗口内容区高（点）
SCALE = 2             # Retina 2x，背景图 = 窗口内容尺寸 × scale

FONT_PATH = "/System/Library/Fonts/Hiragino Sans GB.ttc"

# 两原生图标的定位（Finder 实际渲染图标，此处仅用于推导图标位置与箭头几何）
APP_POS = (250, 250)      # 左侧 App 图标中心（左下角原点，点）
APPS_POS = (750, 250)     # 右侧 Applications 图标中心（左下角原点，点）
ICON_SIZE = 150           # 图标尺寸（点）

TITLE = "学习通作业爬取工具"


def make_font(size: int, weight: int = 400):
    return ImageFont.truetype(FONT_PATH, size)


def px(point: float) -> int:
    return int(round(point * SCALE))


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", default="build/stage/.background/background.png")
    # 箭头几何参数（单位：点，同 Finder position 的「距内容区底部」坐标系）
    ap.add_argument("--arrow-y-pt", type=float, default=300.0,
                    help="箭头中线的垂直位置，距内容区底部（点），越大越高")
    ap.add_argument("--arrow-cx-pt", type=float, default=425.0,
                    help="箭头水平中心（点）")
    ap.add_argument("--arrow-half-pt", type=float, default=140.0,
                    help="箭杆自中心向两侧的半宽（点）")
    # 实测模式：直接给出两图标的中心坐标（点），脚本自动把箭头夹在两图标之间
    ap.add_argument("--arrow-between", nargs=4, type=float, metavar=("LXC", "LYC", "RXC", "RYC"),
                    help="(可选) 左/右图标中心 x,y，取两图标空隙中心与共同高度画箭头，覆盖上面三个箭头参数")
    ap.add_argument("--arrow-y-nudge", type=float, default=-28.0,
                    help="(仅实测模式) 垂直微调箭头位置（点，负值=上移），矫正图标下方名字标签带来的视觉重心偏移")
    # 直接给定箭头几何（顶原点 y）：由 build_dmg.sh 读取图标真实 bounds 后算出，最精确
    ap.add_argument("--gap-pt", nargs=3, type=float, metavar=("CX", "CY_TOP", "HALF"),
                    help="(可选) 直接给定箭头：中线x, 中线y(左上角原点,点), 半宽(点)；按此精确绘制，覆盖上方所有推导")
    ap.add_argument("--find-pos", action="store_true",
                    help="打印 Finder 需要的图标位置并退出（不生成图片）")
    args = ap.parse_args()

    # ---- 计算箭头几何（若给定实测图标中心则自动夹在中间，否则用显式参数）----
    if args.gap_pt:
        arrow_y_pt, arrow_cx_pt, arrow_half_pt = args.gap_pt[1], args.gap_pt[0], args.gap_pt[2]
        gap_pt_mode = True
    else:
        gap_pt_mode = False
        if args.arrow_between:
            lx, ly, rx, ry = args.arrow_between
            # 图标尺寸 150：空隙为 [lx+75, rx-75]，中心与半宽由此推导
            gap_cx = (lx + 75 + rx - 75) / 2
            # 箭杆自图标左右边缘各内缩 50pt，保证明显比两图标间的空隙短
            gap_half = max((rx - 75 - (lx + 75)) / 2 - 50.0, 30.0)
            arrow_y_pt = (ly + ry) / 2 + args.arrow_y_nudge  # 上移补偿名字标签
            arrow_cx_pt = gap_cx
            arrow_half_pt = gap_half
        else:
            arrow_y_pt = args.arrow_y_pt
            arrow_cx_pt = args.arrow_cx_pt
            arrow_half_pt = args.arrow_half_pt

    if args.find_pos:
        # Finder 的 position 指的是图标左下角（内容区左下角为原点）
        app_left = APP_POS[0] - ICON_SIZE / 2
        app_bottom = APP_POS[1] - ICON_SIZE / 2
        apps_left = APPS_POS[0] - ICON_SIZE / 2
        apps_bottom = APPS_POS[1] - ICON_SIZE / 2
        print(f"WIN={WIN_W},{CONTENT_H} ICON={int(ICON_SIZE)}")
        print(f"APP_POS={app_left:g},{app_bottom:g}")
        print(f"APPS_POS={apps_left:g},{apps_bottom:g}")
        return

    W = px(WIN_W)
    H = px(CONTENT_H)

    # ---- 柔和的竖向渐变背景 ----
    top = (0xF7, 0xF8, 0xFA)
    bottom = (0xE8, 0xEB, 0xF0)
    canvas = Image.new("RGBA", (W, H))
    for y in range(H):
        t = y / max(H - 1, 1)
        color = tuple(round(top[i] + (bottom[i] - top[i]) * t) for i in range(3))
        canvas.paste(Image.new("RGBA", (W, 1), color + (255,)), (0, y))
    draw = ImageDraw.Draw(canvas)

    accent = (0x4F, 0x46, 0xE5, 255)   # 品牌靛蓝
    ink = (0x33, 0x36, 0x3D, 255)
    gray = (0x6B, 0x70, 0x7A, 255)

    # ---- 顶部标题 ----
    title_font = make_font(px(34))
    tb = draw.textbbox((0, 0), TITLE, font=title_font)
    draw.text(((W - (tb[2] - tb[0])) / 2 - tb[0], px(40) - tb[1]), TITLE,
              font=title_font, fill=ink)

    # ---- 两原生图标之间的箭头（Finder 图标由系统渲染，背景只画连接箭头）----
    # 像素 y 采用「左上角原点」坐标。--gap-pt/--arrow-between 都按顶原点理解；
    # 仅旧的显式 --arrow-y-pt 参数约定为「距内容区底部」，需翻转一次。
    if gap_pt_mode or args.arrow_between:
        cy = px(arrow_y_pt)          # 顶原点像素 y，无需翻转
    else:
        cy = H - px(arrow_y_pt)      # 距底部约定，翻转为顶原点
    shaft_l = px(arrow_cx_pt) - px(arrow_half_pt)
    shaft_r = px(arrow_cx_pt) + px(arrow_half_pt)
    head_tip, head_half = shaft_r + px(40), px(34)
    head_base = shaft_r
    draw.line([(shaft_l, cy), (shaft_r, cy)], fill=accent, width=px(12))
    draw.polygon([(head_tip, cy), (head_base, cy - head_half), (head_base, cy + head_half)],
                 fill=accent)

    # ---- 中间说明文字（普通文字，无背景框，避免与按钮混淆）----
    mid_font = make_font(px(24))
    md_text = "将 App 拖入右侧的 Applications 文件夹完成安装"
    mdb = draw.textbbox((0, 0), md_text, font=mid_font)
    draw.text(((W - (mdb[2] - mdb[0])) / 2 - mdb[0], cy + px(180) - mdb[1]),
              md_text, font=mid_font, fill=gray)

    os.makedirs(os.path.dirname(args.out), exist_ok=True)
    # Finder 的 DMG 窗口背景按「1 像素 = 1 点」平铺显示。若直接输出 2x 大图，
    # 窗口内容区只有约 1000 点宽，会把图从左上角裁掉（标题对齐、其余出界）。
    # 因此内部按 2x 高清绘制，最后统一缩小回 1x（= 窗口点尺寸），保证整图完整显示且文字清晰。
    bg = canvas.resize((W // SCALE, H // SCALE), Image.LANCZOS)
    bg = bg.convert("RGB")
    bg.save(args.out)
    print(f"OK background -> {args.out} ({bg.width}x{bg.height})")


if __name__ == "__main__":
    main()