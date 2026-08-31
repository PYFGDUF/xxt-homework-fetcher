#!/usr/bin/env python3
"""
全局配置与状态模块。

所有原本在 chaoxing_spider.py 中通过全局变量共享的状态，仍在此模块中共享。
"""
from __future__ import annotations

import base64
import hashlib
import json
import os
import sys
import threading

from cryptography.hazmat.primitives.ciphers.aead import AESGCM

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
# 加密版登录态文件前缀，用于区分旧版明文 state.json
STATE_CIPHER_MAGIC = "xxt_state_v1:"
# 本机登录态密钥种子文件：用持久化密钥替代基于 mac/主机名的派生，
# 规避 uuid.getnode() 在跨进程/虚拟网卡下变化导致登录态“无法记忆”的问题。
LOGIN_KEY_FILE = "login.key"


def _machine_login_secret() -> str:
    """获取本机登录态密钥种子（持久化，不落盘明文登录态）。

    早期实现用 `uuid.getnode() + socket.gethostname() + sys.platform` 派生密钥，
    但 `uuid.getnode()` 在 macOS 上取的是第一块可用网卡的 MAC，遇到本地管理/虚拟
    网卡（VPN/TUN/蓝牙）或网卡排序变化时，同一台机不同进程会返回不同值，导致保存
    登录态的密文在跨进程（重启 App / 打包引擎）后因密钥变化而无法解密，表现为
    “登录没有记忆、每次都要重新扫码”。

    现改为：首次运行时写入一个随机密钥种子文件（仅当前用户可读写的 0600 权限），
    之后跨进程稳定复用同一密钥。密钥不与 state.json 一起导出，拷贝到其他机器仍无法
    解开，保留“防异地盗用”语义。
    """
    key_file = LOGIN_KEY_FILE
    # 已存在则直接复用
    try:
        with open(key_file, "r", encoding="ascii") as f:
            seed = f.read().strip()
        if seed:
            return "xxt-login-state::v1:" + seed
    except OSError:
        pass
    # 首次运行：生成持久密钥并落盘（0600）
    seed = hashlib.sha256(base64.b64encode(os.urandom(32))).hexdigest()
    try:
        fd = os.open(key_file, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
        with os.fdopen(fd, "w", encoding="ascii") as f:
            f.write(seed)
    except OSError:
        pass
    return "xxt-login-state::v1:" + seed


def _state_cipher_key() -> bytes:
    """派生 AES-256 密钥（32 字节）。"""
    return hashlib.sha256(_machine_login_secret().encode("utf-8")).digest()


def _encrypt_state_value(payload: bytes) -> str:
    """AES-GCM 加密，返回带前缀的 base64 密文。"""
    nonce = os.urandom(12)
    ciphertext = AESGCM(_state_cipher_key()).encrypt(nonce, payload, None)
    return STATE_CIPHER_MAGIC + base64.b64encode(nonce + ciphertext).decode("ascii")


def _decrypt_state_value(token: str) -> bytes:
    """解密 _encrypt_state_value 产生的密文。"""
    raw = base64.b64decode(token)
    nonce, ciphertext = raw[:12], raw[12:]
    return AESGCM(_state_cipher_key()).decrypt(nonce, ciphertext, None)


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

# GUI 作业状态回调：func(url: str, title: str, status: str, progress: float | None = None)
# progress 为该作业内部进度（0~1，None 表示无作业内进度信息）
_STATUS_CALLBACK = None

# 当前正在抓取的作业上下文（用于把单作业进度映射成总进度，供 GUI 总进度条实时联动）
_ACTIVE_HW_IDX = 0        # 当前作业在本次抓取序列中的序号（从 1 起）
_ACTIVE_HW_TOTAL = 0      # 本次待抓作业总数


def set_active_homework(idx: int, total: int):
    """记录本次抓取序列中当前正在处理的作业位置（供总进度联动计算）。id 从 1 起。"""
    global _ACTIVE_HW_IDX, _ACTIVE_HW_TOTAL
    _ACTIVE_HW_IDX = max(1, int(idx))
    _ACTIVE_HW_TOTAL = max(0, int(total))


def reset_active_homework():
    """清除当前作业上下文（抓取结束/新会话时调用）。"""
    global _ACTIVE_HW_IDX, _ACTIVE_HW_TOTAL
    _ACTIVE_HW_IDX = 0
    _ACTIVE_HW_TOTAL = 0


def _overall_progress(progress: float | None) -> float | None:
    """把「在途作业进度」映射成单调递增的 0..1 总进度。

    并发 worker 各自上报本作业内部进度：此处按线程登记在途进度并求和，
    结合线程安全的已完成计数得到总进度：
        overall = (已完成数 + 各在途作业进度之和) / 总量
    由于 `done_count()` 单调不减、单个 worker 的内部进度也只增不减，该式计算出的
    总进度不会倒退（避免了旧实现里共享 `_ACTIVE_HW_IDX` 被并发 worker 覆盖导致的回退）。
    """
    total = _ACTIVE_HW_TOTAL
    if total <= 0:
        return None
    p = max(0.0, min(1.0, progress if progress is not None else 0.0))
    with _DONE_LOCK:
        # 记录当前线程在途作业的内部进度；随后与已完成计数在同把锁下求和，
        # 避免「某个 worker 完工、其余 worker 仍在途」时读到不一致快照。
        _INFLIGHT_PROGRESS[threading.get_ident()] = p
        inflight_sum = min(float(total), sum(_INFLIGHT_PROGRESS.values()))
        done = _DONE_COUNT
    return min(1.0, (done + inflight_sum) / total)

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

# 是否在生成的 Word 文档中展示「来源：URL」行
SHOW_SOURCE_URL = True

# 「实验室」实验性功能——多线程并发抓取（默认关闭=串行；开启后在选择线程数内并发）
# worker 线程数上限 4，多浏览器并发抓不同作业页（GUI 选定模式尤其受益）
CONCURRENCY_MAX = 4
_CONCURRENCY_ENABLED = False
_CONCURRENCY_WORKERS = 2
DEFAULT_CONCURRENCY = 2

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


def get_show_source_url() -> bool:
    return SHOW_SOURCE_URL


def set_show_source_url(value: bool):
    """设置是否在 Word 文档中展示「来源：URL」，并保存到 settings.json。"""
    global SHOW_SOURCE_URL
    SHOW_SOURCE_URL = bool(value)
    settings = load_settings()
    settings["show_source_url"] = SHOW_SOURCE_URL
    save_settings(settings)


def set_concurrency(enabled: bool, workers: int):
    """设置实验室「多线程并发」开关与线程数，并保存到 settings.json。

    enabled=False 时实际抓取走串行（get_concurrency() 返回 1）；
    开启后线程数夹在 2..CONCURRENCY_MAX（4）之间。
    """
    global _CONCURRENCY_ENABLED, _CONCURRENCY_WORKERS
    _CONCURRENCY_ENABLED = bool(enabled)
    try:
        _CONCURRENCY_WORKERS = max(2, min(int(workers), CONCURRENCY_MAX))
    except Exception:
        _CONCURRENCY_WORKERS = DEFAULT_CONCURRENCY
    settings = load_settings()
    settings["concurrency_enabled"] = _CONCURRENCY_ENABLED
    settings["concurrency_workers"] = _CONCURRENCY_WORKERS
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
        except Exception as e:
            print(f"[debug] 进度回调异常：{e}")


# 并发 worker 模式下「已完成作业数」与「各 worker 在途作业进度」的线程安全共享态。
# 用同一把锁保护：`bump_done_count()` 的「完成+清除在途」与 `_overall_progress()`
# 的「读完成+读在途」在同把锁下原子完成，保证总进度单调不减、不倒退。
_DONE_LOCK = threading.Lock()
_DONE_COUNT = 0
_INFLIGHT_PROGRESS: dict[int, float] = {}  # 线程标识 -> 该线程当前作业内部进度(0..1)


def reset_done_count():
    """抓取开始前清零已完成计数与在途进度登记。"""
    global _DONE_COUNT
    with _DONE_LOCK:
        _DONE_COUNT = 0
        _INFLIGHT_PROGRESS.clear()


def done_count() -> int:
    """当前已完成的作业数（并发 worker 汇总）。"""
    with _DONE_LOCK:
        return _DONE_COUNT


def bump_done_count() -> int:
    """一个作业处理完成，递增计数、清除本线程在途进度，并返回新值。

    完成作业对应的「1 单位进度」需从在途桶转移到已完成桶：这里在同把锁下
    「+1 完成计数 且 pop 本线程在途条目」，与 _overall_progress 的读取保持一致，
    避免旧实现里共享下标被 worker 覆盖、或在途条目残留导致的进度重复/倒退。
    """
    global _DONE_COUNT
    with _DONE_LOCK:
        _DONE_COUNT += 1
        _INFLIGHT_PROGRESS.pop(threading.get_ident(), None)
        return _DONE_COUNT


def set_status_callback(callback):
    """设置作业状态回调，签名：callback(url: str, title: str, status: str, progress: float | None = None, overall: float | None = None)。"""
    global _STATUS_CALLBACK
    _STATUS_CALLBACK = callback


def _report_status(url: str, title: str, status: str, progress: float | None = None):
    """内部作业状态上报（completed / failed / in_progress 等）。
    progress 为该作业内部进度（0~1），用于 GUI 展示单个作业的百分比进度。
    同时附带 overall（0..1 总进度）供 GUI 的总进度条与单作业进度实时联动。"""
    overall = _overall_progress(progress) if status == "in_progress" else None
    if _STATUS_CALLBACK:
        try:
            _STATUS_CALLBACK(url, title, status, progress, overall)
        except Exception as e:
            print(f"[debug] 状态回调异常：{e}")


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
    """GUI 关闭或用户中断时调用。

    只设置停止标志，由运行线程在 should_stop() 检测点（wait_stable 轮询、翻页
    循环、runner 收尾的 finally）自行关闭浏览器/上下文。
    注意：绝不能在本线程直接调用 playwright 的 ctx.close()/brw.close()——
    浏览器/上下文绑定在运行线程的 greenlet 上，命令线程跨线程关闭会触发
    “greenlet.error: Cannot switch to a different thread”，并连带让运行线程
    后续操作全部报 “context closed”。由运行线程在正确 greenlet 内关闭才安全。
    """
    set_should_stop(True)
    print("[info] 收到停止信号，正在安全终止（由运行线程关闭浏览器）...")


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
    global BASE_OUTPUT_DIR, BASE_DEBUG_DIR, COURSE_URL, HEADLESS, AUTO_EXPORT_PDF, FORCE_REGRAB, OPEN_DIR_ON_COMPLETE, SHOW_SOURCE_URL, _CONCURRENCY_ENABLED, _CONCURRENCY_WORKERS
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
    if "show_source_url" in settings:
        SHOW_SOURCE_URL = bool(settings["show_source_url"])
    if "concurrency_enabled" in settings:
        _CONCURRENCY_ENABLED = bool(settings["concurrency_enabled"])
    if "concurrency_workers" in settings:
        try:
            _CONCURRENCY_WORKERS = max(2, min(int(settings["concurrency_workers"]), CONCURRENCY_MAX))
        except Exception:
            _CONCURRENCY_WORKERS = DEFAULT_CONCURRENCY


# 启动时自动加载配置
apply_settings()


def get_concurrency() -> int:
    """返回实际生效的 worker 线程数。

    实验室「多线程并发」默认关闭 → 返回 1（串行抓取）；开启后在所选线程数
    （2..CONCURRENCY_MAX=4）内并发。关闭意味着与旧版单线程行为一致。
    """
    if not _CONCURRENCY_ENABLED:
        return 1
    return max(2, min(_CONCURRENCY_WORKERS, CONCURRENCY_MAX))


def get_concurrency_enabled() -> bool:
    """实验室「多线程并发」开关当前值（用于设置回读，使 GUI 显示与持久化一致）。"""
    return _CONCURRENCY_ENABLED


def get_concurrency_workers() -> int:
    """实验室「多线程并发」所选线程数（2..CONCURRENCY_MAX=4）。"""
    return max(2, min(_CONCURRENCY_WORKERS, CONCURRENCY_MAX))


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
    """读取 Playwright storage_state，解密密文还原为明文 dict。

    支持旧版明文 state.json：解密失败且能按 JSON 解析时沿用（下次保存会转密文），
    保证升级后已登录用户仍能保持登录态。
    """
    if not os.path.exists(STATE_FILE):
        return None
    try:
        with open(STATE_FILE, "r", encoding="utf-8") as f:
            text = f.read()
    except Exception:
        return None
    if text.startswith(STATE_CIPHER_MAGIC):
        try:
            return json.loads(
                _decrypt_state_value(text[len(STATE_CIPHER_MAGIC):]).decode("utf-8"))
        except Exception:
            # 密文损坏或本机标识变化导致无法解密，视为未登录
            return None
    # 兼容旧版明文 state.json：就地加密重写，避免升级后仍残留明文登录态
    try:
        state = json.loads(text)
    except Exception:
        return None
    try:
        payload = json.dumps(state, ensure_ascii=False, separators=(",", ":")).encode("utf-8")
        with open(STATE_FILE, "w", encoding="ascii") as f:
            f.write(_encrypt_state_value(payload))
    except Exception:
        pass
    return state


def save_state(context):
    """保存 Playwright storage_state 到 STATE_FILE（AES-GCM 加密）。

    不借助 Playwright 的 `storage_state(path=...)`（其底层 `open(...,"w")`
    使用进程默认编码，在打包/frozen 环境下易触发 "unknown encoding" 异常），
    改为自己取 storage_state 字典、加密后以显式 UTF-8 写入，避免登录态明文落盘。
    """
    try:
        state = context.storage_state()
        payload = json.dumps(state, ensure_ascii=False, separators=(",", ":")).encode("utf-8")
        with open(STATE_FILE, "w", encoding="ascii") as f:
            f.write(_encrypt_state_value(payload))
        return True
    except Exception as e:
        print(f"[warn] 保存 state.json 失败：{e}")
        return False
