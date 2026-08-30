# -*- coding: utf-8 -*-
"""core.active_queue 运行期动态待抓队列的完整单元测试。

覆盖：初始注册、运行中追加、去重（含 id/url 身份键、mark_active_done 防重加）、
越界读取、清空收尾、注册状态切换，以及「模拟抓取线程 + GUI 追加线程」的动态迭代场景
（新作业自动进入队列并被处理、总量随增长更新、重复项不被二次处理）。
"""
import threading

import pytest

import core.active_queue as aq


@pytest.fixture(autouse=True)
def _reset_queue():
    """每个用例前后清空动态队列全局态，避免用例间相互污染。"""
    aq.clear_active_queue()
    yield
    aq.clear_active_queue()


def _hw(_id, url=None, list_url=None, title=""):
    hw = {"id": str(_id), "title": title or f"作业{_id}"}
    if url:
        hw["url"] = url
    if list_url:
        hw["list_url"] = list_url
    return hw


# ---------------- _key：身份键解析 ----------------

def test_key_prefers_id():
    assert aq._key({"id": "42", "url": "u", "list_url": "l"}) == "42"


def test_key_falls_back_to_url_when_no_id():
    assert aq._key({"url": "https://x/w", "title": "t"}) == "https://x/w"


def test_key_empty():
    assert aq._key({}) == ""
    assert aq._key({"title": "t"}) == ""


# ---------------- register_active_homeworks ----------------

def test_register_sets_items_and_registered_flag():
    items = [_hw(1), _hw(2)]
    aq.register_active_homeworks(items)
    assert aq.is_active_registered() is True
    assert aq.active_queue_length() == 2
    assert aq.active_get_homework(0)["id"] == "1"


def test_register_copies_inputs():
    items = [_hw(1)]
    aq.register_active_homeworks(items)
    # 修改外部列表不应影响已注册的队列
    items.clear()
    assert aq.active_queue_length() == 1


def test_register_resets_previous_state():
    aq.register_active_homeworks([_hw(1), _hw(2)])
    aq.add_active_homeworks([_hw(3)])
    aq.register_active_homeworks([_hw(9)])
    assert aq.active_queue_length() == 1
    assert aq.active_get_homework(0)["id"] == "9"


# ---------------- add_active_homeworks：追加与去重 ----------------

def test_add_before_register_returns_zero():
    assert aq.add_active_homeworks([_hw(1)]) == 0
    assert aq.active_queue_length() == 0


def test_add_new_items_appends_to_tail():
    aq.register_active_homeworks([_hw(1), _hw(2)])
    added = aq.add_active_homeworks([_hw(3), _hw(4)])
    assert added == 2
    assert aq.active_queue_length() == 4
    assert [aq.active_get_homework(i)["id"] for i in range(4)] == ["1", "2", "3", "4"]


def test_add_skips_items_already_in_initial_set():
    aq.register_active_homeworks([_hw(1)])
    assert aq.add_active_homeworks([_hw(1), _hw(2)]) == 1
    assert aq.active_queue_length() == 2


def test_add_skips_already_added():
    aq.register_active_homeworks([_hw(1)])
    assert aq.add_active_homeworks([_hw(2)]) == 1
    # 同一作业重复追加应被去重
    assert aq.add_active_homeworks([_hw(2)]) == 0
    assert aq.active_queue_length() == 2


def test_add_ignores_non_dict_entries():
    aq.register_active_homeworks([_hw(1)])
    assert aq.add_active_homeworks(["not-a-dict", _hw(2), None]) == 1
    assert aq.active_queue_length() == 2


def test_add_ignores_entry_without_id_and_url():
    aq.register_active_homeworks([_hw(1)])
    assert aq.add_active_homeworks([{"title": "无身份键"}]) == 0
    assert aq.active_queue_length() == 1


def test_add_dedup_by_url_when_id_absent():
    # 无 id 但有 url 的作业，用 url 作为身份键去重
    aq.register_active_homeworks([{"url": "https://x/w1", "title": "A"}])
    assert aq.add_active_homeworks([{"url": "https://x/w1", "title": "A2"}]) == 0
    assert aq.active_queue_length() == 1


def test_add_dedup_by_id_when_different_url_conflict():
    # 同一 id 即使 url 不同也只保留一份（id 优先作为身份键）
    aq.register_active_homeworks([_hw(5, url="https://a")])
    assert aq.add_active_homeworks([_hw(5, url="https://b")]) == 0
    assert aq.active_queue_length() == 1


# ---------------- active_get_homework / active_queue_length ----------------

def test_get_out_of_bound_returns_none():
    aq.register_active_homeworks([_hw(1)])
    assert aq.active_get_homework(-1) is None
    assert aq.active_get_homework(1) is None


def test_get_returns_copy():
    aq.register_active_homeworks([_hw(1)])
    got = aq.active_get_homework(0)
    got["id"] = "999"
    assert aq.active_get_homework(0)["id"] == "1"


# ---------------- mark_active_done：处理中防重加 ----------------

def test_mark_done_prevents_readd():
    aq.register_active_homeworks([])
    hw = _hw(7)
    aq.mark_active_done(hw)
    assert aq.add_active_homeworks([hw]) == 0
    assert aq.active_queue_length() == 0


def test_mark_done_with_no_key_does_not_poison():
    aq.register_active_homeworks([_hw(1)])
    aq.mark_active_done({"title": "无身份"})
    assert aq.add_active_homeworks([_hw(1)]) == 0
    assert aq.active_queue_length() == 1


# ---------------- clear_active_queue ----------------

def test_clear_resets_all_state():
    aq.register_active_homeworks([_hw(1), _hw(2)])
    aq.clear_active_queue()
    assert aq.is_active_registered() is False
    assert aq.active_queue_length() == 0
    # 清空后无法再追加
    assert aq.add_active_homeworks([_hw(1)]) == 0


# ---------------- 动态迭代：模拟抓取线程 + GUI 追加 ----------------

def _drain_with_growth_support(pending_at_tail: dict):
    """模拟 runner 的动态 while 迭代 + _wait_for_active_growth 语义。

    pending_at_tail: {tail_idx: [新作业...]} —— 当循环迭代到尾部（idx == len）
    时，模拟 GUI 在此时追加这些新作业（等价于共享线程并发写入队列）；
    若尾部无新增则判定可以结束（对应 _wait_for_active_growth 返回 False）。
    返回 (processed_ids, max_total_seen)。
    """
    processed = []
    idx = 0
    pending = {k: list(v) for k, v in pending_at_tail.items()}
    max_total = aq.active_queue_length()

    while True:
        # 队列迭代到尾部：进入等待窗口，期间 GUI 可能追加新作业
        if idx >= aq.active_queue_length():
            grew = False
            if pending.get(idx):
                added = aq.add_active_homeworks(pending[idx])
                pending[idx] = []
                grew = added > 0
            if not grew:
                break  # 窗口内无新增 -> 判定已处理完（_wait_for_active_growth False）
            max_total = aq.active_queue_length()
            continue

        hw = aq.active_get_homework(idx)
        idx += 1
        max_total = max(max_total, aq.active_queue_length())
        aq.mark_active_done(hw)
        processed.append(hw)

    return [h["id"] for h in processed], max_total


def test_dynamic_add_picked_up_during_iteration():
    aq.register_active_homeworks([_hw(1, title="A"), _hw(2, title="B")])
    # GUI 在抓取线程处理完前 2 个后（到达尾部时）追加两个新作业
    ids, total = _drain_with_growth_support({2: [_hw(3, title="C"), _hw(4, title="D")]})
    assert ids == ["1", "2", "3", "4"]
    assert total == 4


def test_dynamic_add_total_grows():
    aq.register_active_homeworks([_hw(1)])
    # 先到达尾部追加作业2，处理完后再次到达尾部追加作业3
    ids, total = _drain_with_growth_support({1: [_hw(2)], 2: [_hw(3)]})
    assert ids == ["1", "2", "3"]
    assert total == 3


def test_dynamic_add_of_already_processed_is_not_reprocessed():
    aq.register_active_homeworks([_hw(1), _hw(2)])
    # GUI 误把已处理完的作业 1、2 以及一个新作业 3 一起追加：只应处理新作业 3
    ids, total = _drain_with_growth_support({2: [_hw(1), _hw(2), _hw(3)]})
    assert ids == ["1", "2", "3"]
    assert total == 3


def test_no_growth_drains_initial_once():
    aq.register_active_homeworks([_hw(1), _hw(2)])
    ids, total = _drain_with_growth_support({})
    assert ids == ["1", "2"]
    assert total == 2


def test_empty_registered_queue_drains_to_nothing():
    aq.register_active_homeworks([])
    ids, total = _drain_with_growth_support({})
    assert ids == []
    assert total == 0


# ---------------- 线程安全冒烟：并发追加与读取不破环一致性 ----------------

def test_concurrent_add_and_grow_is_safe():
    aq.register_active_homeworks([_hw("init")])
    errors = []

    def adder(offset, count):
        try:
            for i in range(count):
                aq.add_active_homeworks([_hw(offset + i)])
        except Exception as e:  # pragma: no cover
            errors.append(e)

    # 各线程 id 从 1..4000，与初始 "init" 不冲突
    threads = [threading.Thread(target=adder, args=(1 + i * 500, 500)) for i in range(8)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()

    assert not errors
    assert aq.active_queue_length() == 1 + 8 * 500
    # 身份键无重复
    keys = {aq._key(aq.active_get_homework(i)) for i in range(aq.active_queue_length())}
    assert len(keys) == aq.active_queue_length()