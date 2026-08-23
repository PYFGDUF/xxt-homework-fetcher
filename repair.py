#!/usr/bin/env python3
"""
修复已抓取作业中答案缺失/仅有学生答案的问题。
读取 out/*/.metadata/*.json，找出答案为空的作业，用当前脚本重新抓取并覆盖。
支持命令行全量修复，也支持 GUI 批量勾选后修复。
"""
import json
import os
import sys
import traceback
import glob

from playwright.sync_api import sync_playwright

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import chaoxing_spider as cs


def needs_repair(questions):
    """判断题目列表是否需要重新抓取。"""
    if not questions:
        return True
    bad = 0
    for q in questions:
        ans = q.get("answer", "")
        if not ans or ans.startswith("我的答案：") or "无正确答案" in ans or ans == "未识别":
            bad += 1
    # 超过一半答案缺失就重抓
    return bad > len(questions) / 2


def count_good_answers(questions):
    """统计正确答案数量（非空且不是学生答案）。"""
    good = 0
    for q in questions:
        ans = q.get("answer", "")
        if ans and not ans.startswith("我的答案：") and "无正确答案" not in ans and ans != "未识别":
            good += 1
    return good


def collect_repair_items():
    """扫描所有时间戳子目录下的 .metadata，返回需要修复的作业列表。"""
    cs.ensure_dirs()
    to_repair = []
    json_pattern = os.path.join(cs.BASE_OUTPUT_DIR, "*", ".metadata", "*.json")
    for path in sorted(glob.glob(json_pattern)):
        try:
            with open(path, "r", encoding="utf-8") as f:
                data = json.load(f)
            url = data.get("url", "")
            title = data.get("title", "")
            questions = data.get("questions", [])
            if not url:
                continue
            if needs_repair(questions):
                to_repair.append({
                    "path": path,
                    "title": title,
                    "url": url,
                    "old_good": count_good_answers(questions),
                    "old_total": len(questions),
                })
        except Exception as e:
            print(f"读取 {path} 失败: {e}")
    return to_repair


def _create_browser_context():
    """创建修复专用的浏览器上下文。"""
    state = cs.load_state()
    if not state:
        print("未找到 state.json，请先运行 chaoxing_spider.py 登录")
        return None, None, None

    p = sync_playwright().start()
    browser = p.chromium.launch(
        headless=cs.get_headless(),
        args=["--disable-blink-features=AutomationControlled"],
    )
    context = browser.new_context(
        storage_state=state,
        viewport={"width": 1280, "height": 900},
        user_agent=(
            "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
            "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/125.0.0.0 Safari/537.36"
        ),
    )
    return p, browser, context


def _repair_one(context, item):
    """修复单个作业，返回 (success, new_good, total)。"""
    print(f"修复：{item['title']}")
    print(f"    URL: {item['url'][:120]}")
    print(f"    原结果：{item['old_good']}/{item['old_total']} 题有正确答案")

    new_page = None
    original_run_id = cs.get_run_id()
    original_course_name = cs.get_course_name()
    try:
        new_page = context.new_page()
        new_page.goto(item["url"], wait_until="domcontentloaded", timeout=cs.WAIT_TIMEOUT)
        cs.wait_stable(new_page, 5000)

        if cs.is_login_page(new_page):
            print("    [error] 修复时检测到登录页，请重新登录后重试")
            return False, 0, 0

        questions = cs.extract_all_questions(new_page)
        new_good = count_good_answers(questions)
        print(f"    新结果：{new_good}/{len(questions)} 题有正确答案")

        # 仅当新结果不比旧结果差才保存
        if questions and new_good >= item['old_good']:
            # item['path'] 形如 .../out/{old_dir}/.metadata/{title}.json
            old_dir = os.path.basename(os.path.dirname(os.path.dirname(item["path"])))
            # 兼容旧版纯时间戳目录：清空课程名，避免 output_dir 追加课程名前缀
            cs.set_course_name("")
            cs.set_run_id(old_dir)
            cs.save_homework(item["title"], item["url"], questions)
            print("    已覆盖保存")
            return True, new_good, len(questions)
        else:
            print("    新结果未改善，保留原文件")
            return False, new_good, len(questions)

    except Exception as e:
        print(f"    [error] 修复失败: {e}")
        traceback.print_exc()
        return False, 0, 0

    finally:
        cs.set_run_id(original_run_id)
        cs.set_course_name(original_course_name)
        if new_page:
            try:
                new_page.close()
            except Exception:
                pass
        # 清理残留页面
        try:
            for pg in context.pages:
                if not pg.is_closed():
                    pg.close()
        except Exception:
            pass


def repair_selected(items):
    """修复用户选中的作业列表（供 GUI 调用）。"""
    if not items:
        print("没有需要修复的作业")
        return

    p, browser, context = _create_browser_context()
    if not context:
        return

    try:
        print(f"\n开始修复选中的 {len(items)} 个作业\n")
        for idx, item in enumerate(items, 1):
            print(f"[{idx}/{len(items)}]", end=" ")
            _repair_one(context, item)
    finally:
        try:
            context.close()
        except Exception:
            pass
        try:
            browser.close()
        except Exception:
            pass
        try:
            p.stop()
        except Exception:
            pass
        cs.clear_browser_state()

    print("\n修复完成")


def main():
    """命令行入口：全量修复所有需要修复的作业。"""
    cs.ensure_dirs()
    to_repair = collect_repair_items()
    if not to_repair:
        print("没有需要修复的作业")
        return
    repair_selected(to_repair)


if __name__ == "__main__":
    main()
