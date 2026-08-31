#!/usr/bin/env python3
"""并发冒烟验证：2 个独立浏览器实例并发抓取 2 个不同作业页，确认学习通不踢会话、题目可正常抓取。

只读探针 —— 不保存 Word、不写 progress、不覆盖登录态（仅复用读取）。
以 {App Support}/XxtApp 为 cwd 运行（登录态 state.json 相对 cwd 解析）。

用法:
    python3 script/concurrency_smoke.py [job_a_url] [job_b_url]
不带参数时自动从 progress.json 中选取 2 个含 url 的作业。

判定:
    - 若某一浏览器抓取期间因跳回登录页拿不到题目 => 会话被踢（输出 KICKED）。
    - 两浏览器都能抓到题目 => 学习通容忍该并发量 => 建议落地 worker 化。
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

# 单作业抓取预算：与 runner 一致，超时截断保留已抓题目
_JOB_TIMEOUT_SEC = 300
_OUT = ["", ""]
_LOCK = threading.Lock()


def _pick_two_jobs() -> list:
    """从 progress.json 中挑选 2 个含 url 的真实作业；不足则报错退出。"""
    for cand in ("progress.json",):
        if not os.path.exists(cand):
            continue
        try:
            with open(cand, "r", encoding="utf-8") as f:
                data = json.load(f)
            items = [v for v in data.get("items", {}).values() if v.get("url")]
            if len(items) >= 2:
                return items[:2]
        except Exception as e:
            print(f"[warn] 读取 {cand} 失败：{e}")
    print("[error] 无法从 progress.json 取到至少 2 个含 url 的作业，请显式传入两个作业 URL。")
    sys.exit(2)


def _worker(index: int, url: str, title: str) -> None:
    """独立线程：自己的 sync_playwright + Chromium + context（共享同一登录态）。"""
    label = f"W{index + 1}"
    try:
        state = load_state()
        if not state:
            _OUT[index] = "NO_LOGIN"
            print(f"[{label}] 未找到有效登录态，无法抓取。请先在 App 中登录学习通。")
            return
        with sync_playwright() as p:
            browser = p.chromium.launch(
                headless=True,
                args=["--disable-blink-features=AutomationControlled"],
            )
            ctx = browser.new_context(
                storage_state=state,
                viewport={"width": 1280, "height": 800},
                user_agent=(
                    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
                    "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/125.0.0.0 Safari/537.36"
                ),
            )
            page = ctx.new_page()
            print(f"[{label}] 开始抓取：{title[:40]}")
            page.goto(url, wait_until="domcontentloaded", timeout=60_000)
            time.sleep(3)

            # 被重定向到登录页 => 会话被踢
            if is_login_page(page):
                print(f"[{label}] !! 被重定向到登录页（会话被踢或已过期）")
                _OUT[index] = "KICKED"
                # 记录用于诊断
                try:
                    page.screenshot(path=f"debug_concurrency_w{index+1}_login.png")
                except Exception:
                    pass
                return

            deadline = time.time() + _JOB_TIMEOUT_SEC
            questions = extract_all_questions(page, title=title, url=url, deadline=deadline)
            n = len(questions)
            if n > 0:
                print(f"[{label}] 成功抓到 {n} 道题（第 1 题标题：{questions[0].get('title', '')[:40]}）")
                _OUT[index] = f"OK:{n}"
            else:
                # 抓不到题：区分「拿到空页面」还是「掉登录」
                if is_login_page(page):
                    print(f"[{label}] !! 抓题空且页面跳转登录页（会话被踢）")
                    _OUT[index] = "KICKED"
                else:
                    print(f"[{label}] 未抓到题目（页面非登录页，需排查；保存了截图）")
                    try:
                        page.screenshot(path=f"debug_concurrency_w{index+1}_empty.png", full_page=True)
                    except Exception:
                        pass
                    _OUT[index] = "EMPTY"
            ctx.close()
            browser.close()
    except Exception as e:
        print(f"[{label}] 异常：{e!r}")
        _OUT[index] = f"ERR:{e}"
    finally:
        with _LOCK:
            pass  # 并发标记已由 _OUT 各自隔离，无需额外同步


def _main() -> int:
    args = sys.argv[1:]
    if len(args) >= 2 and args[0].startswith("http"):
        jobs = [{"url": args[0], "title": args[0]}, {"url": args[1], "title": args[1]}]
    else:
        jobs = _pick_two_jobs()

    print(f"准备并发抓取 {len(jobs)} 个作业（仅只读，不保存任何文件）\n")
    threads = [
        threading.Thread(target=_worker, args=(i, jobs[i].get("url", ""), jobs[i].get("title", "")))
        for i in range(len(jobs))
    ]
    for t in threads:
        t.start()
    for t in threads:
        t.join()

    print("\n===== 并发冒烟结果 =====")
    for i, r in enumerate(_OUT):
        print(f"  W{i + 1}: {r}")

    kicked = any(r == "KICKED" or r == "NO_LOGIN" for r in _OUT)
    if kicked:
        print("\n结论: 并发抓取导致会话被踢/无登录态，服务端不容忍当前并发。")
        print("建议: 降低并发数或改回串行，先排查被踢的具体作业。")
        return 1

    ok = [r for r in _OUT if isinstance(r, str) and r.startswith("OK:")]
    if len(ok) == len(_OUT):
        print("\n结论: 2 个并发浏览器均正常抓到题目，学习通未踢会话。")
        print("建议: 可行 —— 可落地 worker 化改造（建议并发数 2~3，结合 headless）。")
        return 0
    if ok:
        print("\n结论: 部分成功但未全部成功，需进一步分析失败的 worker。")
        return 2
    print("\n结论: 未抓到任何题目，需排查页面结构与登录态。")
    return 3


if __name__ == "__main__":
    sys.exit(_main())