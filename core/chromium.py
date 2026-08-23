#!/usr/bin/env python3
"""
无头浏览器目录管理。

轻量化分发策略：App 只内置无头浏览器（chromium_headless_shell）与 ffmpeg，
日常抓取（扫码登录与作业抓取统一走 headless）无需完整 Chromium。

v1.3 起完全脱离“下载完整 Chromium 登录组件”的逻辑，本模块仅托管浏览器根目录。
"""
from __future__ import annotations

import os

_ENV = "PLAYWRIGHT_BROWSERS_PATH"

# 完整 Chromium 目录名（历史遗留，用于在复制时跳过，避免误拷），
# 需与 Playwright 版本/PW_PIN 对齐。
_CHROMIUM_DIR = "chromium-1223"


def browsers_dir() -> str:
    """浏览器根目录：优先取 PLAYWRIGHT_BROWSERS_PATH（用户可写），否则用系统默认缓存目录。"""
    env = os.environ.get(_ENV)
    if env:
        return env
    return os.path.expanduser(os.path.join("~", "Library", "Caches", "ms-playwright"))