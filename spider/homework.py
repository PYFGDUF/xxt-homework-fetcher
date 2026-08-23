#!/usr/bin/env python3
"""课程页 -> 作业列表相关逻辑。"""
from __future__ import annotations

import re
import time
from urllib.parse import urljoin

from playwright.sync_api import Page

from core.config import ACTION_TIMEOUT, MAX_HOMEWORK_PAGES, should_stop
from spider.browser import (
    scroll_frame_to_bottom,
    wait_for_iframe_content,
    wait_stable,
)
from spider.questions import click_next_page, has_next_page



def enter_homework_tab(page: Page) -> bool:
    """尝试点击课程页里的"作业/任务"标签。"""
    tab_selectors = [
        'a:has-text("作业")', 'li:has-text("作业")', 'span:has-text("作业")',
        'a:has-text("任务")', 'li:has-text("任务")',
        'a:has-text("作业考试")', 'li:has-text("作业考试")',
        '.work-tab', '.zy-tab', '.task-tab',
        '[data-type="work"]', '[data-type="task"]',
    ]
    for sel in tab_selectors:
        try:
            el = page.locator(sel).first
            if el.count() and el.is_visible():
                print(f'  点击标签：{sel}')
                el.click(timeout=ACTION_TIMEOUT)
                wait_stable(page, 3000)
                return True
        except Exception:
            continue
    return False


def is_insight_link(href: str, text: str = "") -> bool:
    """判断是否为"智能分析"链接（路径/域名/文字/类名多维度）。"""
    if not href:
        return False
    low = href.lower()
    # 智能分析页面域名/路径特征
    if "stat2-ans.chaoxing.com" in low or "study-knowledge" in low or "/ans?" in low:
        return True
    if "analysis" in low or "analyse" in low or "knowledge" in low:
        return True
    if text and ("智能分析" in text or text.strip() == "分析"):
        return True
    return False


# 明显的非作业提示文案（页面 UI 噪音），无论出现在哪个提取分支都会被最终去重环节剔除。
_BOILERPLATE_KEYWORDS = (
    "相似度分析", "请勿抄袭", "提交的作业将经过", "大雅",
    "温馨提示", "公告", "暂无作业", "没有更多", "敬请期待",
)


def is_boilerplate_title(title: str) -> bool:
    """判断是否为非作业的页面提示文案。"""
    return any(k in title for k in _BOILERPLATE_KEYWORDS)


def extract_homework_items(page_or_frame) -> list:
    """
    在课程页/作业列表 iframe 中提取所有作业/测验入口。
    返回每个作业的 {title, url, click_text}。
    url 可能为空，表示需要点击元素进入。
    """
    items = []
    base_url = page_or_frame.url

    # 先等 iframe 内容加载并滚动到底，触发懒加载
    wait_for_iframe_content(page_or_frame, 10_000)
    scroll_frame_to_bottom(page_or_frame)
    time.sleep(2)

    # 0. 优先：提取学习通作业列表 li[data*="work/task"] 或 li[data*="exam/test"]
    try:
        js_items = page_or_frame.evaluate("""
            () => {
                const result = [];
                const lis = document.querySelectorAll('li[data*="work/task"], li[data*="exam/test"], li[data*="work/phone"], li[data*="exam/phone"], [data*="work/task"], [data*="exam/test"]');
                lis.forEach(li => {
                    const text = (li.innerText || '').trim().replace(/\\s+/g, ' ');
                    // 标题通常在最前面的 p.overHidden2 里
                    const titleEl = li.querySelector('.overHidden2, .overHidden, .title, .work-title, .task-title') || li;
                    let title = '';
                    if (titleEl) {
                        title = (titleEl.innerText || '').trim().split(/\\n/)[0].slice(0, 80);
                    }
                    if (!title && /第[一二三四五六七八九十0-9]+章/.test(text)) {
                        const m = text.match(/第[一二三四五六七八九十0-9]+章[^\\n]*/);
                        title = m ? m[0] : text.slice(0, 80);
                    }
                    if (!title) title = text.slice(0, 80);
                    let dataUrl = li.getAttribute('data') || '';
                    // 过滤 dataUrl 里的智能分析（理论上不会，但保险）
                    if (dataUrl && (dataUrl.includes('study-knowledge') || dataUrl.includes('/ans?'))) {
                        dataUrl = '';
                    }
                    result.push({title, dataUrl, text: text.slice(0, 300)});
                });
                return result;
            }
        """)
        for el in js_items:
            title = el.get("title", "") or el.get("text", "")[:60]
            data_url = el.get("dataUrl", "")
            url = ""
            if data_url and not is_insight_link(data_url):
                url = data_url if data_url.startswith("http") else urljoin(base_url, data_url)
            if title and "智能分析" not in title:
                items.append({"title": title, "url": url, "click_text": title})
    except Exception as e:
        print(f"    [warn] JS 提取 li[data] 失败：{e}")

    # 1. JavaScript 兜底：按行提取标题，跳过"智能分析"
    try:
        js_items = page_or_frame.evaluate("""
            () => {
                const result = [];
                const rows = document.querySelectorAll('li, tr, .item, .list-item, [class*="work"], [class*="task"], [class*="homework"]');
                rows.forEach(row => {
                    const text = (row.innerText || '').trim().replace(/\\s+/g, ' ');
                    if (/第[一二三四五六七八九十0-9]+章|作业|测试|测验|考试|练习/.test(text)) {
                        const titleEl = Array.from(row.querySelectorAll('*')).find(el => {
                            const t = (el.innerText || '').trim();
                            return /第[一二三四五六七八九十0-9]+章/.test(t) && el.children.length === 0;
                        });
                        const title = titleEl ? titleEl.innerText.trim().split(/\\n/)[0].slice(0, 80) : text.split(/\\n/)[0].slice(0, 80);
                        // 找标题最近的带 href 的祖先或兄弟 a 标签，但绝不取"智能分析"链接
                        let href = '';
                        if (titleEl) {
                            let p = titleEl.closest('a');
                            if (!p) p = titleEl.parentElement.closest('a');
                            if (!p) {
                                const siblingAs = titleEl.parentElement.querySelectorAll('a[href]');
                                for (const a of siblingAs) {
                                    const aText = (a.innerText || '').trim();
                                    const aHref = a.href || a.getAttribute('href') || '';
                                    if (!aText.includes('智能分析') && !aText.includes('分析') && !aHref.includes('study-knowledge') && !aHref.includes('/ans?') && !aHref.includes('analysis')) {
                                        p = a;
                                        break;
                                    }
                                }
                            }
                            if (p) {
                                const pText = (p.innerText || '').trim();
                                const pHref = p.href || p.getAttribute('href') || '';
                                if (!pText.includes('智能分析') && !pText.includes('分析') && !pHref.includes('study-knowledge') && !pHref.includes('/ans?') && !pHref.includes('analysis')) {
                                    href = pHref;
                                }
                            }
                        }
                        result.push({title, href, text: text.slice(0, 300)});
                    }
                });
                return result;
            }
        """)
        for el in js_items:
            title = el.get("title", "") or el.get("text", "")[:60]
            href = el.get("href", "")
            url = ""
            if href and not is_insight_link(href, title):
                url = href if href.startswith("http") else urljoin(base_url, href)
            if title and "智能分析" not in title:
                items.append({"title": title, "url": url, "click_text": title})
    except Exception as e:
        print(f"    [warn] JS 按行提取失败：{e}")

    # 2. 常见 a 链接
    href_patterns = [
        'a[href*="work/do"]', 'a[href*="work/phone"]', 'a[href*="work/edit"]', 'a[href*="work/view"]',
        'a[href*="exam/test"]', 'a[href*="exam/phone"]', 'a[href*="mooc2-ans/work"]', 'a[href*="mooc2-ans/exam"]',
        'a[href*="work/"] a', 'a[href*="exam/"] a',
        'a[href*="work"]', 'a[href*="exam"]', 'a[href*="quiz"]',
    ]
    for sel in href_patterns:
        for a in page_or_frame.locator(sel).all():
            try:
                href = a.get_attribute("href") or ""
                title = a.inner_text().strip().replace("\n", " ") or "未命名"
                if is_insight_link(href, title):
                    continue
                if href and ("作业" in title or "测试" in title or "测验" in title or "考试" in title or re.search(r"第[一二三四五六七八九十0-9]+章", title)):
                    url = href if href.startswith("http") else urljoin(base_url, href)
                    if "login" not in url:
                        items.append({"title": title, "url": url, "click_text": title})
            except Exception:
                continue

    # 3. 兜底：表格/列表里的作业名（不跳过含智能分析的行，但绝不用智能分析链接）
    for row in page_or_frame.locator('tr, .list-item, .item, li').all():
        try:
            text = row.inner_text().strip()
            if re.search(r"第[一二三四五六七八九十0-9]+章|作业|测验|考试|测试", text):
                title_match = re.search(r"第[一二三四五六七八九十0-9]+章[^\n]*", text)
                title = title_match.group(0) if title_match else text.split("\n")[0][:60]
                if "智能分析" in title:
                    continue
                # 优先找不含"智能分析"的 a 标签
                url = ""
                for a in row.locator('a').all():
                    try:
                        href = a.get_attribute("href") or ""
                        a_text = a.inner_text().strip()
                        if is_insight_link(href, a_text):
                            continue
                        if href:
                            url = href if href.startswith("http") else urljoin(base_url, href)
                            break
                    except Exception:
                        continue
                # 如果当前行是 li[data] 但没被上面提取到，也尝试读 data
                if not url:
                    data_url = row.get_attribute("data") or ""
                    if data_url and not is_insight_link(data_url, title):
                        url = data_url if data_url.startswith("http") else urljoin(base_url, data_url)
                items.append({"title": title, "url": url, "click_text": title})
        except Exception:
            continue

    # 去重：相同标题只保留一个，优先保留有真实 URL 的项
    by_title = {}
    for item in items:
        url = item.get("url", "")
        title = item.get("title", "")
        if not title or "javascript:void" in url or is_boilerplate_title(title):
            continue
        existing = by_title.get(title)
        if not existing:
            by_title[title] = item
        else:
            # 优先保留带 work/task/exam 真实 URL 的项
            if url and ("work/task" in url or "exam/test" in url or "work/phone" in url or "exam/phone" in url):
                if not existing.get("url") or "work/task" not in existing.get("url", ""):
                    by_title[title] = item
    return list(by_title.values())


def click_homework_item(context, page_or_frame, title: str):
    """
    点击作业列表里对应标题的 li/p 元素，捕获并返回新打开的标签页。
    绝不点击"智能分析"。
    """
    # 取标题中比较有辨识度的部分（第X章...）
    match = re.search(r"第[一二三四五六七八九十0-9]+章[^\n]*", title)
    key = match.group(0) if match else title[:20]

    # 监听新标签页
    new_page_future = []
    def handle_page(page):
        new_page_future.append(page)
    context.on("page", handle_page)

    clicked = False
    try:
        # 1. 优先点击 li（学习通作业列表项是 li[onclick="goTask(this)"][data="..."]）
        rows = page_or_frame.locator('li').all()
        for li in rows:
            try:
                text = li.inner_text().strip()
                if key not in text and title[:30] not in text:
                    continue
                # 确保不是智能分析链接的 li
                if "智能分析" in text:
                    continue
                data = li.get_attribute("data") or ""
                if data and is_insight_link(data):
                    continue
                if li.is_visible():
                    li.click(timeout=ACTION_TIMEOUT)
                    wait_stable(page_or_frame, 4000)
                    clicked = True
                    break
            except Exception:
                continue

        # 2. 兜底：通过文本定位（标题 <p> 本身）
        if not clicked:
            for text_key in [key, title[:30]]:
                try:
                    locator = page_or_frame.locator(f"text={text_key}").first
                    if locator.count() and locator.is_visible():
                        locator.click(timeout=ACTION_TIMEOUT)
                        wait_stable(page_or_frame, 4000)
                        clicked = True
                        break
                except Exception:
                    continue
    finally:
        context.remove_listener("page", handle_page)

    if not clicked:
        return None

    # 等待新标签页打开
    deadline = time.time() + 8
    while time.time() < deadline and not new_page_future:
        time.sleep(0.2)

    if new_page_future:
        new_page = new_page_future[0]
        new_page.wait_for_load_state("domcontentloaded", timeout=60_000)
        wait_stable(new_page, 3000)
        return new_page
    return None


def find_homework_list_frame(page: Page):
    """
    课程页的作业列表通常在一个 iframe 里（URL 含 work/list）。
    返回该 iframe，若找不到则返回原 page。
    """
    try:
        page.wait_for_selector("iframe", timeout=ACTION_TIMEOUT)
    except Exception:
        pass

    for f in page.frames:
        try:
            url = f.url
            if "work/list" in url or "exam/list" in url or "workList" in url.lower() or "homework/list" in url:
                return f
        except Exception:
            continue
    return page


def collect_all_homeworks(list_frame, on_page=None) -> list:
    """翻页收集所有作业条目（仅统计，不进入作业），返回带 list_url 的作业列表。

    on_page: 可选回调，每翻完一页后以「本页新增条目列表」调用一次，
             供 GUI 即时增量展示，无需等待全部翻页完成。
    """
    all_homeworks = []
    seen_titles = set()
    page_num = 1
    while page_num <= MAX_HOMEWORK_PAGES:
        if should_stop():
            print("\n[info] 收到停止信号，中断统计")
            break
        print(f"\n===== 作业列表第 {page_num} 页（统计）=====")
        homeworks = extract_homework_items(list_frame)
        new = []
        for h in homeworks:
            title = h.get("title", "")
            if not title or "智能分析" in title or title in seen_titles:
                continue
            seen_titles.add(title)
            h["list_url"] = list_frame.url
            new.append(h)
        all_homeworks.extend(new)
        print(f"  本页 {len(new)} 个新作业，累计 {len(all_homeworks)} 个")
        if on_page and new:
            on_page(new)

        if not has_next_page(list_frame):
            print("  没有下一页了")
            break
        if not click_next_page(list_frame):
            print("  点击下一页失败，停止统计")
            break
        page_num += 1
        wait_for_iframe_content(list_frame, 10_000)
        scroll_frame_to_bottom(list_frame)
        time.sleep(1)

    if page_num > MAX_HOMEWORK_PAGES:
        print(f"\n[warn] 作业列表页数超过上限 {MAX_HOMEWORK_PAGES}，已停止翻页")
    return all_homeworks
