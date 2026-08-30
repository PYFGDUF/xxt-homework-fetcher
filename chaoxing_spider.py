#!/usr/bin/env python3
"""
学习通（超星）作业题目抓取脚本 —— 兼容入口。

用法：
    1. 先用 Chrome 登录学习通，复制 Cookie 字符串到 cookies.txt（可选）
    2. python chaoxing_spider.py
    3. 按提示操作；若未提供 Cookie 则会在浏览器中让你手动扫码/登录

本文件现在仅作为兼容入口，保留所有公共 API 供 gui.py / repair.py 导入。
核心逻辑已拆分到 core / exporters / spider 子模块中。
"""
from __future__ import annotations

import os
import sys

# 确保直接运行时能找到 core/spider/exporters 模块
_SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
if _SCRIPT_DIR not in sys.path:
    sys.path.insert(0, _SCRIPT_DIR)

# ============ 核心配置与状态 ============
from core.config import (
    COURSE_URL,
    DEFAULT_OUTPUT_DIR,
    DEFAULT_DEBUG_DIR,
    COOKIE_FILE,
    STATE_FILE,
    SETTINGS_FILE,
    HEADLESS,
    WAIT_TIMEOUT,
    ACTION_TIMEOUT,
    RUN_ID,
    BASE_OUTPUT_DIR,
    BASE_DEBUG_DIR,
    _CURRENT_BROWSER,
    _CURRENT_CONTEXT,
    _SHOULD_STOP,
    _PROGRESS_CALLBACK,
    AUTO_EXPORT_PDF,
    FORCE_REGRAB,
    PROGRESS_FILE,
    MAX_HOMEWORK_PAGES,
    MAX_QUESTION_PAGES,
    set_headless,
    get_headless,
    set_output_dir,
    set_course_url,
    get_course_url,
    set_course_name,
    get_course_name,
    set_auto_export_pdf,
    get_auto_export_pdf,
    set_force_regrab,
    get_force_regrab,
    set_progress_callback,
    set_status_callback,
    set_login_prompt_callback,
    reset_login_event,
    notify_login_done,
    wait_for_login,
    prompt_login_and_wait,
    _report_progress,
    force_stop,
    set_run_id,
    get_run_id,
    set_current_browser,
    get_current_browser,
    set_current_context,
    get_current_context,
    set_should_stop,
    should_stop,
    clear_browser_state,
    set_reusable_browser,
    get_reusable_browser,
    set_reusable_context,
    get_reusable_context,
    set_reusable_page,
    get_reusable_page,
    clear_reusable_browser,
    load_settings,
    save_settings,
    apply_settings,
    get_appearance,
    set_appearance,
    output_dir,
    debug_dir,
    ensure_dirs,
    load_state,
    save_state,
)

# ============ 日志 ============
from core.logger import setup_logging, LOGGER, TeeStdout, with_logging

# ============ 工具函数 ============
from core.utils import (
    safe_filename,
    extract_course_name,
    is_login_page,
    check_course_url_valid,
    _get_system_chinese_font,
    _set_run_font,
    _set_document_default_font,
    _safe_run_text,
    _clean_extracted_text,
    _clean_alt_for_markdown,
)

# ============ 进度 ============
from core.progress import MAX_PROGRESS_RECORDS, MAX_PROGRESS_DAYS, ProgressTracker

# ============ 导出器 ============
from exporters import (
    ImageRegistry,
    _img_url_to_local_name,
    download_image,
    download_images_in_text,
    _calc_picture_size,
    add_markdown_paragraph,
    export_pdf,
    save_word,
    merge_all_docx,
)

# ============ 爬虫逻辑 ============
from spider import (
    enter_homework_tab,
    find_homework_list_frame,
    extract_homework_items,
    click_homework_item,
    collect_all_homeworks,
    find_question_frame,
    extract_text_with_images,
    extract_questions_js,
    extract_answer_fallback,
    extract_questions_from_page,
    click_start_button,
    has_next_page,
    click_next_page,
    get_question_frame,
    extract_all_questions,
    load_homework_list,
    run,
    save_homework,
    standalone_login,
    list_courses,
)
from spider.browser import (
    load_cookies,
    wait_stable,
    click_when_ready,
    debug_screenshot,
    dump_frame_html,
    wait_for_iframe_content,
    scroll_frame_to_bottom,
)
from spider.homework import find_course_list_frame, extract_course_list, is_insight_link

__all__ = [
    # config
    "COURSE_URL",
    "DEFAULT_OUTPUT_DIR",
    "DEFAULT_DEBUG_DIR",
    "COOKIE_FILE",
    "STATE_FILE",
    "SETTINGS_FILE",
    "HEADLESS",
    "WAIT_TIMEOUT",
    "ACTION_TIMEOUT",
    "RUN_ID",
    "BASE_OUTPUT_DIR",
    "BASE_DEBUG_DIR",
    "_CURRENT_BROWSER",
    "_CURRENT_CONTEXT",
    "_SHOULD_STOP",
    "_PROGRESS_CALLBACK",
    "AUTO_EXPORT_PDF",
    "FORCE_REGRAB",
    "PROGRESS_FILE",
    "MAX_HOMEWORK_PAGES",
    "MAX_QUESTION_PAGES",
    "set_headless",
    "get_headless",
    "set_output_dir",
    "set_course_url",
    "get_course_url",
    "set_course_name",
    "get_course_name",
    "set_auto_export_pdf",
    "get_auto_export_pdf",
    "set_force_regrab",
    "get_force_regrab",
    "set_progress_callback",
    "set_status_callback",
    "set_login_prompt_callback",
    "reset_login_event",
    "notify_login_done",
    "wait_for_login",
    "prompt_login_and_wait",
    "_report_progress",
    "force_stop",
    "set_run_id",
    "get_run_id",
    "set_current_browser",
    "get_current_browser",
    "set_current_context",
    "get_current_context",
    "set_should_stop",
    "should_stop",
    "clear_browser_state",
    "set_reusable_browser",
    "get_reusable_browser",
    "set_reusable_context",
    "get_reusable_context",
    "set_reusable_page",
    "get_reusable_page",
    "clear_reusable_browser",
    "load_settings",
    "save_settings",
    "apply_settings",
    "get_appearance",
    "set_appearance",
    "output_dir",
    "debug_dir",
    "ensure_dirs",
    "load_state",
    "save_state",
    # logger
    "setup_logging",
    "LOGGER",
    "TeeStdout",
    "with_logging",
    # utils
    "safe_filename",
    "extract_course_name",
    "is_login_page",
    "check_course_url_valid",
    "_get_system_chinese_font",
    "_set_run_font",
    "_set_document_default_font",
    "_safe_run_text",
    "_clean_extracted_text",
    "_clean_alt_for_markdown",
    # progress
    "MAX_PROGRESS_RECORDS",
    "MAX_PROGRESS_DAYS",
    "ProgressTracker",
    # exporters
    "ImageRegistry",
    "_img_url_to_local_name",
    "download_image",
    "download_images_in_text",
    "_calc_picture_size",
    "add_markdown_paragraph",
    "export_pdf",
    "save_word",
    "merge_all_docx",
    # spider
    "load_cookies",
    "wait_stable",
    "click_when_ready",
    "debug_screenshot",
    "dump_frame_html",
    "wait_for_iframe_content",
    "scroll_frame_to_bottom",
    "enter_homework_tab",
    "find_homework_list_frame",
    "extract_homework_items",
    "click_homework_item",
    "collect_all_homeworks",
    "is_insight_link",
    "find_question_frame",
    "extract_text_with_images",
    "extract_questions_js",
    "extract_answer_fallback",
    "extract_questions_from_page",
    "click_start_button",
    "has_next_page",
    "click_next_page",
    "get_question_frame",
    "extract_all_questions",
    "load_homework_list",
    "run",
    "save_homework",
    "standalone_login",
    "list_courses",
    "find_course_list_frame",
    "extract_course_list",
]

if __name__ == "__main__":
    run()
