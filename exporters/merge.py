#!/usr/bin/env python3
"""Word 文档合并。"""
from __future__ import annotations

import os
import traceback


def merge_all_docx(output_directory: str, merged_name: str = "全部作业合并.docx") -> str:
    """把 output_directory 下所有 .docx 合并成一个文档，图片会一并保留。"""
    docx_files = []
    for f in sorted(os.listdir(output_directory)):
        if f.endswith(".docx") and f != merged_name:
            docx_files.append(os.path.join(output_directory, f))

    if len(docx_files) < 2:
        print(f"[info] 目录下只有 {len(docx_files)} 个 Word 文件，无需合并")
        return ""

    try:
        from docxcompose.composer import Composer
        from docx import Document
    except Exception as e:
        print(f"[warn] 加载合并组件失败（docxcompose），本次跳过自动合并：{e}")
        return ""

    try:
        master = Document(docx_files[0])
        composer = Composer(master)
        for path in docx_files[1:]:
            try:
                doc = Document(path)
                composer.append(doc)
                print(f"    已合并：{os.path.basename(path)}")
            except Exception as e:
                print(f"    [warn] 合并 {os.path.basename(path)} 失败：{e}")

        merged_path = os.path.join(output_directory, merged_name)
        composer.save(merged_path)
        print(f"\n已生成合并文档：{merged_path}")
        return merged_path
    except Exception as e:
        print(f"[error] 合并文档失败：{e}")
        traceback.print_exc()
        return ""
