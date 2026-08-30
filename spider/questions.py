#!/usr/bin/env python3
"""作业页 -> 题目提取相关逻辑。"""
from __future__ import annotations

import re
import time
import traceback

from playwright.sync_api import Page

from core.config import ACTION_TIMEOUT, MAX_QUESTION_PAGES, should_stop, _report_status
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
    except Exception as e:
        print(f"    [debug] extract_text_with_images JS 方案失败，回退 innerHTML：{e}")

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
    except Exception as e:
        print(f"    [debug] extract_text_with_images innerHTML 方案失败：{e}")

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


# 一次 evaluate 提取整页所有题目（Markdown 化图片、多选择器、rightAnswerContent 优先）。
# 与逐字段路径逻辑等价，但整页仅一次往返，极大缩短抓取耗时。
# 实测：5 题整页提取 ~0.001s，答案与逐字段路径完全一致（mismatch=0）。
BULK_EXTRACT_JS = """() => {
    const results = [];
    const imgToMd = el => {
        const clone = el.cloneNode(true);
        clone.querySelectorAll('img').forEach(img => {
            const src = img.src || img.getAttribute('src') || '';
            let alt = (img.alt || '').replace(/[\\[\\]\\(\\)]/g, '').trim();
            if (!alt) alt = '图片';
            img.replaceWith(document.createTextNode(src ? ` ![${alt}](${src}) ` : ''));
        });
        let t = (clone.innerText || '').trim().replace(/\\s+/g, ' ');
        return t.replace(/[\\u200b-\\u200f\\ufeff]/g, '');
    };
    const containers = document.querySelectorAll('.questionLi.singleQuesId, .questionLi');
    containers.forEach((item, idx) => {
        const tText = (item.innerText || '').trim();
        let title = '';
        for (const sel of ['.mark_name', '.qtContent', '.title', '.topic', '.q-title', '.stem', '.TiMuTitle',
                            '.shiti', '.question-title', '.subject-title', 'h3', 'h4', '.topic-detail',
                            '.timu', '.topic-desc', '.question-stem']) {
            const el = item.querySelector(sel);
            if (el) { title = imgToMd(el); if (title) break; }
        }
        if (!title) {
            const first = tText.split(/\\n/).find(s => s.trim());
            title = first ? first.trim().slice(0, 500) : '';
        }
        let options = [];
        for (const sel of ['.mark_letter.qtDetail li', '.qtDetail li', '.options li', '.answer-list li',
                            '.option-item', '.choise', '.option', '.answer_option', 'label',
                            '.topic-options li', '.question-option', '.select-option']) {
            const opts = Array.from(item.querySelectorAll(sel)).map(imgToMd).filter(x => x);
            if (opts.length) { options = opts; break; }
        }
        let answer = '';
        const right = item.querySelector('.rightAnswerContent');
        if (right) { answer = imgToMd(right); }
        if (!answer) {
            for (const sel of ['.right-answer', '.answer', '.correct', '.right_key', '.answer-content',
                                '.answer_text', '[data-answer]', '.true_answer', '.right', '.rightAnswer',
                                '.answer-analysis', '.blank-answer', '.fill-answer', '.completion-answer',
                                '.fill_blank', '.essay-answer', '.short-answer', '.subjective-answer',
                                '.answer-area', '.answer-text', '.blank', '.answer-input']) {
                const el = item.querySelector(sel);
                if (el) { const a = imgToMd(el); if (a) { answer = a; break; } }
            }
        }
        if (!answer) {
            const vals = [];
            item.querySelectorAll("input[type='text'], input[type='number'], textarea, .blank, .fill_blank, .answer-input")
                .forEach(i => { const v = i.value || i.innerText || ''; if (v.trim()) vals.push(v.trim()); });
            if (vals.length) answer = vals.join('；');
        }
        if (!answer) {
            const cleanT = tText.replace(/\\s+/g, ' ');
            const m = cleanT.match(/正确答案[：:](.+?)(?:我的答案|$)|标准答案[：:](.+?)(?:我的答案|$)|答案[：:](.+?)(?:我的答案|$)/);
            if (m) answer = (m[1] || m[2] || m[3] || '').trim();
        }
        if (!answer) {
            const stu = item.querySelector('.stuAnswerContent');
            if (stu) { const st = imgToMd(stu); answer = st ? '我的答案：' + st : '（仅有学生作答，无正确答案）'; }
        }
        if (answer) { answer = answer.replace(/^我的答案[：:]\s*/, ''); }
        let qtype = '未知';
        if (title.includes('单选题') || (options.length && options.length <= 5 && !title.includes('多选题'))) qtype = '单选题';
        if (title.includes('多选题')) qtype = '多选题';
        if (title.includes('判断题')) qtype = '判断题';
        if (title.includes('填空题')) qtype = '填空题';
        if (title.includes('简答题')) qtype = '简答题';
        if (title || options.length) {
            results.push({index: idx + 1, type: qtype, title, options, answer});
        }
    });
    return results;
}"""


def extract_questions_bulk(page_or_frame) -> list:
    """一次 evaluate 批量提取整页题目（尽量替换逐字段往返，显著提速）。

    返回 list[{index,type,title,options,answer}]；失败或无容器返回 []。
    """
    try:
        raw = page_or_frame.evaluate(BULK_EXTRACT_JS)
        if not raw:
            return []
        out = []
        for q in raw:
            out.append({
                "index": int(q.get("index") or 0),
                "type": q.get("type") or "未知",
                "title": q.get("title") or "",
                "options": [o for o in (q.get("options") or []) if o],
                "answer": q.get("answer") or "",
            })
        return out
    except Exception as e:
        print(f"    [warn] 批量 JS 提取失败，回退逐字段提取：{e}")
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


def extract_questions_from_page(page_or_frame, progress_hook=None) -> list:
    """
    提取当前 frame 中的题目和答案。
    针对学习通 work/view 页结构优化：.questionLi.singleQuesId 为单题容器。
    progress_hook: 可选 (idx, total) 回调，用于页内逐题上报进度（index 从 1 开始）。
    """
    questions = []
    print("    [extract] 开始识别题目容器...")

    # 优先一次 JS 批量提取整页题目（整页仅一次往返，比逐字段快一个数量级）。
    # 批量路径不经 progress_hook 逐题上报，由调用方经 per_page 兜底保证进度单调。
    bulk = extract_questions_bulk(page_or_frame)
    if bulk:
        # 修正全局题号由调用方负责，这里赋予页内序号
        print(f"    [extract] 批量提取命中 {len(bulk)} 题")
        return bulk

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
        # 每题处理前上报页内进度（即便本题解析失败也推进，保证单调）
        if progress_hook:
            try:
                progress_hook(idx, len(items))
            except Exception:
                pass
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
    # 提速优化：一次性定位本页所有可见展开按钮并依次点击，不再「点一个等 600ms」，
    # 全部点完后再统一 wait_stable 等答案渲染稳定。
    pressed = False
    try:
        for el in page_or_frame.locator(", ".join(reveal_selectors)).all():
            try:
                if el.is_visible() and not el.is_disabled():
                    el.click(timeout=ACTION_TIMEOUT)
                    pressed = True
            except Exception:
                continue
    except Exception:
        return pressed
    if pressed:
        wait_stable(page_or_frame, 1200)
    return pressed


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


# 单作业进度：题目抓取阶段所占总进度的起止区间（0~1）
# 前段（0~_HW_EXTRACT_START）为打开作业阶段，由 open_progress_reporter 平滑上报
# （等待 iframe 稳定/展开答案），避免进度停在 0%；末段（_HW_EXTRACT_END~1）在 runner 上报、completed 置满。
# 区间内按翻页数自适应估算，保证进度单调递增、最后一页贴到区间末尾。
_HW_EXTRACT_START = 0.10
_HW_EXTRACT_END = 0.95


def open_progress_reporter(title: str, url: str):
    """返回"打开作业阶段"的进度上报器（单作业），带 1% 节流避免高频 NDJSON。

    调用方传 0..1 表示当前打开阶段内部工作量，映射到 [0, _HW_EXTRACT_START]。同一作业的
    多个子步骤（等待 iframe、点开始、定位 frame、展开答案）复用同一个 writer，保证整段
    单调递增不回退。
    """
    last = {"v": -1.0}

    def _report(fract: float):
        v = min(_HW_EXTRACT_START, _HW_EXTRACT_START * max(0.0, min(1.0, fract)))
        if v - last["v"] >= 0.005 or v >= _HW_EXTRACT_START:
            last["v"] = v
            try:
                _report_status(url or "", title, "in_progress", progress=v)
            except Exception:
                pass

    return _report


def _report_homework_progress(title: str, url: str, fract: float):
    """上报单个作业的内部进度（0~1），供 GUI 行级展示百分比。
    fract 为题目抓取阶段内部的进度（0~1），按 _HW_EXTRACT_START/_HW_EXTRACT_END 映射到作业总进度。"""
    try:
        v = _HW_EXTRACT_START + (_HW_EXTRACT_END - _HW_EXTRACT_START) * max(0.0, min(1.0, fract))
        _report_status(url or "", title, "in_progress", progress=v)
    except Exception:
        pass


def extract_all_questions(page_or_frame, title: str = "", url: str = "",
                          deadline: float = 0) -> list:
    """
    进入作业页后，点击开始按钮，切换到题目 iframe，翻页抓取所有题目。
    每处理完一页会上报一次该作业的内部进度，供 GUI 展示单作业百分比。

    deadline：可选的墙钟截止时刻（time.time()+秒）。翻页循环超时即提前截断并保留
    已抓到的题目，避免单个作业卡死拖垮整个课程；0 表示不限制。
    """
    all_questions = []
    page_idx = 1

    # 打开阶段进度上报器：把 0..1 打开工作量映射到 [0, _HW_EXTRACT_START]
    rep = open_progress_reporter(title, url)

    # 等待题目 iframe 加载（切片上报，覆盖打开阶段前段，消除进度停在 0% 的空窗）
    print("    等待题目 iframe/页面加载...")
    wait_stable(page_or_frame, 4000, on_progress=lambda f: rep(0.7 * f))

    # 若页面有“开始作答”等按钮，先点击（主文档层）
    click_start_button(page_or_frame)
    rep(0.78)

    qframe = get_question_frame(page_or_frame)
    print(f"    题目所在 frame URL：{qframe.url[:120]}")
    rep(0.86)

    # 尝试展开“查看答案”——必须在题目 iframe 内点击，主文档 locator 到不了 frame 内部
    click_reveal_answer(qframe)
    rep(0.94)

    # ---- 页内逐题进度的全局单调模型 ----
    # p = 已完整抓完页数 + 当前页已完成题目占比（0..1）；
    # 全局抽取进度 = p/(p+1)，p 随页内 idx 递增与翻页只会上升，天然单调不回退；
    # 映射到 [_HW_EXTRACT_START, _HW_EXTRACT_END] 区间，最后一页再贴到区间末尾。
    pages_done = 0          # 已完整抓完的页数
    per_page_reported = False  # 当前页是否已通过逐题钩子上报（JS 兜底时不逐题）
    timed_out = False       # 是否因超过 deadline 提前截断

    def _per_question_progress(idx, n):
        nonlocal per_page_reported
        per_page_reported = True
        p = pages_done + idx / max(n, 1)
        _report_homework_progress(title, url, p / (p + 1))

    while page_idx <= MAX_QUESTION_PAGES:
        if should_stop():
            print("\n[info] 收到停止信号，中断题目抓取")
            break
        if deadline and time.time() >= deadline:
            timed_out = True
            break
        print(f"    正在抓取第 {page_idx} 页...")
        t0 = time.time()
        per_page_reported = False  # 每页开始时复位逐题标记
        try:
            questions = extract_questions_from_page(qframe, progress_hook=_per_question_progress)
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

        # JS 兜底路径未走逐题钩子：把本页整体计为一个进度块，保证仍单调推进
        if not per_page_reported:
            _per_question_progress(1, 1)

        # 最后一页：贴到题目抓取区间末尾（映射到 _HW_EXTRACT_END）
        has_more = has_next_page(qframe)
        if not has_more:
            _report_homework_progress(title, url, 1.0)
            print("    没有下一页了")
            break

        # 进入下一页：本页计入已完成页数，下一页逐题钩子基于新的 pages_done 继续单调递增
        pages_done += 1

        if not click_next_page(qframe):
            print("    点击下一页失败")
            break

        page_idx += 1
        # 翻页后题目 iframe 可能重新加载，重新定位
        qframe = get_question_frame(page_or_frame)
        print(f"    翻页后题目 frame URL：{qframe.url[:120]}")
        # 翻页后可能仍需展开答案（在 iframe 内部点击）
        click_reveal_answer(qframe)

    if timed_out:
        print(f"\n[warn] 该作业抓取超时，已提前截断（保留已抓 {len(all_questions)} 题，避免拖垮整个课程）")
    elif page_idx > MAX_QUESTION_PAGES:
        print(f"\n[warn] 题目页数超过上限 {MAX_QUESTION_PAGES}，已停止翻页")
    return all_questions
