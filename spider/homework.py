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


# ---- 列表加载速度调参：降低固定等待下限，擦亮刷新速度 ----
# wait_stable 已在 networkidle 之后做守卫等待，以下为额外硬等待上限，可在此整体调优。
LIST_NAV_SETTLE_MS = 800        # 进入页面/goto 后守卫等待（原 3000）
LIST_TAB_SETTLE_MS = 1200       # 进入作业Tab后的守卫等待（原 5000）
LIST_LAZY_SETTLE_SEC = 0.8      # 列表懒加载后等待稳定（原 2）
# C方案：翻页统计改为「每页只 wait/scroll/sleep 一次」——单独一次足够覆盖懒加载的等待，
# 不再叠加 extract_homework_items 内部的另一次 wait+scroll+sleep(0.8)。
LIST_PAGE_TURN_SETTLE_SEC = 0.8  # 分页翻页后单次稳定等待，同时充当懒加载等待（原 0.4 + 内部 0.8 叠加）

# ---- 列表总量校验与网络韧性翻页 ----
# 学习通作业列表页顶部通常会显示总量（如「已完成 33 / 共 41 份」）。
# 网络较差时某一页可能加载不全导致「下一页」按钮短暂不可见，误判到底而漏作业。
# 通过解析总量 + 已知不足时的兜底重探，显著降低缺漏概率。
LIST_TOTAL_REPROBE_MS = 1200       # 兜底重探时的稳定等待
LIST_TOTAL_REPROBE_RETRIES = 2     # has_next_page 短暂失效时的补探次数
LIST_MAX_TOTAL = 5000              # 总量合理上限，防止把得分等数字误当总量


def read_homework_total(list_frame):
    """尽力从作业列表页文本解析总量统计（如「已完成 33 / 共 41 份」）。

    返回 (reported_done, reported_total)；解析不到则返回 (None, None)。
    此解析为「尽力而为」：只要正则能命中即可获得校验依据，不阻塞现有成功流程。
    """
    try:
        txt = list_frame.evaluate("() => (document.body && document.body.innerText) || ''")
    except Exception as e:
        print(f"    [debug] 读取列表页文本失败：{e}")
        return None, None
    txt = re.sub(r"[ \t\u00a0]+", " ", txt or "")

    def _valid(n):
        return n is not None and 0 < n <= LIST_MAX_TOTAL

    # 1) 明确上下文模式：''共 41 份/个作业'、'已有 41 个作业'、'总作业数 41'
    m = re.search(r"(?:共|已有|总计|共计|总共)\s*[有:]?\s*(\d+)\s*(?:份|个作业|个任务|个作业列表|项)", txt)
    if m and _valid(int(m.group(1))):
        total = int(m.group(1))
        dm = re.search(r"已完成?\s*[：:]?\s*(\d+)", txt)
        return (int(dm.group(1)), total) if dm else (None, total)

    # 2) 分数式：'已完成 33/41'，取右值作总量
    m = re.search(r"已完成?\s*[：:]?\s*(\d+)\s*/\s*(\d+)", txt)
    if m:
        done, total = int(m.group(1)), int(m.group(2))
        if _valid(total) and 0 <= done <= total:
            return done, total

    # 3) 兜底普通 'X / Y'（仍要求总量在合理区间）
    m = re.search(r"(\d+)\s*/\s*(\d+)", txt)
    if m:
        done, total = int(m.group(1)), int(m.group(2))
        if _valid(total) and 0 <= done <= total:
            return done, total

    return None, None


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
                wait_stable(page, LIST_NAV_SETTLE_MS)
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


def extract_homework_items(page_or_frame, skip_lazy: bool = False) -> list:
    """
    在课程页/作业列表 iframe 中提取所有作业/测验入口。
    返回每个作业的 {title, url, click_text}。
    url 可能为空，表示需要点击元素进入。

    skip_lazy: 为 True 时跳过开头的 wait/scroll/sleep 懒加载处理。
    翻页统计场景下由 collect_all_homeworks 先在每一页统一做一次 wait+scroll+sleep，
    故此处不再重复处理（C方案：去重分页每页的 redundant 懒加载）。
    """
    items = []
    base_url = page_or_frame.url

    # 先等 iframe 内容加载并滚动到底，触发懒加载
    if not skip_lazy:
        wait_for_iframe_content(page_or_frame, 10_000)
        scroll_frame_to_bottom(page_or_frame)
        time.sleep(LIST_LAZY_SETTLE_SEC)

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


def collect_all_homeworks(list_frame, on_page=None, initial_homeworks=None) -> list:
    """翻页收集所有作业条目（仅统计，不进入作业），返回带 list_url 的作业列表。

    on_page: 可选回调，每翻完一页后以「本页新增条目列表」调用一次，
             供 GUI 即时增量展示，无需等待全部翻页完成。
    initial_homeworks: 调用方已提取好的第 1 页条目。传入后跳过对第 1 页的重复提取，
             直接从第 2 页开始翻页（提速：避免首帧被 extract+scroll+sleep 重复处理一次）。
    """
    all_homeworks = []
    seen_titles = set()

    # 读取页面总量做完整性校验（尽力而为，解析不到不阻塞）
    expected_total = -1
    try:
        reported_done, expected_total = read_homework_total(list_frame)
        if expected_total:
            print(f"  检测到作业总量：{reported_done if reported_done is not None else '?'}/{expected_total}")
    except Exception:
        expected_total = -1

    def _absorb(items) -> list:
        new = []
        for h in items:
            title = h.get("title", "")
            if not title or "智能分析" in title or title in seen_titles:
                continue
            seen_titles.add(title)
            h["list_url"] = list_frame.url
            new.append(h)
        all_homeworks.extend(new)
        return new

    page_num = 1

    # 第 1 页：优先用调用方已提取好的条目，否则本函数内部提取一次
    if initial_homeworks:
        new_first = _absorb(initial_homeworks)
        print(f"  第 1 页（seed）{len(new_first)} 个新作业，累计 {len(all_homeworks)} 个")
        if on_page and new_first:
            on_page(new_first)
    else:
        print("\n===== 作业列表第 1 页（统计）=====")
        new_first = _absorb(extract_homework_items(list_frame))
        print(f"  第 1 页 {len(new_first)} 个新作业，累计 {len(all_homeworks)} 个")
        if on_page and new_first:
            on_page(new_first)

    # 从第 2 页开始逐页翻页统计
    while page_num <= MAX_HOMEWORK_PAGES:
        if should_stop():
            print("\n[info] 收到停止信号，中断统计")
            break
        if not has_next_page(list_frame):
            # 网络韧性：已知总量但收集数不足时，「下一页」可能只是短暂未加载，
            # 做几次滚动+等待兜底重探，避免漏页后误判到底。
            if expected_total and 0 < expected_total and len(all_homeworks) < expected_total:
                probed = False
                for pm in range(1, LIST_TOTAL_REPROBE_RETRIES + 1):
                    scroll_frame_to_bottom(list_frame)
                    wait_stable(list_frame, LIST_TOTAL_REPROBE_MS)
                    if has_next_page(list_frame):
                        print(f"  [warn] 第 {page_num} 页下一页一度未加载，重探第 {pm} 次后判定可继续")
                        probed = True
                        break
                if not probed:
                    print("  没有下一页了（已完成缺失兜底探测）")
                    break
            else:
                print("  没有下一页了")
                break
        if not click_next_page(list_frame):
            print("  点击下一页失败，停止统计")
            break
        page_num += 1
        wait_for_iframe_content(list_frame, 10_000)
        scroll_frame_to_bottom(list_frame)
        time.sleep(LIST_PAGE_TURN_SETTLE_SEC)

        print(f"\n===== 作业列表第 {page_num} 页（统计）=====")
        # C方案：上方已统一 wait+scroll+sleep 一次（含懒加载），此处跳过 extract 内部的重复懒加载
        new = _absorb(extract_homework_items(list_frame, skip_lazy=True))
        print(f"  第 {page_num} 页 {len(new)} 个新作业，累计 {len(all_homeworks)} 个")
        if on_page and new:
            on_page(new)

    if page_num > MAX_HOMEWORK_PAGES:
        print(f"\n[warn] 作业列表页数超过上限 {MAX_HOMEWORK_PAGES}，已停止翻页")

    # 完整性校验：若能解析到总量但收集数不足，提示可能存在网络缺漏
    if expected_total and 0 < expected_total and len(all_homeworks) < expected_total:
        print(f"\n[warn] 识别到 {len(all_homeworks)} 个作业，但页面显示总量为 {expected_total}，"
              f"可能存在网络缺漏，建议网络稳定后重新加载作业列表")
    return all_homeworks


# =====================================================================
# 个人空间 -> 课程列表解析（「选课程」功能）
# 学习通个人空间 i.chaoxing.com/base 的课程列表渲染在嵌套 iframe
#   https://mooc1-1.chaoxing.com/visit/interaction?s=...
# 每个课程是一个 li.course.clearfix，内含真实课程入口链接
#   /mooc-ans/visit/stucoursemiddle?courseid=xx&clazzid=xx&cpi=xx&ismooc2=1&v=2
# =====================================================================

# 个人空间课程列表 iframe 的 URL 特征（域名 + 路径），用于唯一定位
_PERSONAL_SPACE_IFRAME_KEYWORDS = ("visit/interaction", "stucoursemiddle")


def find_course_list_frame(page) -> "object | None":
    """在个人空间页面中定位课程列表 iframe；找不到返回 None。"""
    try:
        for f in page.frames:
            u = f.url or ""
            if any(k in u for k in _PERSONAL_SPACE_IFRAME_KEYWORDS):
                return f
    except Exception as e:
        print(f"    [debug] 遍历页面 frame 失败：{e}")
    return None


def extract_course_list(page) -> list:
    """从个人空间课程列表 iframe 中提取全部课程。

    返回每个课程的字典：{"title", "teacher", "url", "courseid", "clazzid", "cpi"}
    其中 url 为 stucoursemiddle 课程的完整入口链接（登录会话内可直接访问，
    会被 302 跳转到带 enc/t 参数的 mycouse/stu 课程页，供 load_homework_list 复用）。
    解析不到时返回空列表。较新的英文改版个人空间界面课程入口仍保持经典结构，
    故按「stucoursemiddle 链接」这一稳定特征定位，不依赖界面语言。
    """
    frame = find_course_list_frame(page)
    if frame is None:
        print("[warn] 未找到个人空间课程列表 iframe（visit/interaction）")
        return []

    try:
        entries = frame.evaluate("""() => {
            const cards = [];
            document.querySelectorAll('li.course').forEach(li => {
                const a = li.querySelector('a[href*="stucoursemiddle"]');
                if (!a) return;
                let href = a.href || a.getAttribute('href') || '';
                if (!/^https?:\\/\\//.test(href)) return;
                // 标题：优先 .course-name，兜底整卡文本
                const nameEl = li.querySelector('.course-name');
                let title = nameEl ? (nameEl.innerText || '').trim().replace(/\\s+/g, ' ').slice(0, 120) : '';
                if (!title) {
                    const mm = li.querySelector('h3, .course-info');
                    if (mm) title = (mm.innerText || '').trim().replace(/\\s+/g, ' ').slice(0, 120);
                }
                // 真实封面缩略图：官方卡片里 <img> 本身通常带 course-cover 类（无外层包裹），
                // 也可能用 div.course-cover > img，或懒加载 data-original/data-src。
                // 依次按「class 含 cover / 图床路径特征 / 卡内首张主图」兜底命中。
                let cover = '';
                const imgs = li.querySelectorAll('img');
                for (let i = 0; i < imgs.length; i++) {
                    const img = imgs[i];
                    const src = (img.currentSrc || img.getAttribute('src') ||
                                 img.getAttribute('data-original') || img.getAttribute('data-src') || '').trim();
                    if (!src) continue;
                    const cls = (img.className || '').toString().toLowerCase();
                    if (cls.indexOf('cover') !== -1 || src.indexOf('ananas') !== -1 ||
                        /_130c|240_130|140_80/.test(src)) {
                        cover = src;
                        break;
                    }
                }
                if (!cover && imgs.length) {
                    cover = (imgs[0].currentSrc || imgs[0].getAttribute('src') ||
                             imgs[0].getAttribute('data-src') || '').trim();
                }
                // 教师：官方卡片通常在 .course-info 里（形如「杨乔东」）
                let teacher = '';
                const ps = li.querySelectorAll('.course-info p');
                if (ps.length) {
                    const last = ps[ps.length - 1];
                    teacher = (last.getAttribute('title') || (last.innerText || '')).trim().replace(/\\s+/g, ' ');
                }
                if (!teacher) {
                    const infoEl = li.querySelector('.course-info');
                    if (infoEl) {
                        teacher = (infoEl.innerText || '').trim().replace(/\\s+/g, ' ');
                    }
                }
                if (title.includes('已修') || title.includes('Public') || title.includes('Library')
                    || title.includes('Index') || title.includes('Notes')) return;
                // 「课程已结束」：整卡文本含该标记或 class 含 end 即视为已结束课程
                const cardText = (li.innerText || '');
                const ended = cardText.includes('课程已结束')
                    || (li.className || '').toLowerCase().indexOf('end') !== -1
                    || !!li.querySelector('[class*="end"]');
                cards.push({href, title, teacher, cover, ended});
            });
            return cards;
        }""")
    except Exception as e:
        print(f"    [warn] 提取课程列表失败：{e}")
        return []

    courses = []
    seen = set()
    for en in entries:
        href = (en.get("href") or "").strip()
        title = (en.get("title") or "").strip()
        # 课程入口链接需要能进入课程页；过滤纯 JS 空链与明显非课程入口
        if not href or not href.startswith("http") or "stucoursemiddle" not in href:
            continue
        if not title:
            title = href
        cover = (en.get("cover") or "").strip()
        if cover and not cover.startswith("http"):
            cover = urljoin(frame.url, cover)
        teacher = (en.get("teacher") or "").strip()
        # 去重：同一 courseid+clazzid 视为同一课程
        cid = _parse_course_param(href, "courseid")
        clazz = _parse_course_param(href, "clazzid")
        key = (cid or title, clazz or "")
        if key in seen:
            continue
        seen.add(key)
        courses.append({
            "title": title,
            "teacher": teacher,
            "cover": cover,
            "url": href,
            "courseid": cid,
            "clazzid": clazz,
            "cpi": _parse_course_param(href, "cpi"),
            "ended": bool(en.get("ended")),
        })

    if not courses:
        print("[warn] 未在个人空间识别到课程列表")
    else:
        print(f"[info] 已识别 {len(courses)} 门课程")
    return courses


def _parse_course_param(href: str, key: str) -> str:
    """从 stucoursemiddle 链接中解析 query 参数（courseid/clazzid/cpi）。"""
    try:
        from urllib.parse import parse_qs, urlsplit
        q = parse_qs(urlsplit(href).query)
        v = q.get(key, [""])[0]
        return str(v) if v else ""
    except Exception:
        return ""
