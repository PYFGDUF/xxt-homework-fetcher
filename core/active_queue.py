#!/usr/bin/env python3
"""运行期动态待抓队列。

允许 GUI 在「抓取进行中」向引擎追加新的未抓取作业，引擎正在跑的主循环会
在索引迭代中自动把新追加的作业纳入抓取队列，实现「运行中新增作业自动入队」。

线程安全：Swift/GUI 通过 bridge 主线程调用 add_active_homeworks() 追加，
Playwright 抓取线程通过 active_get_homework()/active_queue_length() 读取，
两者在不同线程访问同一列表，统一用 RLock 保护。
"""
from __future__ import annotations

import threading

_lock = threading.RLock()
_items: list[dict] = []       # 待抓队列（可按索引读取，尾部会被运行中追加）
_done: set = set()            # 已入队/已处理作业的身份键，用于去重，防重复加入
_registered = False           # 本次运行是否已装载初始队列
_claim_idx = 0                # worker 并发领取的“下一个未认领”下标（串行迭代不受影响）


def _key(hw: dict) -> str:
    return str(hw.get("id") or hw.get("url") or "")


def register_active_homeworks(items: list[dict]):
    """一次抓取开始前装载初始队列，并重置去重集合与领取下标。"""
    global _items, _done, _registered, _claim_idx
    with _lock:
        _items = [dict(i) for i in items]
        _done = {_key(i) for i in _items}
        _registered = True
        _claim_idx = 0


def add_active_homeworks(items) -> int:
    """运行中加入新作业，仅追加「未入队、未处理」的项。返回实际新增个数。"""
    global _items
    added = 0
    with _lock:
        if not _registered:
            return 0
        for it in items:
            if not isinstance(it, dict):
                continue
            k = _key(it)
            if not k or k in _done:
                continue
            _done.add(k)
            _items.append(dict(it))
            added += 1
    return added


def active_queue_length() -> int:
    """当前队列长度（含运行中新增项）。"""
    with _lock:
        return len(_items)


def active_get_homework(index: int) -> dict | None:
    """按下标读取队列项；越界返回 None。返回副本，避免调用方在锁外改动队列内部状态。"""
    with _lock:
        if index < 0 or index >= len(_items):
            return None
        return dict(_items[index])


def mark_active_done(hw: dict) -> None:
    """记录一个作业已进入处理流程，防止 GUI 对已处理的作业重复加入。"""
    with _lock:
        k = _key(hw)
        if k:
            _done.add(k)


def active_claim_next() -> tuple:
    """并发模式下原子领取下一个未处理作业。

    返回 (hw, index, queue_len)：hw 为队列项副本；队列已到底或已停止则 hw 为
    None。index 为该作业在队列中的位置（1 基），queue_len 为当前队列长度。
    worker 线程之间通过该函数互斥领取，保证同一作业只被一个 worker 处理。
    """
    global _claim_idx
    with _lock:
        if _claim_idx >= len(_items):
            return None, _claim_idx, len(_items)
        item = dict(_items[_claim_idx])
        k = _key(item)
        if k:
            _done.add(k)
        _claim_idx += 1
        return item, _claim_idx, len(_items)


def active_claim_index() -> int:
    """返回当前已领取到的下标（用于决定是否继续等待动态新增）。"""
    with _lock:
        return _claim_idx


def is_active_registered() -> bool:
    """当前是否有进行中的动态抓取队列。"""
    with _lock:
        return _registered


def clear_active_queue() -> None:
    """抓取结束/异常收尾时清空动态队列。"""
    global _items, _done, _registered, _claim_idx
    with _lock:
        _items = []
        _done = set()
        _registered = False
        _claim_idx = 0