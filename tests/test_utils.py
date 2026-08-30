"""core.utils 纯函数单元测试：文件名清洗、文本清洗、字体选择等。"""
import sys

import pytest

from core.utils import (
    safe_filename,
    _safe_run_text,
    _clean_extracted_text,
    _clean_alt_for_markdown,
    _get_system_chinese_font,
)


# ---------------- safe_filename ----------------

def test_safe_filename_trims_whitespace():
    assert safe_filename("  第一章 作业  ") == "第一章_作业"


def test_safe_filename_removes_status_suffix():
    # 常见状态后缀会被剔除，避免同一作业生成重复文件
    assert safe_filename("作业1(已完成)") == "作业1"
    assert safe_filename("作业1（未交）") == "作业1"
    assert safe_filename("作业2_进行中") == "作业2"
    assert safe_filename("作业3 待做") == "作业3"


def test_safe_filename_replaces_illegal_chars():
    assert safe_filename("a/b\\c:d*e?f\"g<h>i|j") == "a_b_c_d_e_f_g_h_i_j"


def test_safe_filename_removes_control_and_zero_width():
    assert safe_filename("a\x00b\x1fc\u200bd") == "abcd"


def test_safe_filename_collapses_underscores_and_strips_ends():
    assert safe_filename("  a__  _b  ") == "a_b"


def test_safe_filename_empty_yields_default():
    assert safe_filename("") == "未命名"
    assert safe_filename("   ") == "未命名"


def test_safe_filename_truncated_to_80():
    long_title = "章" * 200
    result = safe_filename(long_title)
    assert len(result) == 80


# ---------------- _safe_run_text ----------------

def test_safe_run_text_strips_control_chars():
    assert _safe_run_text("a\x00b\x01c\u200bd\x7fe") == "abcde"


def test_safe_run_text_empty_and_none():
    assert _safe_run_text("") == ""
    assert _safe_run_text(None) == ""


# ---------------- _clean_extracted_text ----------------

def test_clean_extracted_text_folds_whitespace():
    assert _clean_extracted_text("  第一章\t作业\n答案  ") == "第一章 作业 答案"


def test_clean_extracted_text_strips_control():
    # 零宽/控制字符被「移除」而非转空格
    assert _clean_extracted_text("a\u200bb\x00c") == "abc"


# ---------------- _clean_alt_for_markdown ----------------

def test_clean_alt_removes_markdown_delimiters():
    assert _clean_alt_for_markdown("[图](x)") == "图x"


def test_clean_alt_empty_defaults():
    assert _clean_alt_for_markdown("") == "图片"
    assert _clean_alt_for_markdown(None) == "图片"


def test_clean_alt_truncates_to_60():
    result = _clean_alt_for_markdown("图" * 100)
    assert len(result) == 60


# ---------------- _get_system_chinese_font ----------------

def test_system_font_per_platform(monkeypatch):
    cases = {
        "darwin": "PingFang SC",
        "win32": "Microsoft YaHei",
        "linux": "WenQuanYi Micro Hei",
    }
    for platform, expected in cases.items():
        monkeypatch.setattr(sys, "platform", platform)
        assert _get_system_chinese_font() == expected