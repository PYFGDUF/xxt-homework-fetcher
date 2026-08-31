#!/usr/bin/env python3
"""抓取耗时基准：相同 5 个作业，对比「单线程串行」 vs 「双线程 worker」。

只抓题（extract_all_questions），不保存 Word / 不写 progress / 不覆盖登录态，
用于纯粹对比网络往返（页面加载 + 翻页 + 答题展开）的真实墙钟耗时。

用法:
    <venv-python> script/concurrency_bench.py [数量]
以 {App Support}/XxtApp 为 cwd 运行（state.json/progress.json 相对 cwd 解析）。
不带数量参数默认取 5 个作业。
"""
from __future__ import annotations

import json
import os
import sys
import threading
import time

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(os.path.abspath(__file__)), "..")))

from playwright.sync_api import sync_playwright  # noqa: E402

from core.config import load_state  # noqa: E402
from core.utils import is_login_page  # noqa: E402
from spider.questions import extract_all_questions  # noqa: E402

_JOB_TIMEOUT_SEC = 300
_STATE = None  # 登录态缓存，所有浏览器复用同一 storage_state
_LOCK = threading.Lock()
_JOB_RESULTS = {}  # title -> dict(seq, n, elapsed)


def _load_jobs(n: int) -> list:
    for cand in ("progress.json",):
        if not os.path.exists(cand):
            continue
        try:
            with open(cand, "r", encoding="utf-8") as f:
                data = json.load(f)
            items = [v for v in data.get("items", {}).values() if v.get("url")]
            if len(items) >= n:
                return items[:n]
            print(f"[warn] {cand} 中带 url 的作业不足 {n} 个（实际 {len(items)}）")
        except Exception as e:
            print(f"[warn] 读取 {cand} 失败：{e}")
    print("[error] 无法取到足量含 url 的作业，请先在 App 中抓取过至少一次（可产 progress.json）。")
    sys.exit(2)


def _scrape_page(page, url: str, title: str) -> tuple:
    """goto + 抓题，返回 (n, wall_sec)。掉登录也如实统计时长。"""
    start = time.time()
    page.goto(url, wait_until="domcontentloaded", timeout=60_000)
    time.sleep(3)  # 与冒烟探针一致，等页面结构稳定
    if is_login_page(page):
        print(f"      !! 被重定向到登录页（会话失效）：{title[:30]}")
        return 0, time.time() - start
    deadline = time.time() + _JOB_TIMEOUT_SEC
    questions = extract_all_questions(page, title=title, url=url, deadline=deadline)
    return len(questions), time.time() - start


def _open_browser(pw_obj):
    browser = pw_obj.chromium.launch(
        headless=True,
        args=["--disable-blink-features=AutomationControlled"],
    )
    ctx = browser.new_context(
        storage_state=_STATE,
        viewport={"width": 1280, "height": 800},
        user_agent=(
            "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
            "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/125.0.0.0 Safari/537.36"
        ),
    )
    page = ctx.new_page()
    return browser, ctx, page


def _run_single(jobs: list) -> float:
    """串行：一个浏览器顺序抓取全程。返回总墙钟秒。"""
    t0 = time.time()
    with sync_playwright() as p:
        browser, ctx, page = _open_browser(p)
        for seq, hw in enumerate(jobs, 1):
            print(f"  [1/1][{seq}/{len(jobs)}] 抓取：{hw['title'][:30]} ...")
            n, sec = _scrape_page(page, hw["url"], hw["title"])
            _JOB_RESULTS[hw["title"]] = {"seq": seq, "n": n, "elapsed": sec}
            print(f"          -> {n} 题，{sec:.2f}s")
            time.sleep(0.5)
        ctx.close()
        browser.close()
    return time.time() - t0


def _worker_run(wid: int, jobs: list, _claim):
    """worker 线程：自建浏览器，原子领取未处理作业。"""
    pw_obj = browser = ctx = page = None
    try:
        pw_obj = sync_playwright().start()
        browser, ctx, page = _open_browser(pw_obj)
        while True:
            with _LOCK:
                if _claim[0] >= len(jobs):
                    break
                idx = _claim[0]
                _claim[0] += 1
            hw = jobs[idx]
            print(f"  [2][{idx + 1}/{len(jobs)}] W{wid} 抓取：{hw['title'][:30]} ...")
            n, sec = _scrape_page(page, hw["url"], hw["title"])
            _JOB_RESULTS[hw["title"]] = {"seq": idx + 1, "n": n, "elapsed": sec, "worker": wid}
            print(f"          -> W{wid} {n} 题，{sec:.2f}s")
            time.sleep(0.3)
    except Exception as e:
        print(f"[error] W{wid} 异常：{e!r}")
    finally:
        for obj in (page, ctx, browser, pw_obj):
            if obj:
                try:
                    if hasattr(obj, "close"):
                        obj.close()
                    elif hasattr(obj, "stop"):
                        obj.stop()
                except Exception:
                    pass


def _run_workers(jobs: list, concurrency: int = 2) -> float:
    """双线程：2 个 worker 各一浏览器并发领取。返回总墙钟秒。"""
    t0 = time.time()
    _claim = [0]
    threads = [threading.Thread(target=_worker_run, args=(i + 1, jobs, _claim)) for i in range(concurrency)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()
    return time.time() - t0


def _report(mode: str, total: float, label: str):
    lines = _JOB_RESULTS
    seqkeys = sorted(lines, key=lambda k: lines[k]["seq"])
    print(f"\n===== {label}（总墙钟 {total:.2f}s，作业数 {len(seqkeys)}）=====")
    ts = 0.0
    for t in seqkeys:
        r = lines[t]
        print(f"  #{r['seq']:<2} {t[:34]:<36} {r['n']:>3} 题   {r['elapsed']:6.2f}s")
        ts += r["elapsed"]
    print(f"  题目耗时累计 {ts:.2f}s" + (f"（平均每作业 {ts / max(len(seqkeys), 1):.2f}s）" if seqkeys else ""))


def _main() -> int:
    global _STATE
    n = int(sys.argv[1]) if len(sys.argv) > 1 else 5
    jobs = _load_jobs(n)
    _STATE = load_state()
    if not _STATE:
        print("[error] 未找到有效登录态，请先在 App 中登录学习通。")
        return 2

    print(f"选定 {len(jobs)} 个作业（只抓题不保存，仅做耗时对比）:\n")
    print(">> 阶段一：单线程串行（一个浏览器顺序抓取）")
    t_single = _run_single(jobs)
    _report("single", t_single, "单线程串行结果")
    saved = {t: _JOB_RESULTS[t] for t in _JOB_RESULTS}

    _JOB_RESULTS.clear()
    print("\n>> 阶段二：双线程 worker（2 个浏览器并发）")
    t_double = _run_workers(jobs, 2)
    _report("double", t_double, "双线程并发结果")

    print("\n===== 对比 =====")
    print(f"  单线程: {t_single:.2f}s   双线程: {t_double:.2f}s   加速比: {t_single / max(t_double, 1e-9):.2f}x")
    print(f"  单线程题均 {t_single / len(jobs):.2f}s/作业   双线程题均 {t_double / len(jobs):.2f}s/作业")
    return 0


if __name__ == "__main__":
    sys.exit(_main())