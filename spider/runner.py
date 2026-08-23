#!/usr/bin/env python3
"""主抓取流程。"""
from __future__ import annotations

import json
import os
import subprocess
import sys
import time
import traceback

from playwright.sync_api import sync_playwright

from core.config import (
    STATE_FILE,
    WAIT_TIMEOUT,
    clear_browser_state,
    clear_reusable_browser,
    debug_dir,
    emit_image_fail,
    emit_login_qr,
    emit_login_success,
    ensure_dirs,
    get_auto_export_pdf,
    get_course_url,
    get_force_regrab,
    get_headless,
    get_open_dir_on_complete,
    get_reusable_browser,
    get_reusable_context,
    get_reusable_page,
    load_state,
    output_dir,
    reset_login_event,
    reset_login_cancel,
    is_login_cancelled,
    save_state,
    set_course_name,
    set_current_browser,
    set_current_context,
    set_run_id,
    set_should_stop,
    should_stop,
    wait_for_login,
    _report_progress,
    _report_status,
)
from core.logger import with_logging
from core.progress import ProgressTracker
from core.utils import check_course_url_valid, extract_course_name, is_login_page, safe_filename
from exporters.merge import merge_all_docx
from exporters.pdf import export_pdf
from exporters.word import ImageRegistry, download_images_in_text, save_word
from spider.browser import (
    debug_screenshot,
    dump_frame_html,
    load_cookies,
    scroll_frame_to_bottom,
    wait_for_iframe_content,
    wait_stable,
)
from spider.homework import (
    click_homework_item,
    collect_all_homeworks,
    enter_homework_tab,
    extract_homework_items,
    find_homework_list_frame,
    is_insight_link,
)
from spider.questions import extract_all_questions


def _open_output_dir(directory: str):
    """在 Finder 中打开输出目录；仅在 macOS 上可用。"""
    if not directory or not os.path.isdir(directory):
        print(f"[warn] 输出目录不存在，无法自动打开：{directory}")
        return
    try:
        if sys.platform == "darwin":
            subprocess.Popen(["open", directory])
            print(f"[info] 已在 Finder 中打开输出目录：{directory}")
        else:
            print("[warn] 仅在 macOS 上支持自动打开输出目录")
    except Exception as e:
        print(f"[warn] 自动打开输出目录失败：{e}")


def _open_item_list(context, sys_page, hw):
    """
    选定模式（未走课程首页导航）下，为缺少直接 URL 的作业准备一个可点击的列表上下文。
    返回可点击的 page/frame；失败返回 None。
    """
    list_url = hw.get("list_url") or hw.get("url") or ""
    if not list_url:
        return None
    p = None
    try:
        p = context.new_page()
        p.goto(list_url, wait_until="domcontentloaded", timeout=WAIT_TIMEOUT)
        wait_stable(p, 3000)
        # 若打开的整页本身就是作业列表，或含作业列表 iframe，均可点击
        if "work/list" in p.url or "exam/list" in p.url or "workList" in p.url.lower():
            wait_for_iframe_content(p, 10_000)
            return p
        frame = find_homework_list_frame(p)
        if frame != p:
            wait_for_iframe_content(frame, 10_000)
            return frame
        return p
    except Exception:
        if p is not None:
            try:
                p.close()
            except Exception:
                pass
        return None


def _get_browser_context_page(playwright_obj):
    """
    优先复用 GUI 登录阶段保留的浏览器实例；否则按配置启动新浏览器。
    返回 (browser, context, page, reused)。
    """
    reused_browser = get_reusable_browser()
    reused_context = get_reusable_context()
    reused_page = get_reusable_page()

    if reused_browser and reused_context and reused_page:
        try:
            if reused_browser.is_connected():
                print("[info] 复用登录阶段的浏览器实例")
                # 清空可复用标记，避免重复复用或泄漏
                clear_reusable_browser()
                return reused_browser, reused_context, reused_page, True
        except Exception:
            pass
        clear_reusable_browser()

    headless = get_headless()
    # v1.3 起完全使用内置无头浏览器（扫码登录与抓取统一走无头），
    # 不再需要下载完整 Chromium，故移除旧的“显示浏览器/缺登录组件”下载提示分支。
    print(f"[info] 启动浏览器（headless={headless}）")
    browser = playwright_obj.chromium.launch(
        headless=headless,
        args=["--disable-blink-features=AutomationControlled"],
    )
    context_args = {
        "viewport": {"width": 1280, "height": 800},
        "user_agent": (
            "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
            "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/125.0.0.0 Safari/537.36"
        ),
    }
    state = load_state()
    cookies = load_cookies()
    if state:
        context = browser.new_context(storage_state=state, **context_args)
    else:
        context = browser.new_context(**context_args)
    if cookies and not state:
        context.add_cookies(cookies)
    page = context.new_page()
    return browser, context, page, False


# 候选二维码元素选择器（学习通登录页改版时按需补充）
_QR_SELECTORS = [
    "img#quickCode",
    "img#quickMark",
    "img#quickMarkImg",
    "img.login-qrcode",
    ".qrlogin-img img",
    "#qrcode img",
    ".qr-code img",
    "img[src*='qrcode']",
    "img[src*='QRCode']",
]

# 无头扫码登录总预算（秒）
_HEADLESS_LOGIN_TIMEOUT = 300


class LoginCancelledError(RuntimeError):
    """用户在登录界面点击「取消登录」触发的取消信号。"""

    def __init__(self, message: str = "已取消登录，任务已终止"):
        super().__init__(message)


def _capture_qr(page) -> tuple:
    """从登录页截取二维码 PNG 并返回 base64，以及是否命中二维码元素。

    只截取二维码元素本身（清晰、小）。返回 (base64, found_qr)：
      found_qr=True  → base64 为有效二维码图；
      found_qr=False → 页面已不存在二维码元素（通常意味着扫码后已跳转离开登录页），base64 为空串。
    注意：不再回退为整页网页截图，避免扫码成功后把网页误当二维码回传显示。
    """
    import base64 as _b64
    for sel in _QR_SELECTORS:
        try:
            el = page.locator(sel).first
            if el.count():
                try:
                    el.scroll_into_view_if_needed(timeout=1500)
                except Exception:
                    pass
                data = el.screenshot(timeout=3000)
                if data:
                    return _b64.b64encode(data).decode("ascii"), True
        except Exception:
            continue
    return "", False


def _headless_login(page, context) -> bool:
    """无头模式扫码登录：用内置无头浏览器渲染登录页，把二维码截图回传 GUI 原生显示。

    后台轮询页面是否已带登录态跳转离开登录页（扫码成功会触发 JS 跳转）；
    用户扫码后点击“已完成登录”也会唤醒推进。二维码约 1~2 分钟过期，期间自动刷新。
    返回 True 表示登录成功。
    """
    print("[info] 检测到未登录，已改用内置无头浏览器扫码登录（无需下载完整 Chromium）。")
    emit_login_qr("", "正在获取登录二维码…")
    deadline = time.time() + _HEADLESS_LOGIN_TIMEOUT
    last_qr = 0.0
    reset_login_event()
    reset_login_cancel()
    while time.time() < deadline:
        # 用户在 GUI 点击「取消登录」：立即返回 False，让上层终止当前任务
        if is_login_cancelled():
            print("[warn] 已取消登录")
            return False
        # 若扫码成功、JS 已带登录态自动跳转离开登录页，直接判定成功
        if not is_login_page(page):
            save_state(context)
            emit_login_success()
            print("[info] 扫码登录成功，登录态已保存")
            return True
        # 周期性刷新二维码（过期二维码会失效）
        if last_qr == 0 or (time.time() - last_qr) >= 15:
            b64, found_qr = _capture_qr(page)
            if found_qr:
                emit_login_qr(b64, "请用学习通App扫码后点击下方“已完成登录”（二维码过期会自动刷新）")
                last_qr = time.time()
            elif not is_login_page(page):
                # 扫码成功已跳转离开登录页且二维码元素消失：立即判定登录成功
                save_state(context)
                emit_login_success()
                print("[info] 扫码登录成功，登录态已保存")
                return True
            else:
                # 仍在登录页但暂未截到二维码：不发误导性的网页图，稍后重试
                emit_login_qr("", "正在获取登录二维码…")
                last_qr = 0
        # 每 5 秒醒来重检登录态；用户点击“已完成登录”也会立即唤醒
        wake = wait_for_login(timeout=5)
        if wake:
            reset_login_event()
            wait_stable(page, 4000)
            if not is_login_page(page):
                save_state(context)
                emit_login_success()
                print("[info] 扫码登录成功，登录态已保存")
                return True
            # 仍为登录页：刷新页面取得新二维码后继续等待
            try:
                page.reload(wait_until="domcontentloaded", timeout=WAIT_TIMEOUT)
                wait_stable(page, 3000)
            except Exception as e:
                print(f"[warn] 刷新登录页失败：{e}")
    raise RuntimeError("登录超时，请重新扫码。若反复失败可删除登录状态后重试。")


def _gui_login_flow(page, context, interactive: bool) -> bool:
    """
    统一处理登录态：CLI 模式等待用户按回车；GUI 模式统一走无头扫码登录
    （内置无头浏览器渲染登录页，二维码回传原生显示），无需完整 Chromium。
    返回 True 表示可以继续后续流程。
    """
    if interactive:
        print("检测到未登录，请在浏览器中完成登录/扫码，然后按回车继续...")
        input()
        wait_stable(page, 3000)
        return True

    # v1.3 起一律使用内置无头浏览器扫码登录，不再依赖完整 Chromium。
    return _headless_login(page, context)


def standalone_login() -> bool:
    """独立发起扫码登录（设置中「登录学习通」入口）。

    打开课程页（缺省用学习通通用登录页），若是登录页则走无头扫码登录；
    若本已登录则直接上报成功。返回 True 表示已登录。
    """
    url = get_course_url() or "https://passport2.chaoxing.com/login"
    browser = context = playwright_obj = None
    try:
        playwright_obj = sync_playwright().start()
        browser, context, page, _reused = _get_browser_context_page(playwright_obj)
        set_current_browser(browser)
        set_current_context(context)
        page.goto(url, wait_until="domcontentloaded", timeout=WAIT_TIMEOUT)
        wait_stable(page, 3000)

        if is_login_page(page):
            if not _headless_login(page, context):
                raise LoginCancelledError("已取消登录")
        else:
            save_state(context)
            emit_login_success("检测到您已登录学习通，无需重新扫码")
        return True
    finally:
        clear_browser_state()
        for obj in (context, browser, playwright_obj):
            if obj:
                try:
                    if hasattr(obj, "close"):
                        obj.close()
                    elif hasattr(obj, "stop"):
                        obj.stop()
                except Exception:
                    pass


def save_homework(title: str, url: str, questions: list) -> str:
    """
    保存为 Word（主输出）和 JSON（元数据，隐藏目录）。
    同一 URL 的作业覆盖旧文件，避免产生 _1/_2 重复文件。
    返回生成的 Word 文件路径（若失败返回空字符串）。
    """
    safe_title = safe_filename(title)
    word_base = os.path.join(output_dir(), safe_title)
    metadata_dir = os.path.join(output_dir(), ".metadata")
    metadata_base = os.path.join(metadata_dir, safe_title)
    os.makedirs(metadata_dir, exist_ok=True)

    # 若已有同名文件，检查 URL 是否相同：相同则覆盖，不同才加序号
    final_word_base = word_base
    final_metadata_base = metadata_base
    counter = 1
    while os.path.exists(f"{final_metadata_base}.json"):
        try:
            with open(f"{final_metadata_base}.json", "r", encoding="utf-8") as f:
                old_data = json.load(f)
            if old_data.get("url") == url:
                break  # 同一作业，覆盖
        except Exception:
            pass
        final_word_base = f"{word_base}_{counter}"
        final_metadata_base = f"{metadata_base}_{counter}"
        counter += 1

    # 图片目录：每个作业独立子目录
    images_dir = os.path.join(output_dir(), "images", safe_title)
    relative_prefix = f"images/{safe_title}"
    registry = ImageRegistry()

    # 为 Word 准备带本地图片占位符的题目副本（先注册、不下载）
    doc_questions = []
    for q in questions:
        dq = dict(q)
        dq["title"], _ = download_images_in_text(q.get("title", ""), images_dir, relative_prefix, registry)
        dq["options"] = [
            download_images_in_text(opt, images_dir, relative_prefix, registry)[0]
            for opt in q.get("options", [])
        ]
        dq["answer"], _ = download_images_in_text(q.get("answer", ""), images_dir, relative_prefix, registry)
        doc_questions.append(dq)

    # 并发下载所有图片
    failed_imgs = registry.download_all(max_workers=5, max_retries=2)
    # 有图片下载失败时上报事件，供 GUI 在抓取完成后弹窗提示
    if failed_imgs:
        emit_image_fail(failed_imgs, title)

    # 将下载失败的占位符替换为提示文本
    for dq in doc_questions:
        dq["title"] = registry.replace_failed_placeholders(dq["title"])
        dq["options"] = [registry.replace_failed_placeholders(opt) for opt in dq["options"]]
        dq["answer"] = registry.replace_failed_placeholders(dq["answer"])

    # JSON 元数据保存到隐藏目录 .metadata，用于 repair.py（保留原始 Markdown，便于重新处理）
    data = {"title": title, "url": url, "total": len(questions), "questions": questions}
    with open(f"{final_metadata_base}.json", "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)

    # Word 文档（主输出）
    docx_path = f"{final_word_base}.docx"
    try:
        save_word(title, url, doc_questions, final_word_base, output_dir(), registry)
    except Exception as e:
        print(f"    [error] 生成 Word 失败：{e}")
        return ""

    # 自动导出 PDF（如果开启）
    if get_auto_export_pdf() and os.path.exists(docx_path):
        export_pdf(docx_path)

    # 若本次作业没有任何图片，删除空 images 子目录
    if os.path.isdir(images_dir) and not os.listdir(images_dir):
        try:
            os.rmdir(images_dir)
            print("    该作业无图片，已删除空 images 文件夹")
        except Exception:
            pass

    # 若 images 顶层目录为空，也一并删除
    top_images_dir = os.path.join(output_dir(), "images")
    if os.path.isdir(top_images_dir) and not os.listdir(top_images_dir):
        try:
            os.rmdir(top_images_dir)
        except Exception:
            pass

    return docx_path


@with_logging
def load_homework_list(course_url: str = None, headless: bool = None, interactive: bool = True,
                       stream_callback=None) -> list:
    """
    仅加载课程作业列表并返回，不抓取。
    返回每个作业的字典列表：{"title": ..., "url": ..., "list_url": ...}
    interactive: 是否允许通过终端 input() 等待用户操作；GUI 调用时应设为 False。
    stream_callback: 可选回调，每翻完一页以其新增条目列表调用一次，供 GUI 即时增量展示。
    """
    url = course_url or get_course_url()

    browser = None
    context = None
    playwright_obj = None
    try:
        playwright_obj = sync_playwright().start()
        browser, context, page, reused = _get_browser_context_page(playwright_obj)
        set_current_browser(browser)
        set_current_context(context)
        page.goto(url, wait_until="domcontentloaded", timeout=WAIT_TIMEOUT)
        wait_stable(page, 3000)

        # 先处理登录态：CLI 交互模式下允许手动登录；GUI 非交互模式弹出登录对话框等待
        if is_login_page(page):
            if not _gui_login_flow(page, context, interactive):
                raise LoginCancelledError

        err = check_course_url_valid(page)
        if err:
            raise RuntimeError(err)

        # 提取课程名称，用于后续输出目录命名
        course_name = extract_course_name(page)
        set_course_name(course_name)
        print(f"课程名称：{course_name}")

        save_state(context)
        print(f"登录态已保存到 {STATE_FILE}")

        print("当前页面：", page.url)
        print("页面标题：", page.title())

        entered_tab = enter_homework_tab(page)
        if entered_tab:
            wait_stable(page, 5000)

        list_frame = find_homework_list_frame(page)
        if list_frame != page:
            print(f"    找到作业列表 iframe：{list_frame.url[:120]}")
            wait_for_iframe_content(list_frame, 10_000)

        print("正在查找作业列表...")
        homeworks = extract_homework_items(list_frame)

        if not homeworks:
            print("未自动识别到作业入口，保存 iframe HTML 用于分析...")
            dump_frame_html(list_frame, "homework_list_frame")
            debug_screenshot(page, "homework_list_page")
            if interactive:
                print("按回车后将再次尝试...")
                input()
                homeworks = extract_homework_items(list_frame)
            else:
                print("[warn] 未识别到作业入口，请检查课程 URL 是否过期或登录状态是否有效")
                return []

        if len(homeworks) > 0 and homeworks[0].get("title") != "manual_capture":
            print(f"\n开始统计全部作业（当前已识别 {len(homeworks)} 个）...")
            homeworks = collect_all_homeworks(list_frame, on_page=stream_callback)

        # 记录每个作业的 list_url，便于后续抓取时回到正确列表页
        for hw in homeworks:
            if not hw.get("list_url"):
                hw["list_url"] = list_frame.url

        return homeworks

    finally:
        clear_browser_state()
        for obj in (context, browser, playwright_obj):
            if obj:
                try:
                    if hasattr(obj, "close"):
                        obj.close()
                    elif hasattr(obj, "stop"):
                        obj.stop()
                except Exception:
                    pass


@with_logging
def run(selected_homeworks: list = None, interactive: bool = True):
    """
    主抓取流程。
    selected_homeworks: 若提供，则只抓取这些作业；否则自动加载全部作业，并跳过已完成的。
    interactive: 是否允许通过终端 input() 等待用户操作；GUI 调用时应设为 False。
    """
    set_run_id(time.strftime("%Y%m%d_%H%M%S"))
    tracker = ProgressTracker()

    set_should_stop(False)
    browser = None
    context = None
    playwright_obj = None
    try:
        playwright_obj = sync_playwright().start()
        browser, context, page, reused = _get_browser_context_page(playwright_obj)
        set_current_browser(browser)
        set_current_context(context)

        if selected_homeworks is not None:
            # —— GUI 选定模式：直接抓取勾选的作业，不依赖设置里的课程 URL。
            #    避免因设置中课程 URL 与左侧列表不一致而抓到错误课程（如误入“离散数学”）。 ——
            homeworks = [h for h in selected_homeworks if h.get("title")]
            total_count = len(homeworks)
            if total_count == 0:
                print("[info] 没有需要抓取的作业")
                return
            # 课程名与登录态在 load_homeworks 时已记录/保存，这里复用即可
            ensure_dirs()
            print(f"\n===== GUI 选定 {total_count} 个作业待抓取 =====")
            print(f"本次运行输出目录：{output_dir()}\n")
            list_frame = None
        else:
            # —— 自动 / 断点续传模式：从设置课程页进入并统计全部 ——
            print("正在打开课程页面...")
            page.goto(get_course_url(), wait_until="domcontentloaded", timeout=WAIT_TIMEOUT)
            wait_stable(page, 3000)

            # 先处理登录态：CLI 交互模式下允许手动登录；GUI 非交互模式弹出登录对话框等待
            if is_login_page(page):
                if not _gui_login_flow(page, context, interactive):
                    raise LoginCancelledError

            # 检查课程 URL 是否有效/过期
            err = check_course_url_valid(page)
            if err:
                raise RuntimeError(err)

            # 提取课程名称，用于输出目录命名
            course_name = extract_course_name(page)
            set_course_name(course_name)
            print(f"课程名称：{course_name}")

            # 现在才能确定最终的输出/调试目录
            ensure_dirs()
            print(f"\n本次运行输出目录：{output_dir()}")
            print(f"本次运行 debug 目录：{debug_dir()}\n")

            # 保存登录态
            save_state(context)
            print(f"登录态已保存到 {STATE_FILE}")

            print("当前页面：", page.url)
            print("页面标题：", page.title())

            # 尝试进入作业标签
            print("尝试进入作业列表...")
            entered_tab = enter_homework_tab(page)
            if entered_tab:
                wait_stable(page, 5000)  # 等 iframe 充分加载

            # 学习通课程页的作业列表通常在一个 iframe 里
            print("查找作业列表 iframe...")
            list_frame = find_homework_list_frame(page)
            if list_frame != page:
                print(f"    找到作业列表 iframe：{list_frame.url[:120]}")
                wait_for_iframe_content(list_frame, 10_000)

            # 提取作业列表
            print("正在查找作业列表...")
            homeworks = extract_homework_items(list_frame)

            if not homeworks:
                print("未自动识别到作业入口，保存 iframe HTML 用于分析...")
                dump_frame_html(list_frame, "homework_list_frame")
                debug_screenshot(page, "homework_list_page")
                print("  已保存 debug 文件，请检查 debug/ 目录下的 html 和 png")
                if interactive:
                    print("按回车后将再次尝试；或你可以手动在浏览器中点击进入某个作业/测验，")
                    print("然后回到终端按回车，脚本将抓取当前页面题目。")
                    input()
                    homeworks = extract_homework_items(list_frame)
                    if not homeworks:
                        homeworks = [{"title": "manual_capture", "url": page.url}]
                else:
                    print("[warn] 未识别到作业入口，请检查课程 URL 是否过期或登录状态是否有效")
                    return

            # 先翻页收集所有作业，获得准确总数用于进度显示
            if len(homeworks) > 0 and homeworks[0].get("title") != "manual_capture":
                print(f"\n开始统计全部作业（当前已识别 {len(homeworks)} 个）...")
                homeworks = collect_all_homeworks(list_frame)

            # 记录每个作业的 list_url
            for hw in homeworks:
                if not hw.get("list_url"):
                    hw["list_url"] = list_frame.url

            # 自动模式按断点续传过滤
            total = len(homeworks)
            homeworks = tracker.filter_homeworks(homeworks, skip_completed=True)
            skipped = total - len(homeworks)
            if skipped > 0 and not get_force_regrab():
                print(f"[info] 已跳过 {skipped} 个已抓取作业（共 {total} 个）")
            print(f"\n===== 共 {len(homeworks)} 个作业待抓取 =====\n")
            total_count = len(homeworks)
            if total_count == 0:
                print("[info] 没有需要抓取的作业")
                return

        for idx, hw in enumerate(homeworks, 1):
            if should_stop():
                print("\n[info] 收到停止信号，中断抓取")
                break

            print(f"[{idx}/{total_count}] 正在抓取：{hw['title']}")

            new_page = None
            save_url = ""
            try:
                # 回到该作业所在列表页，保持上下文一致（自动模式才有课程级 list_frame）
                if list_frame is not None:
                    list_url = hw.get("list_url", list_frame.url)
                    if list_url and list_frame.url != list_url:
                        try:
                            list_frame.goto(list_url)
                            wait_for_iframe_content(list_frame, 10_000)
                            scroll_frame_to_bottom(list_frame)
                            time.sleep(0.5)
                        except Exception as e:
                            print(f"    [warn] 返回列表页失败：{e}")

                target_url = hw.get("url", "")
                # 如果识别到是智能分析 URL，强制置空
                if target_url and is_insight_link(target_url, hw["title"]):
                    print(f"    [warn] 过滤掉智能分析链接：{target_url}")
                    target_url = ""

                if target_url:
                    # 直接打开真实作业 URL（选定模式下作业自带直达 URL，可在任意课程上下文下抓取）
                    print(f"    新标签页打开：{target_url}")
                    new_page = context.new_page()
                    new_page.goto(target_url, wait_until="domcontentloaded", timeout=WAIT_TIMEOUT)
                    wait_stable(new_page, 4000)
                    save_url = target_url
                else:
                    # 点击标题进入作业，并捕获新打开的标签页
                    # 选定模式无课程级列表帧时，用作业自身 list_url 临时打开一个列表上下文
                    entry = list_frame if list_frame is not None else _open_item_list(context, page, hw)
                    if entry is None:
                        print("    无法定位作业列表上下文，跳过")
                        tracker.set(hw.get("url", ""), hw["title"], "failed")
                        _report_status(hw.get("url", ""), hw["title"], "failed")
                        _report_progress(idx, total_count, hw["title"])
                        continue
                    print("    点击标题进入作业...")
                    new_page = click_homework_item(context, entry, hw["title"])
                    if not new_page:
                        print("    点击失败，跳过")
                        tracker.set(hw.get("url", ""), hw["title"], "failed")
                        _report_status(hw.get("url", ""), hw["title"], "failed")
                        _report_progress(idx, total_count, hw["title"])
                        continue
                    save_url = new_page.url

                questions = extract_all_questions(new_page)

                if questions:
                    docx_path = save_homework(hw["title"], save_url, questions)
                    if docx_path:
                        tracker.set(hw.get("url", ""), hw["title"], "completed",
                                    output_dir=output_dir(), word_file=docx_path)
                        _report_status(hw.get("url", ""), hw["title"], "completed")
                    else:
                        tracker.set(hw.get("url", ""), hw["title"], "failed")
                        _report_status(hw.get("url", ""), hw["title"], "failed")
                else:
                    print("    未抓到任何题目，保存 debug 后关闭标签页")
                    debug_screenshot(new_page, hw["title"])
                    tracker.set(hw.get("url", ""), hw["title"], "failed")
                    _report_status(hw.get("url", ""), hw["title"], "failed")

            except Exception as e:
                print(f"    [error] 抓取失败: {e}")
                traceback.print_exc()
                tracker.set(hw.get("url", ""), hw["title"], "failed")
                _report_status(hw.get("url", ""), hw["title"], "failed")
                if new_page:
                    debug_screenshot(new_page, hw["title"] + "_error")
                elif list_frame is not None:
                    debug_screenshot(list_frame, hw["title"] + "_error")

            finally:
                # 及时关闭新标签页释放内存
                if new_page:
                    try:
                        new_page.close()
                        print("    已关闭新标签页")
                    except Exception:
                        pass

                # 清理上下文中残留的其他页面/弹窗，避免 frame 累积导致后续定位异常
                try:
                    for pg in context.pages:
                        if pg != page and not pg.is_closed():
                            pg.close()
                except Exception:
                    pass

            # 本作业处理完毕（成功或失败），再上报进度，
            # 避免最后一个作业尚未完成时进度就已到 100%
            _report_progress(idx, total_count, hw["title"])

            # 每个作业之间短暂停顿，避免请求过快
            time.sleep(0.5)

        # 合并本次生成的所有 Word 文档
        print("\n正在合并本次生成的 Word 文档...")
        merge_all_docx(output_dir())

        # 抓取全部完成后，若开启则自动在 Finder 中打开本次输出目录
        if get_open_dir_on_complete():
            _open_output_dir(output_dir())

        # 最终保存状态
        save_state(context)
        print(f"\n浏览器状态已保存到 {STATE_FILE}，下次运行可直接复用。")

    except KeyboardInterrupt:
        print("\n[info] 用户中断运行")
    except Exception as e:
        print(f"\n[error] 运行异常：{e}")
        traceback.print_exc()
        raise
    finally:
        # 确保浏览器进程被关闭，避免终端退出时无响应
        clear_browser_state()
        for obj in (context, browser, playwright_obj):
            if obj:
                try:
                    if hasattr(obj, "close"):
                        obj.close()
                    elif hasattr(obj, "stop"):
                        obj.stop()
                except Exception:
                    pass
