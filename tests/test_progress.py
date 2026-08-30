"""core.progress 断点续传 / 自动清理 / 作业过滤单元测试。"""
import json
import time

import pytest

import core.config as config
from core.progress import (
    ProgressTracker,
    MAX_PROGRESS_RECORDS,
    MAX_PROGRESS_DAYS,
)


def _now_str():
    return time.strftime("%Y%m%d_%H%M%S")


# ---------------- 基础读写 ----------------

def test_new_tracker_has_empty_items(tmp_path):
    t = ProgressTracker(str(tmp_path / "progress.json"))
    assert t.data["items"] == {}
    assert t.path == str(tmp_path / "progress.json")


def test_set_and_get(tmp_path):
    t = ProgressTracker(str(tmp_path / "progress.json"))
    t.set("http://x/work/1", "作业一", "completed", output_dir="/o", word_file="/o/作业一.docx")
    item = t.get("http://x/work/1")
    assert item["status"] == "completed"
    assert item["title"] == "作业一"
    assert item["output_dir"] == "/o"
    assert item["word_file"] == "/o/作业一.docx"
    assert item["last_run"]


def test_get_status_and_is_completed(tmp_path):
    t = ProgressTracker(str(tmp_path / "progress.json"))
    assert t.get_status("http://x/work/2") == "pending"
    assert not t.is_completed("http://x/work/2")
    t.set("http://x/work/2", "作业二", "completed")
    assert t.is_completed("http://x/work/2")


def test_get_empty_url(tmp_path):
    t = ProgressTracker(str(tmp_path / "progress.json"))
    assert t.get("") == {}
    assert t.get_status("") == "pending"
    t.set("", "无 URL", "completed")  # 空 URL 应静默忽略
    assert t.data["items"] == {}


def test_url_key_is_md5_deterministic(tmp_path):
    t = ProgressTracker(str(tmp_path / "progress.json"))
    assert t._url_key("http://x/a") == t._url_key("http://x/a")
    assert t._url_key("http://x/a") != t._url_key("http://x/b")


def test_clear(tmp_path):
    t = ProgressTracker(str(tmp_path / "progress.json"))
    t.set("http://x/work/3", "作业三", "completed")
    t.clear()
    assert t.data["items"] == {}


# ---------------- 断点/损坏文件兜底 ----------------

def test_corrupted_file_falls_back_to_empty(tmp_path):
    p = tmp_path / "progress.json"
    p.write_text("{not valid json", encoding="utf-8")
    t = ProgressTracker(str(p))
    assert t.data == {"version": 1, "items": {}}


def test_non_dict_file_falls_back(tmp_path):
    p = tmp_path / "progress.json"
    p.write_text('["a"]', encoding="utf-8")
    t = ProgressTracker(str(p))
    assert t.data == {"version": 1, "items": {}}


def test_incompatible_version_resets(tmp_path):
    p = tmp_path / "progress.json"
    p.write_text(json.dumps({"version": 99, "items": {"k": {}}}), encoding="utf-8")
    t = ProgressTracker(str(p))
    assert t.data == {"version": 1, "items": {}}


def test_persists_across_instances(tmp_path):
    p = str(tmp_path / "progress.json")
    t1 = ProgressTracker(p)
    t1.set("http://x/work/9", "作业九", "completed")
    t2 = ProgressTracker(p)
    assert t2.is_completed("http://x/work/9")


# ---------------- filter_homeworks ----------------

def _hw(url, title="作业"):
    return {"url": url, "title": title}


def test_filter_skips_completed(tmp_path, monkeypatch):
    monkeypatch.setattr(config, "FORCE_REGRAB", False)
    t = ProgressTracker(str(tmp_path / "progress.json"))
    t.set("http://x/done", "已抓", "completed")
    homeworks = [_hw("http://x/done"), _hw("http://x/pending")]
    assert t.filter_homeworks(homeworks) == [_hw("http://x/pending")]


def test_filter_keeps_all_when_force_regrab(tmp_path, monkeypatch):
    monkeypatch.setattr(config, "FORCE_REGRAB", True)
    t = ProgressTracker(str(tmp_path / "progress.json"))
    t.set("http://x/done", "已抓", "completed")
    homeworks = [_hw("http://x/done"), _hw("http://x/pending")]
    assert t.filter_homeworks(homeworks) == homeworks


def test_filter_keeps_all_when_skip_completed_false(tmp_path, monkeypatch):
    monkeypatch.setattr(config, "FORCE_REGRAB", False)
    t = ProgressTracker(str(tmp_path / "progress.json"))
    t.set("http://x/done", "已抓", "completed")
    homeworks = [_hw("http://x/done")]
    assert t.filter_homeworks(homeworks, skip_completed=False) == homeworks


def test_filter_drops_missing_url(tmp_path):
    t = ProgressTracker(str(tmp_path / "progress.json"))
    homeworks = [{"url": ""}, {"url": None}, {"url": "http://x/ok"}]
    assert t.filter_homeworks(homeworks) == [{"url": "http://x/ok"}]


# ---------------- list_all ----------------

def test_list_all_sorted_by_title(tmp_path):
    t = ProgressTracker(str(tmp_path / "progress.json"))
    t.set("http://x/b", "作业B", "completed")
    t.set("http://x/a", "作业A", "failed")
    titles = [i["title"] for i in t.list_all()]
    assert titles == ["作业A", "作业B"]


# ---------------- 自动清理 ----------------

def test_clean_removes_expired_days(tmp_path):
    t = ProgressTracker(str(tmp_path / "progress.json"))
    t.data["items"] = {
        "old": {"last_run": "19700101_000000"},
        "new": {"last_run": _now_str()},
    }
    t._clean()
    assert "old" not in t.data["items"]
    assert "new" in t.data["items"]


def test_clean_keeps_fresh_and_saves(tmp_path):
    p = str(tmp_path / "progress.json")
    t = ProgressTracker(p)
    t.data["items"] = {
        "old": {"last_run": "19700101_000000"},
        "new": {"last_run": _now_str()},
    }
    t._clean()
    assert "old" not in t.data["items"]
    # 清理触发了 save，落盘应只剩新记录
    t2 = ProgressTracker(p)
    assert "old" not in t2.data["items"]


def test_clean_limit_max_records(tmp_path):
    t = ProgressTracker(str(tmp_path / "progress.json"))
    items = {}
    # 造 MAX_PROGRESS_RECORDS + 10 条，用「近期」时间戳（落在 90 天保留期内），
    # last_run 随索引递增，确保只触发条数上限裁剪而非天数清理。
    base = time.time() - (MAX_PROGRESS_RECORDS + 20)
    for i in range(MAX_PROGRESS_RECORDS + 10):
        items[f"k{i}"] = {"last_run": time.strftime("%Y%m%d_%H%M%S", time.gmtime(base + i))}
    t.data["items"] = items
    t._clean()
    assert len(t.data["items"]) == MAX_PROGRESS_RECORDS
    # 裁剪后保留最新 MAX_PROGRESS_RECORDS 条 → 最早的 k0..k9 被裁掉
    keys = sorted(t.data["items"].keys(), key=lambda k: t.data["items"][k]["last_run"])
    assert keys[0] == "k10"


def test_clean_empty_noop(tmp_path):
    t = ProgressTracker(str(tmp_path / "progress.json"))
    t.data["items"] = {}
    t._clean()  # 不应抛异常


# ---------------- 设置持久化（set 触发 auto-clean） ----------------

def test_set_triggers_clean(tmp_path):
    t = ProgressTracker(str(tmp_path / "progress.json"))
    t.data["items"] = {"old": {"last_run": "19700101_000000"}}
    t.set("http://x/work/7", "作业七", "completed")
    assert "old" not in t.data["items"]
    assert "http://x/work/7" in {c["url"] for c in t.list_all()}