#!/usr/bin/env python3
"""爬虫逻辑包。"""
from spider.browser import (
    load_cookies,
    load_state,
    save_state,
    wait_stable,
    click_when_ready,
    debug_screenshot,
    dump_frame_html,
    wait_for_iframe_content,
    scroll_frame_to_bottom,
)
from spider.homework import (
    enter_homework_tab,
    is_insight_link,
    extract_homework_items,
    click_homework_item,
    find_homework_list_frame,
    collect_all_homeworks,
)
from spider.questions import (
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
)
from spider.runner import load_homework_list, run, save_homework, standalone_login

__all__ = [
    # browser
    "load_cookies",
    "load_state",
    "save_state",
    "wait_stable",
    "click_when_ready",
    "debug_screenshot",
    "dump_frame_html",
    "wait_for_iframe_content",
    "scroll_frame_to_bottom",
    # homework
    "enter_homework_tab",
    "is_insight_link",
    "extract_homework_items",
    "click_homework_item",
    "find_homework_list_frame",
    "collect_all_homeworks",
    # questions
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
    # runner
    "load_homework_list",
    "run",
    "save_homework",
    "standalone_login",
]
