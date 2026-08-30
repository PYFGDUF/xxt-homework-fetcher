# -*- coding: utf-8 -*-
"""spider.homework 纯逻辑单元测试：链接过滤、总量解析（不依赖真实浏览器）。"""
import pytest

from spider.homework import is_insight_link, is_boilerplate_title, read_homework_total


# ---------------- is_insight_link（智能分析链接过滤） ----------------

def test_insight_none_or_empty():
    assert is_insight_link(None) is False
    assert is_insight_link("") is False


def test_insight_detects_analysis_domain_and_path():
    assert is_insight_link("https://stat2-ans.chaoxing.com/analysis/123") is True
    assert is_insight_link("https://x.com/study-knowledge/foo") is True
    assert is_insight_link("https://mooc2-ans.chaoxing.com/ans?courseid=9") is True


def test_insight_detects_keywords():
    assert is_insight_link("https://x.com/path/analysis") is True
    assert is_insight_link("https://x.com/a/analyse/b") is True
    assert is_insight_link("https://x.com/knowledge/1") is True


def test_insight_detects_text():
    assert is_insight_link("https://x.com/work/home", text="智能分析") is True
    assert is_insight_link("https://x.com/work/home", text="分析") is True


def test_normal_work_link_not_insight():
    url = "https://mooc2-ans.chaoxing.com/mooc2-ans/work/doHomeWorkNew?courseid=1&workid=2"
    assert is_insight_link(url) is False


# ---------------- is_boilerplate_title（非作业提示文案过滤） ----------------

@pytest.mark.parametrize("bad", [
    "相似度分析", "请勿抄袭", "提交的作业将经过xx", "大雅",
    "温馨提示", "公告", "暂无作业", "没有更多", "敬请期待",
])
def test_boilerplate_true(bad):
    assert is_boilerplate_title(bad) is True


@pytest.mark.parametrize("ok", [
    "第一章 课后作业", "第三周测验", "", "作业提交截止",
])
def test_boilerplate_false(ok):
    assert is_boilerplate_title(ok) is False


# ---------------- read_homework_total（总量解析） ----------------

class FakeFrame:
    """最小 frame 替身：只暴露 evaluate，返回预置 body 文本。"""

    def __init__(self, body: str, raise_error: bool = False):
        self._body = body
        self._raise = raise_error

    def evaluate(self, js):
        if self._raise:
            raise RuntimeError("network error")
        return self._body


def test_total_context_pattern():
    # 「已完成 X / 共 Y 份」→ (X, Y)
    assert read_homework_total(FakeFrame("已完成 33 / 共 41 份作业")) == (33, 41)
    # 只有「共 Y 份」，无已完成数 → (None, Y)
    assert read_homework_total(FakeFrame("共 41 份")) == (None, 41)


def test_total_score_pattern():
    assert read_homework_total(FakeFrame("已完成 33/41")) == (33, 41)
    assert read_homework_total(FakeFrame("已完成：5 / 20")) == (5, 20)


def test_total_fallback_slash():
    assert read_homework_total(FakeFrame("第 34 / 42 页")) == (34, 42)


def test_total_no_match():
    assert read_homework_total(FakeFrame("没有任何统计信息")) == (None, None)


def test_total_implausible_total_ignored():
    # 总量高达 999999，超出合理上限，不强加校验
    assert read_homework_total(FakeFrame("999999 / 100")) == (None, None)


def test_total_done_exceeds_total_ignored():
    # 已完成数大于总数属于脏数据，不返回
    assert read_homework_total(FakeFrame("42 / 41")) == (None, None)


def test_total_eval_error_returns_none():
    assert read_homework_total(FakeFrame("", raise_error=True)) == (None, None)