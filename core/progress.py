#!/usr/bin/env python3
"""进度跟踪与断点续传。"""
from __future__ import annotations

import datetime
import hashlib
import json
import os
import time

from core.config import PROGRESS_FILE, get_force_regrab


# 进度文件最多保留的记录数，防止无限增长
MAX_PROGRESS_RECORDS = 500
# 进度记录保留天数，超过此天数未更新的条目会被清理
MAX_PROGRESS_DAYS = 90


class ProgressTracker:
    """记录每个作业的抓取状态，支持断点续传与自动清理。"""

    def __init__(self, path: str = None):
        self.path = path or os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", PROGRESS_FILE)
        self.data = self._load()
        self._migrate()
        self._clean()

    def _load(self) -> dict:
        if not os.path.exists(self.path):
            return {"version": 1, "items": {}}
        try:
            with open(self.path, "r", encoding="utf-8") as f:
                data = json.load(f)
            if not isinstance(data, dict):
                return {"version": 1, "items": {}}
            data.setdefault("version", 1)
            data.setdefault("items", {})
            return data
        except Exception:
            return {"version": 1, "items": {}}

    def _migrate(self):
        """简单的版本迁移：如果数据结构不兼容则重置。"""
        version = self.data.get("version", 1)
        if version != 1:
            self.data = {"version": 1, "items": {}}

    def _clean(self):
        """清理过期和过多的历史记录。"""
        items = self.data.get("items", {})
        if not items:
            return

        now = datetime.datetime.now()
        cutoff_date = now - datetime.timedelta(days=MAX_PROGRESS_DAYS)
        cutoff_str = cutoff_date.strftime("%Y%m%d_%H%M%S")

        # 过滤掉超过保留天数的记录
        valid = {
            k: v for k, v in items.items()
            if v.get("last_run", "19700101_000000") >= cutoff_str
        }

        # 如果仍超过最大记录数，按 last_run 保留最新的
        if len(valid) > MAX_PROGRESS_RECORDS:
            sorted_items = sorted(
                valid.items(),
                key=lambda kv: kv[1].get("last_run", "19700101_000000"),
                reverse=True,
            )
            valid = dict(sorted_items[:MAX_PROGRESS_RECORDS])

        removed = len(items) - len(valid)
        if removed > 0:
            self.data["items"] = valid
            print(f"[info] progress.json 已清理 {removed} 条过期/冗余记录")
            self.save()

    def save(self):
        self.data["last_updated"] = time.strftime("%Y-%m-%dT%H:%M:%S")
        try:
            with open(self.path, "w", encoding="utf-8") as f:
                json.dump(self.data, f, ensure_ascii=False, indent=2)
        except Exception as e:
            print(f"[warn] 保存进度文件失败：{e}")

    @staticmethod
    def _url_key(url: str) -> str:
        if not url:
            return ""
        return hashlib.md5(url.encode("utf-8")).hexdigest()

    def get(self, url: str) -> dict:
        if not url:
            return {}
        return self.data["items"].get(self._url_key(url), {})

    def get_status(self, url: str) -> str:
        return self.get(url).get("status", "pending")

    def set(self, url: str, title: str, status: str, output_dir: str = None, word_file: str = None):
        if not url:
            return
        key = self._url_key(url)
        item = self.data["items"].get(key, {})
        item.update({
            "url": url,
            "title": title,
            "status": status,
            "last_run": time.strftime("%Y%m%d_%H%M%S"),
        })
        if output_dir:
            item["output_dir"] = output_dir
        if word_file:
            item["word_file"] = word_file
        self.data["items"][key] = item
        self.save()
        # 每次写入后检查是否需要清理
        self._clean()

    def is_completed(self, url: str) -> bool:
        return self.get_status(url) == "completed"

    def filter_homeworks(self, homeworks: list, skip_completed: bool = True) -> list:
        """过滤作业列表，返回需要抓取的作业。"""
        result = []
        for hw in homeworks:
            url = hw.get("url", "")
            if not url:
                continue
            if skip_completed and self.is_completed(url) and not get_force_regrab():
                continue
            result.append(hw)
        return result

    def list_all(self) -> list:
        """返回所有已记录作业（按 title 排序）。"""
        return sorted(self.data["items"].values(), key=lambda x: x.get("title", ""))

    def clear(self):
        """清空全部历史记录。"""
        self.data["items"] = {}
        self.save()
