#!/usr/bin/env python3
"""日志配置与输出重定向。"""
from __future__ import annotations

import functools
import logging
import logging.handlers
import os
import sys


def setup_logging() -> logging.Logger:
    """配置分级日志：文件按大小轮转，控制台只输出 INFO 及以上。"""
    log_dir = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "logs")
    os.makedirs(log_dir, exist_ok=True)
    log_file = os.path.join(log_dir, "chaoxing_spider.log")

    logger = logging.getLogger("chaoxing_spider")
    logger.setLevel(logging.DEBUG)

    if not logger.handlers:
        formatter = logging.Formatter("%(asctime)s [%(levelname)s] %(message)s", datefmt="%Y-%m-%d %H:%M:%S")

        # 文件 handler：DEBUG 及以上，按 10MB 轮转，保留 5 个备份
        file_handler = logging.handlers.RotatingFileHandler(
            log_file, maxBytes=10 * 1024 * 1024, backupCount=5, encoding="utf-8"
        )
        file_handler.setLevel(logging.DEBUG)
        file_handler.setFormatter(formatter)

        # 控制台 handler：INFO 及以上
        console_handler = logging.StreamHandler()
        console_handler.setLevel(logging.INFO)
        console_handler.setFormatter(formatter)

        logger.addHandler(file_handler)
        logger.addHandler(console_handler)

    return logger


LOGGER = setup_logging()


class TeeStdout:
    """将 stdout 同时输出到原始目标（GUI 日志框/终端）和日志文件。

    注意：这里只把 print 写进文件日志，不再调用 LOGGER.info 转发，
    否则在桥接场景下会与事件流重复（print 已由 original 到达 GUI）。
    """

    def __init__(self, original, logger: logging.Logger):
        self.original = original
        self.logger = logger

    def _log_to_file(self, msg: str):
        rec = logging.LogRecord("chaoxing_spider", logging.INFO, "", 0, msg, None, None)
        for h in self.logger.handlers:
            if isinstance(h, logging.handlers.RotatingFileHandler):
                try:
                    h.emit(rec)
                except Exception:
                    pass

    def write(self, s: str) -> int:
        self.original.write(s)
        stripped = s.strip()
        if stripped:
            self._log_to_file(stripped)
        return len(s)

    def flush(self):
        self.original.flush()

    def __getattr__(self, name):
        return getattr(self.original, name)


def with_logging(func):
    """装饰器：运行期间将 print 输出同时记录到日志文件。保留原函数签名。"""
    @functools.wraps(func)
    def wrapper(*args, **kwargs):
        original_stdout = sys.stdout
        sys.stdout = TeeStdout(original_stdout, LOGGER)
        try:
            return func(*args, **kwargs)
        finally:
            sys.stdout = original_stdout
    return wrapper
