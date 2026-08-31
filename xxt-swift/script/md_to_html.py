#!/usr/bin/env python3
"""把 docs/使用帮助.md 转成内嵌 HTML 帮助页（用系统默认浏览器可打开，无 Xcode 依赖）。

用法: md_to_html.py <input.md> <output.html>
仅支持本项目文档用到的语法（atx 标题、表格、粗体、行内代码、列表、代码块、引用、分隔线）。
"""
from __future__ import annotations

import html
import re
import sys

CSS = """
body{margin:0 auto;max-width:820px;padding:32px 40px;font-family:-apple-system,BlinkMacSystemFont,"PingFang SC","Helvetica Neue",Arial,sans-serif;
color:#1d1d1f;line-height:1.7;font-size:15px;-webkit-text-size-adjust:100%}
h1{border-bottom:2px solid #f0f0f2;padding-bottom:10px;font-size:26px}
h2{margin-top:32px;font-size:20px;color:#1d1d1f}
h3{font-size:16px}
code{background:#f5f5f7;border-radius:5px;padding:1px 6px;font-size:90%;font-family:"SF Mono",Menlo,monospace}
pre{background:#f5f5f7;border-radius:10px;padding:14px 16px;overflow:auto}
pre code{background:transparent;padding:0}
table{border-collapse:collapse;width:100%;margin:16px 0}
th,td{border:1px solid #e2e2e6;padding:8px 12px;text-align:left;font-size:14px}
th{background:#fafafc}
blockquote{border-left:4px solid #007aff;background:#f0f7ff;margin:12px 0;padding:8px 16px;border-radius:6px;color:#333}
a{color:#007aff;text-decoration:none}
hr{border:none;border-top:1px solid #e2e2e6;margin:24px 0}
ul,ol{padding-left:24px}
"""


def inline(text: str) -> str:
    """行内样式：代码、粗体、链接。"""
    # 先转义，再按序还原
    t = html.escape(text, quote=False)
    t = re.sub(r"`([^`]+)`", lambda m: "<code>%s</code>" % m.group(1), t)
    t = re.sub(r"\*\*([^*]+)\*\*", lambda m: "<strong>%s</strong>" % m.group(1), t)
    t = re.sub(r"\[([^\]]+)\]\(([^)]+)\)",
               lambda m: '<a href="%s">%s</a>' % (m.group(2), m.group(1)), t)
    return t


def slug(text: str) -> str:
    """把标题文本转成稳定的 HTML 片内锚点 id。

    规则：全角破折号/下划线 → 连字符 `-`，再移除其余所有非「中文/字母/数字/连字符」
    字符（标点、空格、括号等）。与 markdown 目录里手写的 `#锚点` 约定保持一致，
    使目录链接与标题 id 能对上、可正常跳转。
    """
    s = text.replace("——", "--").replace("—", "-").replace("_", "-")
    return re.sub(r"[^\w-]", "", s, flags=re.UNICODE)


def render(md: str) -> str:
    lines = md.splitlines()
    out: list[str] = []
    i = 0
    n = len(lines)
    in_code = False
    list_stack: str = ""  # "" or "ul" or "ol"
    table_buf: list[str] = []

    def flush_list():
        nonlocal list_stack
        if list_stack:
            out.append("</%s>" % list_stack)
            list_stack = ""

    def flush_table():
        nonlocal table_buf
        if not table_buf:
            return
        rows = []
        for idx, row in enumerate(table_buf):
            cells = [c.strip() for c in row.strip("|").split("|")]
            tag = "th" if idx == 0 else "td"
            rows.append("<tr>%s</tr>" % "".join("<%s>%s</%s>" % (tag, inline(c), tag) for c in cells))
        out.append('<table><tbody>%s</tbody></table>' % "".join(rows))
        table_buf = []

    while i < n:
        line = lines[i]
        stripped = line.strip()

        # 代码块
        if stripped.startswith("```"):
            if not in_code:
                flush_list()
                flush_table()
                out.append("<pre><code>")
                in_code = True
            else:
                out.append("</code></pre>")
                in_code = False
            i += 1
            continue
        if in_code:
            out.append(html.escape(line))
            i += 1
            continue

        # 空行
        if not stripped:
            flush_list()
            flush_table()
            out.append("")
            i += 1
            continue

        # 表格：连续含 | 行，且第二行是分隔
        if stripped.startswith("|") and i + 1 < n and re.match(r"^\s*\|?[\s:|-]+\|?\s*$", lines[i + 1]):
            flush_list()
            table_buf = [stripped]
            i += 2
            while i < n and "|" in lines[i].strip():
                table_buf.append(lines[i].strip())
                i += 1
            flush_table()
            continue

        # 标题（带 slug 锚点 id，供目录跳转）
        m = re.match(r"^(#{1,6})\s+(.*)$", stripped)
        if m:
            flush_list()
            flush_table()
            level = len(m.group(1))
            anchor = slug(m.group(2))
            out.append('<h%d id="%s">%s</h%d>' % (level, anchor, inline(m.group(2)), level))
            i += 1
            continue

        # 分隔线
        if re.match(r"^-{3,}$", stripped) or re.match(r"^\*{3,}$", stripped):
            flush_list()
            flush_table()
            out.append("<hr>")
            i += 1
            continue

        # 列表
        lm = re.match(r"^([-*]|\d+\.)\s+(.*)$", line)
        if lm:
            tag = "ol" if lm.group(1)[0].isdigit() else "ul"
            if list_stack and list_stack != tag:
                flush_list()
            if not list_stack:
                out.append("<%s>" % tag)
                list_stack = tag
            out.append("<li>%s</li>" % inline(lm.group(2)))
            i += 1
            continue

        # 引用
        if stripped.startswith(">"):
            flush_list()
            flush_table()
            out.append("<blockquote>%s</blockquote>" % inline(stripped.lstrip("> ")))
            i += 1
            continue

        flush_list()
        flush_table()
        out.append("<p>%s</p>" % inline(stripped))
        i += 1

    flush_list()
    flush_table()
    if in_code:
        out.append("</code></pre>")
    return "\n".join(out)


def main() -> int:
    if len(sys.argv) != 3:
        print("usage: md_to_html.py <input.md> <output.html>", file=sys.stderr)
        return 2
    with open(sys.argv[1], encoding="utf-8") as f:
        md = f.read()
    branch = "<br>"  # 备用
    body = render(md)
    page = (
        "<!DOCTYPE html>\n<html lang=\"zh-CN\"><head><meta charset=\"utf-8\">"
        "<title>学习通作业抓取 · 使用帮助</title>"
        f"<style>{CSS}</style></head><body>{body}</body></html>"
    )
    with open(sys.argv[2], "w", encoding="utf-8") as f:
        f.write(page)
    # silence unused
    _ = branch
    return 0


if __name__ == "__main__":
    sys.exit(main())