#!/usr/bin/env python3
"""
全局配置与状态模块。

所有原本在 chaoxing_spider.py 中通过全局变量共享的状态，仍在此模块中共享。
"""
from __future__ import annotations

import json
import os
import sys
import threading

from core.utils import safe_filename

# 强制 stdout 行缓冲，让日志实时可见
if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(line_buffering=True)

# ============ 配置区域 ============
# 课程 URL 默认留空，由用户在界面填写；为空时相关走通用登录页兜底
COURSE_URL = ""
DEFAULT_OUTPUT_DIR = os.path.expanduser("~/Desktop/out")
DEFAULT_DEBUG_DIR = "debug"
COOKIE_FILE = "cookies.txt"
STATE_FILE = "state.json"
SETTINGS_FILE = "settings.json"
HEADLESS = True           # 调试阶段设为 True，避免无显示环境卡死
WAIT_TIMEOUT = 60_000     # 页面加载超时（毫秒）
ACTION_TIMEOUT = 15_000   # 点击/等待元素超时（毫秒）

# 每次运行时由 run() 设置，repair.py 保持为 None 以覆盖原文件
RUN_ID = None

# 输出/调试根目录，会被 load_settings() 覆盖
BASE_OUTPUT_DIR = DEFAULT_OUTPUT_DIR
BASE_DEBUG_DIR = DEFAULT_DEBUG_DIR

# 全局 Playwright 对象，用于 GUI 强制关闭浏览器
_CURRENT_BROWSER = None
_CURRENT_CONTEXT = None
_SHOULD_STOP = False

# GUI 进度回调：func(current, total, title)
_PROGRESS_CALLBACK = None

# GUI 登录提示回调：func(message: str)
_LOGIN_PROMPT_CALLBACK = None

# GUI 扫码二维码图片回传回调：func(image_b64: str, message: str)
_LOGIN_QR_CALLBACK = None

# GUI 作业状态回调：func(url: str, title: str, status: str)
_STATUS_CALLBACK = None

# 登录完成事件：后台线程 wait，GUI 点击按钮后 set
_LOGIN_EVENT = threading.Event()

# GUI 登录阶段保留的可复用浏览器实例，避免登录成功后关闭再打开
_REUSABLE_BROWSER = None
_REUSABLE_CONTEXT = None
_REUSABLE_PAGE = None


def set_reusable_browser(browser):
    global _REUSABLE_BROWSER
    _REUSABLE_BROWSER = browser


def get_reusable_browser():
    return _REUSABLE_BROWSER


def set_reusable_context(context):
    global _REUSABLE_CONTEXT
    _REUSABLE_CONTEXT = context


def get_reusable_context():
    return _REUSABLE_CONTEXT


def set_reusable_page(page):
    global _REUSABLE_PAGE
    _REUSABLE_PAGE = page


def get_reusable_page():
    return _REUSABLE_PAGE


def clear_reusable_browser():
    global _REUSABLE_BROWSER, _REUSABLE_CONTEXT, _REUSABLE_PAGE
    _REUSABLE_BROWSER = None
    _REUSABLE_CONTEXT = None
    _REUSABLE_PAGE = None


# 是否在保存 Word 后自动导出 PDF
AUTO_EXPORT_PDF = False

# 断点续传：是否强制重新抓取已完成的作业
FORCE_REGRAB = False

# 抓取全部完成后，是否自动在 Finder 中打开本次输出目录
OPEN_DIR_ON_COMPLETE = True

# 进度记录文件
PROGRESS_FILE = "progress.json"

# 翻页抓取时的最大页数/题数上限，防止页面异常导致无限循环
MAX_HOMEWORK_PAGES = 200
MAX_QUESTION_PAGES = 200

# 当前课程名称，用于输出/调试目录命名
COURSE_NAME = ""


def set_course_name(name: str):
    """设置当前课程名称（用于输出目录命名）。"""
    global COURSE_NAME
    COURSE_NAME = safe_filename(name) if name else ""


def get_course_name() -> str:
    """获取当前课程名称。"""
    return COURSE_NAME


def set_headless(value: bool):
    """设置是否无头模式并保存到 settings.json。"""
    global HEADLESS
    HEADLESS = bool(value)
    settings = load_settings()
    settings["headless"] = HEADLESS
    save_settings(settings)


def get_headless() -> bool:
    return HEADLESS


def set_output_dir(path: str):
    """设置输出目录并保存到 settings.json。"""
    global BASE_OUTPUT_DIR, BASE_DEBUG_DIR
    BASE_OUTPUT_DIR = path
    BASE_DEBUG_DIR = os.path.join(path, "debug")
    settings = load_settings()
    settings["output_dir"] = path
    save_settings(settings)


def set_course_url(url: str):
    """设置课程 URL 并保存到 settings.json。"""
    global COURSE_URL
    COURSE_URL = url
    settings = load_settings()
    settings["course_url"] = url
    save_settings(settings)


def get_course_url() -> str:
    """获取当前课程 URL。"""
    return COURSE_URL


def set_auto_export_pdf(value: bool):
    """设置是否在保存 Word 后自动导出 PDF。"""
    global AUTO_EXPORT_PDF
    AUTO_EXPORT_PDF = bool(value)
    settings = load_settings()
    settings["auto_export_pdf"] = AUTO_EXPORT_PDF
    save_settings(settings)


def get_auto_export_pdf() -> bool:
    return AUTO_EXPORT_PDF


def set_force_regrab(value: bool):
    """设置是否强制重新抓取已完成的作业，并保存到 settings.json。"""
    global FORCE_REGRAB
    FORCE_REGRAB = bool(value)
    settings = load_settings()
    settings["force_regrab"] = FORCE_REGRAB
    save_settings(settings)


def get_force_regrab() -> bool:
    return FORCE_REGRAB


def get_open_dir_on_complete() -> bool:
    return OPEN_DIR_ON_COMPLETE


def set_open_dir_on_complete(value: bool):
    """设置抓取完成后是否自动打开输出目录，并保存到 settings.json。"""
    global OPEN_DIR_ON_COMPLETE
    OPEN_DIR_ON_COMPLETE = bool(value)
    settings = load_settings()
    settings["open_dir_on_complete"] = OPEN_DIR_ON_COMPLETE
    save_settings(settings)


def set_progress_callback(callback):
    """设置进度回调函数，签名：callback(current, total, title)。"""
    global _PROGRESS_CALLBACK
    _PROGRESS_CALLBACK = callback


def set_login_prompt_callback(callback):
    """设置登录提示回调函数，签名：callback(message: str)。"""
    global _LOGIN_PROMPT_CALLBACK
    _LOGIN_PROMPT_CALLBACK = callback


def set_login_qr_callback(callback):
    """设置扫码二维码图片回传回调，签名：callback(image_b64: str, message: str)。"""
    global _LOGIN_QR_CALLBACK
    _LOGIN_QR_CALLBACK = callback


def emit_login_qr(image_b64: str, message: str = ""):
    """把登录二维码 PNG（base64）回传给 GUI 原生显示。"""
    if _LOGIN_QR_CALLBACK:
        try:
            _LOGIN_QR_CALLBACK(image_b64, message)
        except Exception as e:
            print(f"[warn] 登录二维码回传回调出错：{e}")


# 登录成功事件回调：func(message: str)
_LOGIN_SUCCESS_CALLBACK = None


def set_login_success_callback(callback):
    """设置扫码登录成功回调，签名：callback(message: str)。"""
    global _LOGIN_SUCCESS_CALLBACK
    _LOGIN_SUCCESS_CALLBACK = callback


def emit_login_success(message: str = ""):
    """判定登录成功后立即回传 GUI（用于退出登录界面并提示登录成功）。"""
    if _LOGIN_SUCCESS_CALLBACK:
        try:
            _LOGIN_SUCCESS_CALLBACK(message or "扫码登录成功，已保存登录状态。")
        except Exception as e:
            print(f"[warn] 登录成功回调出错：{e}")


def reset_login_event():
    """清除登录完成事件。"""
    _LOGIN_EVENT.clear()


def notify_login_done():
    """通知后台线程用户已完成登录。"""
    _LOGIN_EVENT.set()


def wait_for_login(timeout: float | None = None) -> bool:
    """阻塞等待用户完成登录，返回是否等到信号。"""
    return _LOGIN_EVENT.wait(timeout)


# 登录取消标记：用户点击「取消登录」后置位，_headless_login 会及时退出
_LOGIN_CANCEL = False


def reset_login_cancel():
    """清除登录取消标记。"""
    global _LOGIN_CANCEL
    _LOGIN_CANCEL = False


def cancel_login():
    """用户取消登录：置位取消标记并唤醒登录等待，让登录流程尽快退出。"""
    global _LOGIN_CANCEL
    _LOGIN_CANCEL = True
    _LOGIN_EVENT.set()


def is_login_cancelled() -> bool:
    return _LOGIN_CANCEL


def prompt_login_and_wait(message: str):
    """
    GUI 模式下由后台线程调用：触发登录提示对话框，并阻塞等待用户完成登录。
    """
    reset_login_event()
    if _LOGIN_PROMPT_CALLBACK:
        try:
            _LOGIN_PROMPT_CALLBACK(message)
        except Exception as e:
            print(f"[warn] 登录提示回调出错：{e}")
    wait_for_login()


def _report_progress(current: int, total: int, title: str):
    """内部进度上报。"""
    if _PROGRESS_CALLBACK:
        try:
            _PROGRESS_CALLBACK(current, total, title)
        except Exception:
            pass


def set_status_callback(callback):
    """设置作业状态回调，签名：callback(url: str, title: str, status: str)。"""
    global _STATUS_CALLBACK
    _STATUS_CALLBACK = callback


def _report_status(url: str, title: str, status: str):
    """内部作业状态上报（completed / failed / skipped 等）。"""
    if _STATUS_CALLBACK:
        try:
            _STATUS_CALLBACK(url, title, status)
        except Exception:
            pass


# 图片下载失败事件回调：func(failed: int, title: str)
_IMAGE_FAIL_CALLBACK = None


def set_image_fail_callback(callback):
    """设置图片下载失败事件回调，签名：callback(failed: int, title: str)。"""
    global _IMAGE_FAIL_CALLBACK
    _IMAGE_FAIL_CALLBACK = callback


def emit_image_fail(failed: int, title: str = ""):
    """上报某作业图片下载失败数量，供 GUI 在抓取完成后弹窗提醒。"""
    if _IMAGE_FAIL_CALLBACK and failed > 0:
        try:
            _IMAGE_FAIL_CALLBACK(failed, title)
        except Exception as e:
            print(f"[warn] 图片失败回调出错：{e}")


def set_run_id(run_id: str | None):
    """设置本次运行的 RUN_ID。"""
    global RUN_ID
    RUN_ID = run_id


def get_run_id() -> str | None:
    return RUN_ID


def set_current_browser(browser):
    """设置当前 Playwright Browser 实例。"""
    global _CURRENT_BROWSER
    _CURRENT_BROWSER = browser


def get_current_browser():
    return _CURRENT_BROWSER


def set_current_context(context):
    """设置当前 Playwright BrowserContext 实例。"""
    global _CURRENT_CONTEXT
    _CURRENT_CONTEXT = context


def get_current_context():
    return _CURRENT_CONTEXT


def set_should_stop(value: bool):
    """设置/清除停止信号。"""
    global _SHOULD_STOP
    _SHOULD_STOP = value


def should_stop() -> bool:
    return _SHOULD_STOP


def clear_browser_state():
    """运行结束后清理浏览器相关全局状态。"""
    global _CURRENT_BROWSER, _CURRENT_CONTEXT, _SHOULD_STOP
    _CURRENT_BROWSER = None
    _CURRENT_CONTEXT = None
    _SHOULD_STOP = False


def force_stop():
    """GUI 关闭或用户中断时调用，强制关闭当前浏览器进程。"""
    set_should_stop(True)
    print("[info] 收到停止信号，正在关闭浏览器...")
    ctx = get_current_context()
    brw = get_current_browser()
    if ctx:
        try:
            ctx.close()
        except Exception:
            pass
    if brw:
        try:
            brw.close()
        except Exception:
            pass


def load_settings() -> dict:
    """读取 settings.json，返回配置字典。"""
    if not os.path.exists(SETTINGS_FILE):
        return {}
    try:
        with open(SETTINGS_FILE, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return {}


def save_settings(settings: dict):
    """保存配置到 settings.json。"""
    try:
        with open(SETTINGS_FILE, "w", encoding="utf-8") as f:
            json.dump(settings, f, ensure_ascii=False, indent=2)
    except Exception as e:
        print(f"[warn] 保存 settings.json 失败：{e}")


def get_appearance() -> str:
    """读取外观偏好：'system'（跟随系统）/ 'light' / 'dark'，默认跟随系统。"""
    settings = load_settings()
    mode = settings.get("appearance", "system")
    return mode if mode in ("system", "light", "dark") else "system"


def set_appearance(mode: str):
    """保存外观偏好。"""
    if mode not in ("system", "light", "dark"):
        raise ValueError(f"无效外观模式: {mode}")
    settings = load_settings()
    settings["appearance"] = mode
    save_settings(settings)


def apply_settings(settings: dict = None):
    """应用配置到全局变量。"""
    global BASE_OUTPUT_DIR, BASE_DEBUG_DIR, COURSE_URL, HEADLESS, AUTO_EXPORT_PDF, FORCE_REGRAB, OPEN_DIR_ON_COMPLETE
    if settings is None:
        settings = load_settings()
    # 用户选择的就是输出根目录，时间戳子目录由 run() 创建；debug 放在其下的 debug/ 中
    BASE_OUTPUT_DIR = settings.get("output_dir", DEFAULT_OUTPUT_DIR)
    BASE_DEBUG_DIR = os.path.join(BASE_OUTPUT_DIR, "debug")
    # 课程 URL 不从此恢复：输入框每次启动都保持为空，由用户自行粘贴课程 URL。
    # 它只作为会话内的临时值（由前端显式传入），不回填为默认值，避免旧 URL 复发。
    COURSE_URL = ""
    if "headless" in settings:
        HEADLESS = bool(settings["headless"])
    if "auto_export_pdf" in settings:
        AUTO_EXPORT_PDF = bool(settings["auto_export_pdf"])
    if "force_regrab" in settings:
        FORCE_REGRAB = bool(settings["force_regrab"])
    if "open_dir_on_complete" in settings:
        OPEN_DIR_ON_COMPLETE = bool(settings["open_dir_on_complete"])


# 启动时自动加载配置
apply_settings()


def output_dir() -> str:
    """获取本次运行的输出目录，包含课程名称与时间戳。"""
    if not RUN_ID:
        return BASE_OUTPUT_DIR
    suffix = f"{COURSE_NAME}_{RUN_ID}" if COURSE_NAME else RUN_ID
    return os.path.join(BASE_OUTPUT_DIR, suffix)


def debug_dir() -> str:
    """获取本次运行的 debug 目录，与输出目录同名。"""
    if not RUN_ID:
        return BASE_DEBUG_DIR
    suffix = f"{COURSE_NAME}_{RUN_ID}" if COURSE_NAME else RUN_ID
    return os.path.join(BASE_DEBUG_DIR, suffix)


def ensure_dirs():
    """创建本次运行所需的输出目录与 debug 目录。"""
    for d in (output_dir(), debug_dir()):
        if not os.path.exists(d):
            os.makedirs(d)


def load_state() -> dict:
    """读取 Playwright storage_state。"""
    if os.path.exists(STATE_FILE):
        try:
            with open(STATE_FILE, "r", encoding="utf-8") as f:
                return json.load(f)
        except Exception:
            return None
    return None


def save_state(context):
    """保存 Playwright storage_state 到 STATE_FILE。

    不借助 Playwright 的 `storage_state(path=...)`（其底层 `open(...,"w")`
    使用进程默认编码，在打包/frozen 环境下易触发 "unknown encoding" 异常），
    改为自己取 storage_state 字典并以显式 UTF-8 写入，确保登录态可靠落盘。
    """
    try:
        state = context.storage_state()
        with open(STATE_FILE, "w", encoding="utf-8") as f:
            json.dump(state, f, ensure_ascii=False)
        return True
    except Exception as e:
        print(f"[warn] 保存 state.json 失败：{e}")
        return False
