#!/usr/bin/env python3
"""作业页 -> 题目提取相关逻辑。"""
from __future__ import annotations

import re
import time
import traceback

from playwright.sync_api import Page

from core.config import ACTION_TIMEOUT, MAX_QUESTION_PAGES, should_stop
from core.utils import (
    _clean_alt_for_markdown,
    _clean_extracted_text,
)
from spider.browser import (
    debug_screenshot,
    dump_frame_html,
    wait_stable,
)


def find_question_frame(page: Page):
    """
    学习通作业题目通常在 iframe 里加载。
    返回最可能包含题目的 frame 或原 page。
    注意：必须和作业列表 iframe（work/list）以及智能分析页区分开。
    """
    try:
        page.wait_for_selector("iframe", timeout=ACTION_TIMEOUT)
    except Exception:
        pass

    frames = page.frames
    for f in frames:
        try:
            url = f.url
            # 先排除明显不是题目的 frame，避免进入智能分析或作业列表
            if "work/list" in url or "exam/list" in url:
                continue
            from spider.homework import is_insight_link
            if is_insight_link(url):
                continue

            body_text = f.locator("body").inner_text(timeout=2000)

            # 有明确题目关键词的 frame 最可能是题目 iframe
            if any(k in body_text for k in ("单选题", "多选题", "判断题", "填空题", "简答题", "题目", "选项", "答案")):
                return f

            # 次选：URL 含 do/test/view/phone 且内容足够
            if any(k in url for k in ("work/do", "work/view", "work/phone", "exam/do", "exam/test", "exam/phone", "quiz")) and len(body_text) > 100:
                return f
        except Exception:
            continue
    return page


def extract_text_with_images(element) -> str:
    """提取元素内的文字，并把 <img> 转成 markdown 图片标记。"""
    # 方案1：在浏览器里把 img 替换成 markdown 后取 innerText（最准确）
    try:
        text = element.evaluate("""
            el => {
                const clone = el.cloneNode(true);
                clone.querySelectorAll('img').forEach(img => {
                    const src = img.src || img.getAttribute('src') || '';
                    let alt = (img.alt || '').replace(/[\\[\\]\\(\\)]/g, '').trim();
                    if (!alt) alt = '图片';
                    const md = src ? ` ![${alt}](${src}) ` : '';
                    img.replaceWith(document.createTextNode(md));
                });
                let t = clone.innerText.trim().replace(/\\s+/g, ' ');
                // 去除零宽字符
                t = t.replace(/[\\u200b-\\u200f\\ufeff]/g, '');
                return t;
            }
        """)
        if text:
            return _clean_extracted_text(text)
    except Exception:
        pass

    # 方案2：fallback 到 innerHTML 正则提取（兼容 element.evaluate 偶发失败）
    try:
        html = element.inner_html()

        def img_repl(m):
            tag = m.group(0)
            src_match = re.search(r'src=["\']([^"\']+)["\']', tag)
            src = src_match.group(1) if src_match else ''
            alt_match = re.search(r'alt=["\']([^"\']*)["\']', tag)
            alt = _clean_alt_for_markdown(alt_match.group(1) if alt_match else '')
            return f' ![{alt}]({src}) ' if src else ''

        text = re.sub(r'<img[^>]+>', img_repl, html, flags=re.IGNORECASE)
        text = re.sub(r'<[^>]+>', ' ', text)
        text = _clean_extracted_text(text)
        if text:
            return text
    except Exception:
        pass

    # 方案3：兜底纯文本
    try:
        return _clean_extracted_text(element.inner_text())
    except Exception:
        return ""


def extract_questions_js(page_or_frame) -> list:
    """
    JavaScript 兜底提取题目。
    针对学习通 work/view 页结构：.questionLi.singleQuesId 为单题容器。
    """
    try:
        raw = page_or_frame.evaluate("""
            () => {
                const results = [];
                // 学习通作业详情页题目容器
                const containers = document.querySelectorAll(
                    '.questionLi.singleQuesId, .questionLi, .singleQuesId, .TiMu .questionLi, .TiMu'
                );
                containers.forEach((item, idx) => {
                    const text = item.innerText || '';
                    // 跳过最外层 .TiMu 包装
                    if (item.classList.contains('TiMu') && item.querySelectorAll('.questionLi').length > 0) return;

                    // 题型
                    let qtype = '未知';
                    if (text.includes('单选题')) qtype = '单选题';
                    else if (text.includes('多选题')) qtype = '多选题';
                    else if (text.includes('判断题')) qtype = '判断题';
                    else if (text.includes('填空题')) qtype = '填空题';
                    else if (text.includes('简答题')) qtype = '简答题';

                    // 处理图片：把 img 转成 markdown
                    const imgToMd = el => {
                        if (!el) return '';
                        const clone = el.cloneNode(true);
                        clone.querySelectorAll('img').forEach(img => {
                            const src = img.src || img.getAttribute('src') || '';
                            const alt = img.alt || '';
                            img.replaceWith(document.createTextNode(src ? ` ![${alt}](${src}) ` : ''));
                        });
                        return clone.innerText.trim().replace(/\\s+/g, ' ');
                    };

                    // 题干
                    let title = '';
                    const titleEl = item.querySelector('.mark_name, .qtContent, .title, .topic, .q-title, .stem, .TiMuTitle, .shiti, .question-title, .subject-title, h3, h4');
                    title = imgToMd(titleEl || item);
                    // 去掉前缀题号/分数，保留原始内容
                    if (!title) {
                        const first = text.split(/\\n/).find(s => s.trim());
                        title = first ? first.trim().slice(0, 500) : '';
                    }

                    // 选项
                    const options = [];
                    const optEls = item.querySelectorAll('.mark_letter.qtDetail li, .qtDetail li, .options li, .answer-list li, .option-item, .option, .answer_option, label');
                    optEls.forEach(el => {
                        const t = imgToMd(el);
                        if (t) options.push(t);
                    });

                    // 答案：优先正确答案（非空才采用），其次 fallback，最后学生答案
                    let answer = '';
                    const rightEl = item.querySelector('.rightAnswerContent');
                    if (rightEl) {
                        const t = imgToMd(rightEl);
                        if (t) answer = t;
                    }
                    if (!answer) {
                        const ansEls = item.querySelectorAll('.right-answer, .answer, .correct, .right_key, .answer-content, .answer_text, [data-answer], .true_answer, .right, .rightAnswer, .answer-analysis, .blank-answer, .fill-answer, .completion-answer, .fill_blank, .essay-answer, .short-answer, .subjective-answer, .answer-area, .answer-text, .blank, .answer-input');
                        for (const el of ansEls) {
                            const t = imgToMd(el);
                            if (t) { answer = t; break; }
                        }
                    }
                    // fallback：收集 input/textarea 值 或 文本中的“答案：”
                    if (!answer) {
                        const inputs = item.querySelectorAll("input[type='text'], input[type='number'], textarea, .blank, .fill_blank, .answer-input");
                        const vals = [];
                        inputs.forEach(i => { const v = i.value || i.innerText || ''; if (v.trim()) vals.push(v.trim()); });
                        if (vals.length) answer = vals.join('；');
                    }
                    if (!answer) {
                        const cleanText = text.replace(/\s+/g, ' ');
                        const m = cleanText.match(/正确答案[：:](.+?)(?:我的答案|$)|标准答案[：:](.+?)(?:我的答案|$)|答案[：:](.+?)(?:我的答案|$)/);
                        if (m) answer = (m[1] || m[2] || m[3] || '').trim();
                    }
                    if (!answer) {
                        const stuEl = item.querySelector('.stuAnswerContent');
                        if (stuEl) {
                            const t = imgToMd(stuEl);
                            answer = t ? '我的答案：' + t : '（仅有学生作答，无正确答案）';
                        }
                    }

                    if (title || options.length) {
                        results.push({ index: idx + 1, type: qtype, title, options, answer });
                    }
                });
                return results;
            }
        """, timeout=15_000)
        for q in raw:
            q["options"] = [o for o in q.get("options", []) if o]
        return raw
    except Exception as e:
        print(f"    [warn] JS 兜底提取失败：{e}")
        return []


def extract_answer_fallback(item, options: list) -> str:
    """标准答案选择器未命中时，尝试从输入框或文本中解析答案（填空/简答兼容）。"""
    # 1. 收集 input/textarea 中已填写的值
    try:
        vals = item.evaluate("""
            el => {
                const inputs = el.querySelectorAll("input[type='text'], input[type='number'], textarea, .blank, .fill_blank, .answer-input");
                const arr = [];
                inputs.forEach(i => {
                    const v = i.value || i.innerText || '';
                    if (v.trim()) arr.push(v.trim());
                });
                return arr;
            }
        """)
        if vals:
            return "；".join(str(v) for v in vals)
    except Exception:
        pass

    # 2. 从文本中匹配“答案：/正确答案：/标准答案：”后的内容
    try:
        text = item.inner_text()
        for pattern in [r'正确答案[：:](.+?)(?:\n|我的答案|$)', r'标准答案[：:](.+?)(?:\n|我的答案|$)', r'答案[：:](.+?)(?:\n|我的答案|$)']:
            m = re.search(pattern, text, re.DOTALL)
            if m:
                ans = re.sub(r'\s+', ' ', m.group(1)).strip()
                if ans and ans not in ('', '未识别'):
                    return ans
    except Exception:
        pass

    # 3. 若题目是判断/选择且没有任何答案文本，尝试从已选中的 radio/checkbox 取值
    if options:
        try:
            chosen = []
            radios = item.locator("input[type='radio']:checked, input[type='checkbox']:checked").all()
            for r in radios:
                val = r.get_attribute("value") or ""
                if not val:
                    rid = r.get_attribute("id") or ""
                    if rid:
                        label = item.locator(f"label[for='{rid}']")
                        if label.count():
                            val = extract_text_with_images(label.first)
                if val:
                    chosen.append(val)
            if chosen:
                return "选中选项：" + ", ".join(chosen)
        except Exception:
            pass

    return ""


def extract_questions_from_page(page_or_frame) -> list:
    """
    提取当前 frame 中的题目和答案。
    针对学习通 work/view 页结构优化：.questionLi.singleQuesId 为单题容器。
    """
    questions = []
    print("    [extract] 开始识别题目容器...")

    # 题目容器选择器（按优先级）
    item_selectors = [
        ".questionLi.singleQuesId", ".questionLi", ".singleQuesId",
        ".question-item", ".singleQ", ".q-item", ".topic-item",
        ".topic_shiti", ".exam_topic", ".shiti", ".subject-item",
        ".question", ".topic", ".shiti-item", ".exam-item",
        ".TiMu",
        "[class*='question' i]", "[class*='shiti' i]", "[class*='topic' i]",
    ]

    items = []
    used_sel = ""
    for sel in item_selectors:
        try:
            items = page_or_frame.locator(sel).all()
            if len(items) > 0:
                used_sel = sel
                break
        except Exception:
            continue

    # 如果命中的是外层 .TiMu 包装，改用内部的 .questionLi
    if used_sel == ".TiMu" and len(items) == 1:
        try:
            inner = items[0].locator(".questionLi").all()
            if len(inner) > 0:
                items = inner
                used_sel = ".questionLi (from .TiMu)"
        except Exception:
            pass

    print(f"    使用题目容器选择器：{used_sel or '无'}，命中 {len(items)} 个")

    # 防止异常情况下命中过多元素导致处理极慢
    if len(items) > 200:
        print("    [warn] 命中元素过多，只处理前 200 个")
        items = items[:200]

    for idx, item in enumerate(items, 1):
        try:
            # 题干：优先带图的文本
            title = ""
            for tsel in [".mark_name", ".qtContent", ".title", ".topic", ".q-title", ".stem", ".TiMuTitle",
                         ".shiti", ".question-title", ".subject-title", "h3", "h4", ".topic-detail",
                         ".timu", ".topic-desc", ".question-stem"]:
                try:
                    el = item.locator(tsel).first
                    if el.count():
                        title = extract_text_with_images(el)
                        if title:
                            break
                except Exception:
                    continue

            # 选项
            options = []
            for opsel in [".mark_letter.qtDetail li", ".qtDetail li", ".options li", ".answer-list li",
                          ".option-item", ".choise", ".option", ".answer_option", "label",
                          ".topic-options li", ".question-option", ".select-option"]:
                try:
                    opts = item.locator(opsel).all()
                    if opts:
                        texts = []
                        for o in opts:
                            t = extract_text_with_images(o)
                            if t:
                                texts.append(t)
                        if texts:
                            options = texts
                            break
                except Exception:
                    continue

            # 正确答案：优先 .rightAnswerContent，仅当内容非空才采用
            answer = ""
            answer_selectors = [
                ".rightAnswerContent", ".mark_answer .mark_key .stuAnswerContent",
                ".mark_answer .stuAnswerContent", ".right-answer", ".answer", ".correct", ".right_key",
                ".answer-content", ".answer_text", "[data-answer]", ".true_answer",
                ".right", ".rightAnswer", ".answer-analysis",
                ".blank-answer", ".fill-answer", ".completion-answer", ".fill_blank",
                ".essay-answer", ".short-answer", ".subjective-answer", ".answer-area",
                ".answer-text", ".blank", ".answer-input",
            ]
            for asel in answer_selectors:
                try:
                    el = item.locator(asel).first
                    if el.count():
                        ans_text = extract_text_with_images(el)
                        if ans_text:
                            answer = ans_text
                            break
                except Exception:
                    continue

            # 选择题：若答案是“我的答案”，去掉“我的答案：”标签只留正文
            if answer:
                answer = re.sub(r'^\s*我的答案\s*[：:]\s*', '', answer).strip()

            # 仍没有，则从 .mark_answer / .mark_fill 整段文本中匹配“正确答案/标准答案/参考答案：”
            if not answer:
                try:
                    seg_el = item.locator(".mark_answer").first
                    if not seg_el.count():
                        seg_el = item.locator(".mark_fill").first
                    if seg_el.count():
                        seg_text = extract_text_with_images(seg_el)
                        if seg_text:
                            m = re.search(r'(?:正确答案|标准答案|参考答案|正确答案是)\s*[：:]\s*(.+)', seg_text)
                            if m:
                                cand = m.group(1).strip("；;，,、 \n")
                                if cand:
                                    answer = cand
                except Exception:
                    pass

            # 若没拿到正确答案，使用 fallback（填空 input、文本匹配、选中选项等）
            if not answer:
                answer = extract_answer_fallback(item, options)

            # 仍无答案则退而求其次取学生答案（标注清楚）
            if not answer:
                try:
                    stu = item.locator(".stuAnswerContent").first
                    if stu.count():
                        stu_text = extract_text_with_images(stu)
                        answer = ("我的答案：" + stu_text) if stu_text else "（仅有学生作答，无正确答案）"
                except Exception:
                    pass

            # 题型推断
            qtype = "未知"
            if "单选题" in title or (options and len(options) <= 5 and "多选题" not in title):
                qtype = "单选题"
            if "多选题" in title:
                qtype = "多选题"
            if "判断题" in title:
                qtype = "判断题"
            if "填空题" in title:
                qtype = "填空题"
            if "简答题" in title:
                qtype = "简答题"

            questions.append({
                "index": idx,
                "type": qtype,
                "title": title,
                "options": options,
                "answer": answer,
            })
        except Exception as e:
            print(f"    [warn] 第 {idx} 题解析失败: {e}")

    return questions


def click_reveal_answer(page_or_frame) -> bool:
    """部分作业页的“正确答案”需要点击“查看答案/展开”按钮才会渲染出来。

    学习通常见「每题一个展开按钮」的布局，若只点第一个，其余题目答案会一直为空，
    导致导出出现“未识别”。这里循环点击所有可见的展开按钮，直到没有更多为止；
    展开后按钮文字会变为“收起答案”，不再命中“.查看答案”选择器，天然避免重复点击同一题。
    """
    reveal_selectors = [
        'button:has-text("查看答案")',
        'a:has-text("查看答案")',
        'span:has-text("查看答案")',
        'div:has-text("查看答案")',
        'button:has-text("查看解析")',
        'a:has-text("查看解析")',
        'button:has-text("查看正确答案")',
        '.showAnswer',
        '.checkAnswer',
        '.btn-answer',
        '.seeAns',
    ]
    # 单页最多尝试点击次数，防止程序化点击死循环
    max_reveal_clicks = 200
    clicked = False
    for _ in range(max_reveal_clicks):
        pressed = False
        for sel in reveal_selectors:
            try:
                el = page_or_frame.locator(sel).first
                if el.count() and el.is_visible() and not el.is_disabled():
                    print(f'    点击查看答案按钮：{sel}')
                    el.click(timeout=ACTION_TIMEOUT)
                    clicked = True
                    pressed = True
                    wait_stable(page_or_frame, 600)
                    break
            except Exception:
                continue
        if not pressed:
            break
    return clicked


def click_start_button(page_or_frame) -> bool:
    """作业/考试页可能需要点击"开始作答"等按钮才会显示题目。"""
    start_selectors = [
        'button:has-text("开始作答")', 'a:has-text("开始作答")',
        'button:has-text("开始考试")', 'a:has-text("开始考试")',
        'button:has-text("进入考试")', 'a:has-text("进入考试")',
        'button:has-text("进入作业")', 'a:has-text("进入作业")',
        'button:has-text("立即开始")', 'a:has-text("立即开始")',
        'button:has-text("答题")', 'a:has-text("答题")',
        '.begin-btn', '.start-btn', '.start-exam', '.start-work',
    ]
    for sel in start_selectors:
        try:
            el = page_or_frame.locator(sel).first
            if el.count() and el.is_visible() and not el.is_disabled():
                print(f'    点击开始按钮：{sel}')
                el.click(timeout=ACTION_TIMEOUT)
                wait_stable(page_or_frame, 4000)
                return True
        except Exception:
            continue
    return False


def has_next_page(page_or_frame) -> bool:
    """判断是否存在下一页/下一题按钮且可用。"""
    next_selectors = [
        'a:has-text("下一页")', 'a:has-text("下页")', 'a.next', '.next-page', '.pagination-next',
        'button:has-text("下一页")', '[title="下一页"]', '.page-next',
        '.xl-nextPage', '#page .xl-nextPage', '.pageDiv .xl-nextPage',
        'a:has-text("下一题")', 'button:has-text("下一题")', '.next-topic', '.next-question',
    ]
    for sel in next_selectors:
        try:
            el = page_or_frame.locator(sel).first
            if el.count() and el.is_visible() and not el.is_disabled():
                # 学习通分页下一页若带 xl-disabled 则不可用
                cls = el.get_attribute("class") or ""
                if "disabled" in cls:
                    continue
                return True
        except Exception:
            continue
    return False


def click_next_page(page_or_frame) -> bool:
    """点击下一页/下一题。"""
    next_selectors = [
        'a:has-text("下一页")', 'a:has-text("下页")', 'a.next', '.next-page', '.pagination-next',
        'button:has-text("下一页")', '[title="下一页"]', '.page-next',
        '.xl-nextPage', '#page .xl-nextPage', '.pageDiv .xl-nextPage',
        'a:has-text("下一题")', 'button:has-text("下一题")', '.next-topic', '.next-question',
    ]
    for sel in next_selectors:
        try:
            el = page_or_frame.locator(sel).first
            if el.count() and el.is_visible() and not el.is_disabled():
                cls = el.get_attribute("class") or ""
                if "disabled" in cls:
                    continue
                el.click(timeout=ACTION_TIMEOUT)
                wait_stable(page_or_frame, 4000)
                return True
        except Exception:
            continue
    return False


def get_question_frame(page_or_frame):
    """重新定位题目 iframe。"""
    if isinstance(page_or_frame, Page):
        return find_question_frame(page_or_frame)
    qframe = find_question_frame(page_or_frame.page)
    if qframe == page_or_frame.page:
        return page_or_frame
    return qframe


def extract_all_questions(page_or_frame) -> list:
    """
    进入作业页后，点击开始按钮，切换到题目 iframe，翻页抓取所有题目。
    """
    all_questions = []
    page_idx = 1

    # 等待题目 iframe 加载
    print("    等待题目 iframe/页面加载...")
    wait_stable(page_or_frame, 4000)

    # 若页面有"开始作答"等按钮，先点击（主文档层）
    click_start_button(page_or_frame)

    qframe = get_question_frame(page_or_frame)
    print(f"    题目所在 frame URL：{qframe.url[:120]}")
    # 尝试展开“查看答案”——必须在题目 iframe 内点击，主文档 locator 到不了 frame 内部
    click_reveal_answer(qframe)

    while page_idx <= MAX_QUESTION_PAGES:
        if should_stop():
            print("\n[info] 收到停止信号，中断题目抓取")
            break
        print(f"    正在抓取第 {page_idx} 页...")
        t0 = time.time()
        try:
            questions = extract_questions_from_page(qframe)
        except Exception as e:
            print(f"    [warn] extract_questions_from_page 异常：{e}")
            traceback.print_exc()
            questions = []
        print(f"    [debug] extract_questions_from_page 耗时 {time.time() - t0:.2f}s，返回 {len(questions)} 题")

        if not questions:
            print("    本页未识别到题目，尝试 JS 兜底...")
            t0 = time.time()
            try:
                questions = extract_questions_js(qframe)
            except Exception as e:
                print(f"    [warn] extract_questions_js 异常：{e}")
                questions = []
            print(f"    [debug] extract_questions_js 耗时 {time.time() - t0:.2f}s，返回 {len(questions)} 题")

        if not questions:
            print("    仍未识别到题目，保存 debug...")
            debug_screenshot(qframe, f"page_{page_idx}_no_questions")
            dump_frame_html(qframe, f"page_{page_idx}_no_questions")
            break

        # 修正全局题号
        for q in questions:
            q["index"] = len(all_questions) + questions.index(q) + 1
        all_questions.extend(questions)
        print(f"    第 {page_idx} 页抓到 {len(questions)} 题，累计 {len(all_questions)} 题")

        if not has_next_page(qframe):
            print("    没有下一页了")
            break

        if not click_next_page(qframe):
            print("    点击下一页失败")
            break

        page_idx += 1
        # 翻页后题目 iframe 可能重新加载，重新定位
        qframe = get_question_frame(page_or_frame)
        print(f"    翻页后题目 frame URL：{qframe.url[:120]}")
        # 翻页后可能仍需展开答案（在 iframe 内部点击）
        click_reveal_answer(qframe)

    if page_idx > MAX_QUESTION_PAGES:
        print(f"\n[warn] 题目页数超过上限 {MAX_QUESTION_PAGES}，已停止翻页")
    return all_questions
