#!/usr/bin/env python3
"""PDF 导出。"""
from __future__ import annotations

import os
import shutil
import subprocess


def detect_pdf_env() -> dict:
    """检测 PDF 转换环境是否可用（Microsoft Word 或 LibreOffice）。

    docx2pdf 在 macOS 上依赖已安装的 Microsoft Word，LibreOffice 走命令行的
    soffice。二者任一可用即可导出。返回：
        {"available": bool, "method": "word"|"libreoffice"|None, "reason": str|None}
    仅作检测，不尝试安装任何依赖。
    """
    # 1) Microsoft Word（docx2pdf 在 mac 的转换宿主）
    word_candidates = [
        "/Applications/Microsoft Word.app",
        os.path.expanduser("~/Applications/Microsoft Word.app"),
    ]
    for p in word_candidates:
        if os.path.isdir(p):
            return {"available": True, "method": "word", "reason": None}
    # 2) LibreOffice 命令行
    if shutil.which("soffice"):
        return {"available": True, "method": "libreoffice", "reason": None}
    return {
        "available": False,
        "method": None,
        "reason": "未检测到 Microsoft Word 或 LibreOffice，将无法导出 PDF",
    }


def export_pdf(docx_path: str, pdf_path: str = None) -> bool:
    """将 Word 文档转换为 PDF。优先使用 docx2pdf，失败时尝试 LibreOffice。"""
    if pdf_path is None:
        pdf_path = docx_path.replace(".docx", ".pdf")
    if os.path.abspath(docx_path) == os.path.abspath(pdf_path):
        pdf_path += ".pdf"

    # 方案 1：docx2pdf（macOS/Windows 需安装 Microsoft Word）
    try:
        from docx2pdf import convert
        convert(docx_path, pdf_path)
        print(f"    已导出 PDF：{pdf_path}")
        return True
    except Exception as e:
        print(f"    [warn] docx2pdf 导出失败：{e}")

    # 方案 2：LibreOffice（跨平台命令行）
    try:
        out_dir = os.path.dirname(os.path.abspath(pdf_path)) or "."
        cmd = [
            "soffice",
            "--headless",
            "--convert-to", "pdf",
            "--outdir", out_dir,
            os.path.abspath(docx_path),
        ]
        result = subprocess.run(cmd, capture_output=True, text=True, timeout=120)
        if result.returncode == 0:
            # LibreOffice 输出文件名与输入相同，仅扩展名变为 .pdf
            generated = os.path.splitext(os.path.abspath(docx_path))[0] + ".pdf"
            if generated != os.path.abspath(pdf_path) and os.path.exists(generated):
                os.replace(generated, pdf_path)
            print(f"    已导出 PDF：{pdf_path}")
            return True
        else:
            print(f"    [warn] LibreOffice 导出失败：{result.stderr}")
    except Exception as e:
        print(f"    [warn] LibreOffice 导出失败：{e}")

    return False
