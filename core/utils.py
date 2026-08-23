#!/usr/bin/env python3
"""通用工具函数。"""
from __future__ import annotations

import re
import sys

from docx import Document
from docx.oxml.ns import qn
from docx.shared import Inches, Pt, RGBColor
try:
    from PIL import Image
except Exception:
    Image = None


def safe_filename(title: str) -> str:
    title = title.strip()
    # 去掉常见状态后缀，避免同一作业产生重复文件
    for status in ["未交", "未做", "已完成", "待做", "进行中"]:
        title = re.sub(r'[\s_\-（(]*' + status + r'[\s_\-）)]*$', '', title)
    # 去除控制字符、零宽字符（避免文件名、JSON、Word 解析异常）
    title = re.sub(r'[\x00-\x1f\x7f\u200b-\u200f\ufeff]', '', title)
    # 去掉会干扰 Markdown 图片语法 / 文件路径的括号、方括号与空格
    title = re.sub(r'[\\/:*?"<>|\n\r\t()\[\] ]', "_", title)
    # 合并连续下划线，去除首尾下划线
    title = re.sub(r'[_]+', "_", title).strip("_")
    return title[:80] or "未命名"


def extract_course_name(page) -> str:
    """从课程页面提取课程名称，用于输出目录命名。"""
    try:
        title = page.title().strip()
    except Exception:
        title = ""

    # 去除学习通/超星常见后缀
    for suffix in ["- 学习通", "— 学习通", "_学习通", " - 超星", " - Chaoxing", " - chaoxing", "-学习通"]:
        if title.endswith(suffix):
            title = title[: -len(suffix)].strip()

    # 取主标题（通常在最前面）
    title = title.split("-")[0].split("—")[0].strip()
    if title and title not in ("用户登录", "404", "错误页面", ""):
        return safe_filename(title)

    # 尝试页面内课程名元素
    selectors = [
        "h1",
        ".course-name",
        ".courseTitle",
        ".course-title",
        ".coursename",
        "[class*='courseName']",
        "[class*='course-name']",
    ]
    for sel in selectors:
        try:
            el = page.locator(sel).first
            if el.count():
                text = el.inner_text().strip()
                if text:
                    return safe_filename(text)
        except Exception:
            continue
    return safe_filename("未命名课程")


def is_login_page(page, debug: bool = True) -> bool:
    """
    判断当前页面是否为学习通登录页。
    使用多重特征（域名、标题、表单元素、页面文本）降低误判。
    debug=True 时打印命中原因，便于排查误判。
    """
    url = page.url.lower()
    title = page.title().lower()

    # 明确是登录域名
    if ("passport2.chaoxing.com" in url or "login.chaoxing.com" in url) and "login" in url:
        if debug:
            print(f"    [debug] 判定为登录页：URL 是登录域名 ({page.url})")
        return True

    # 标题明确是登录
    if "用户登录" in title or "登录-学习通" in title or "登录_学习通" in title:
        if debug:
            print(f"    [debug] 判定为登录页：页面标题 ({page.title()})")
        return True

    # 存在典型登录表单元素（uname + password 同时存在）
    try:
        has_uname = page.locator("input[name='uname']").count() > 0
        has_password = page.locator("input[name='password']").count() > 0
        if has_uname and has_password:
            if debug:
                print("    [debug] 判定为登录页：存在 uname + password 输入框")
            return True
    except Exception:
        pass

    # body 文本包含明确登录提示且伴随账号/密码输入
    try:
        body_text = page.inner_text("body", timeout=3000).lower()
        if ("请登录" in body_text or "登录超时" in body_text or "请重新登录" in body_text) and (
            "账号" in body_text or "密码" in body_text or "uname" in body_text
        ):
            if debug:
                preview = body_text[:120].replace("\n", " ")
                print(f"    [debug] 判定为登录页：页面文本含登录提示 ({preview}...)")
            return True
    except Exception:
        pass

    if debug:
        print(f"    [debug] 非登录页：URL={page.url[:120]}，标题={page.title()}")
    return False


def check_course_url_valid(page) -> str:
    """
    检查课程 URL 是否有效/过期。
    返回空字符串表示正常；否则返回错误提示。
    """
    title = page.title()

    # 跳转到登录页
    if is_login_page(page):
        return "课程 URL 已过期或登录态失效，请重新登录后复制课程页面 URL。"

    # 常见错误页面
    error_keywords = ["404", "error", "无法访问", "不存在", "无权限", "非法请求"]
    if any(kw in title for kw in error_keywords):
        return f"页面返回错误：{title}。请检查课程 URL 是否有效。"

    # 课程页正常应包含课程名或导航，若页面空白/只显示框架可能已过期
    body_text = ""
    try:
        body_text = page.inner_text("body", timeout=3000).lower()
    except Exception:
        pass
    if "参数错误" in body_text or "登录超时" in body_text or "请重新登录" in body_text:
        return "课程 URL 参数错误或登录超时，请重新复制课程页面 URL。"

    return ""


def _get_system_chinese_font() -> str:
    """根据操作系统选择较好看的中文字体。"""
    if sys.platform == "darwin":
        return "PingFang SC"
    elif sys.platform == "win32":
        return "Microsoft YaHei"
    return "WenQuanYi Micro Hei"


def _set_run_font(run, font_name: str = None, font_size: int = None, bold: bool = False, color: str = None):
    """统一设置 run 的字体、字号、加粗、颜色。"""
    if font_name is None:
        font_name = _get_system_chinese_font()
    run.font.name = font_name
    run._element.rPr.rFonts.set(qn('w:eastAsia'), font_name)
    if font_size:
        run.font.size = Pt(font_size)
    run.font.bold = bold
    if color:
        run.font.color.rgb = RGBColor.from_string(color)


def _set_document_default_font(doc: Document, font_name: str):
    """设置文档默认字体（正文 + 东亚字体）。"""
    style = doc.styles['Normal']
    style.font.name = font_name
    style._element.rPr.rFonts.set(qn('w:eastAsia'), font_name)
    style.font.size = Pt(11)


def _calc_picture_size(local_path: str, max_width_inches: float = 5.5, max_height_inches: float = 4.5):
    """根据图片原始尺寸计算 Word 中合适的显示尺寸，保持比例。"""
    if Image is None:
        return Inches(3.0), None
    try:
        with Image.open(local_path) as img:
            w_px, h_px = img.size
            dpi = 96
            try:
                dpi = img.info.get('dpi', (96, 96))[0]
                if not dpi or dpi < 1:
                    dpi = 96
            except Exception:
                pass
            w_in = w_px / dpi
            h_in = h_px / dpi
            if w_in > max_width_inches:
                scale = max_width_inches / w_in
                w_in = max_width_inches
                h_in *= scale
            if h_in > max_height_inches:
                scale = max_height_inches / h_in
                h_in = max_height_inches
                w_in *= scale
            # 小图不过度放大
            if w_in < 1.5:
                scale = 1.5 / w_in
                w_in = 1.5
                h_in *= scale
                if h_in > max_height_inches:
                    scale = max_height_inches / h_in
                    h_in = max_height_inches
                    w_in *= scale
            return Inches(w_in), Inches(h_in)
    except Exception:
        return Inches(3.0), None


def _safe_run_text(text: str) -> str:
    """确保写入 Word 段落的文本不含破坏 XML/OOXML 的控制字符。"""
    if not text:
        return ""
    # 去除 C0 控制字符（保留 TAB、LF、CR 由 python-docx 自行处理）和零宽字符
    text = re.sub(r'[\x00-\x08\x0b-\x0c\x0e-\x1f\x7f\u200b-\u200f\ufeff]', '', text)
    return text


def _clean_extracted_text(text: str) -> str:
    """统一清理从页面提取到的文本：折叠空白、去除控制字符与零宽字符。"""
    if not text:
        return ""
    # 去除控制字符（保留普通换行/空格由后续折叠处理）和零宽字符
    text = re.sub(r'[\x00-\x08\x0b-\x0c\x0e-\x1f\x7f\u200b-\u200f\ufeff]', '', text)
    # 折叠多种空白为单个空格
    text = re.sub(r'\s+', ' ', text).strip()
    return text


def _clean_alt_for_markdown(alt: str) -> str:
    """清理图片 alt 文本，去除会干扰 Markdown 图片语法 []() 的字符。"""
    if not alt:
        return "图片"
    # 去除控制字符、零宽字符
    alt = re.sub(r'[\x00-\x1f\x7f\u200b-\u200f\ufeff]', '', alt)
    # 去除 Markdown 图片语法分隔符及可能破坏路径的字符
    alt = alt.replace('[', '').replace(']', '').replace('(', '').replace(')', '')
    alt = alt.strip() or "图片"
    return alt[:60]
