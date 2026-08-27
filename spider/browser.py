#!/usr/bin/env python3
"""浏览器状态、Cookie 与页面通用工具。"""
from __future__ import annotations

import json
import os
import time

from playwright.sync_api import Page

from core.config import (
    ACTION_TIMEOUT,
    COOKIE_FILE,
    WAIT_TIMEOUT,
    debug_dir,
    load_state as _load_state,
    save_state as _save_state,
)
from core.utils import safe_filename


# 重导出浏览器状态加载/保存，便于 spider 包统一使用
load_state = _load_state
save_state = _save_state


def load_cookies() -> list:
    """从 cookies.txt 解析为 Playwright 可用的 cookie 列表。"""
    if not os.path.exists(COOKIE_FILE):
        return []
    cookies = []
    with open(COOKIE_FILE, "r", encoding="utf-8") as f:
        raw = f.read().strip()
    if raw.startswith("["):
        return json.loads(raw)
    for pair in raw.split(";"):
        pair = pair.strip()
        if "=" not in pair:
            continue
        k, v = pair.split("=", 1)
        cookies.append({"name": k.strip(), "value": v.strip(), "domain": ".chaoxing.com", "path": "/"})
    return cookies


def debug_screenshot(page_or_frame, name: str):
    """失败时截图，方便排查页面结构。兼容 Page 和 Frame。"""
    try:
        ddir = debug_dir()
        os.makedirs(ddir, exist_ok=True)
        path = os.path.join(ddir, f"{int(time.time())}_{safe_filename(name)}.png")
        # Frame 没有 screenshot 方法，要用所属的 page
        if hasattr(page_or_frame, "page") and not isinstance(page_or_frame, Page):
            page_or_frame.page.screenshot(path=path, full_page=True)
        else:
            page_or_frame.screenshot(path=path, full_page=True)
        print(f"    [debug] 已截图：{path}")
    except Exception as e:
        print(f"    [debug] 截图失败：{e}")


def wait_stable(page_or_frame, timeout_ms: int = 5000, on_progress=None):
    """等待页面网络/渲染基本稳定。

    提速优化：与旧版「等 networkidle 后固定 sleep timeout_ms」不同，这里在等出 networkidle
    之后，轮询页面文本，连续多次采样内容不变（渲染已收敛）即提前返回，最多等待 timeout_ms。
    页面早已稳定时无需再付那一段固定等待，从而显著减少抓取耗时。

    on_progress：可选回调，接收 0..1 表示本次等待的完成度，用于在等待期间把进度平滑
    推进（消除"打开作业时进度停在 0%"的空窗）。仅在调用方显式传入时生效。
    """
    start = time.time()
    if on_progress is not None:
        on_progress(0.0)
    try:
        page_or_frame.wait_for_load_state("networkidle", timeout=WAIT_TIMEOUT)
    except Exception as e:
        print(f"    [debug] networkidle 未在 {WAIT_TIMEOUT}ms 内达成（忽略，继续轮询稳定）：{e}")

    # 轮询直至页面内容收敛：连续 SAME_TEXT_STREAK 次采样到的正文长度一致即认为稳定。
    SAME_TEXT_STREAK = 2
    INTERVAL = 0.15
    span = max(0.001, timeout_ms / 1000.0)
    last_len = None
    streak = 0
    while time.time() - start < span:
        try:
            text = page_or_frame.locator("body").inner_text(timeout=1000)
            length = len(text.strip())
        except Exception:
            text, length = "", 0
        if length == last_len:
            streak += 1
            if streak >= SAME_TEXT_STREAK:
                break
        else:
            streak = 0
        last_len = length
        time.sleep(INTERVAL)
        if on_progress is not None:
            on_progress(min(1.0, (time.time() - start) / span))
    if on_progress is not None:
        on_progress(1.0)


def click_when_ready(page, locator, timeout: int = ACTION_TIMEOUT):
    """安全点击，等待元素可见可点击。"""
    locator.first.wait_for(state="visible", timeout=timeout)
    locator.first.click(timeout=timeout)


def dump_frame_html(page_or_frame, name: str):
    """把 frame 的 HTML 保存到 debug，用于分析页面结构。"""
    try:
        html = page_or_frame.content()
        ddir = debug_dir()
        os.makedirs(ddir, exist_ok=True)
        path = os.path.join(ddir, f"{int(time.time())}_{safe_filename(name)}.html")
        with open(path, "w", encoding="utf-8") as f:
            f.write(html)
        print(f"    [debug] 已保存 HTML：{path}")
    except Exception as e:
        print(f"    [debug] 保存 HTML 失败：{e}")


def wait_for_iframe_content(page_or_frame, timeout_ms: int = 10_000):
    """等待 iframe 内动态内容加载。"""
    deadline = time.time() + timeout_ms / 1000
    while time.time() < deadline:
        try:
            text = page_or_frame.locator("body").inner_text(timeout=2000)
            # 有文字内容且不是纯空白，认为加载完成
            if len(text.strip()) > 50:
                return
        except Exception as e:
            print(f"    [debug] wait_for_iframe_content 读取 body 失败（重试中）：{e}")
        time.sleep(0.5)


def scroll_frame_to_bottom(page_or_frame, step: int = 800):
    """在 frame 内滚动到底部，触发懒加载。"""
    try:
        page_or_frame.evaluate("""
            ({step}) => {
                return new Promise(resolve => {
                    let scrollTop = 0;
                    const timer = setInterval(() => {
                        const max = document.body.scrollHeight - window.innerHeight;
                        scrollTop += step;
                        window.scrollTo(0, scrollTop);
                        if (scrollTop >= max) {
                            clearInterval(timer);
                            resolve(document.body.scrollHeight);
                        }
                    }, 300);
                });
            }
        """, {"step": step})
    except Exception as e:
        print(f"    [warn] 滚动失败：{e}")
