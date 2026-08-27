#!/usr/bin/env python3
"""
SwiftUI 前端 <-> Python 引擎的 NDJSON 桥接进程。

通信协议（每行一个 JSON，stdout 事件 / stdin 命令）：
  命令  : {"id": <int>, "cmd": <str>, "params": {...}}
  应答  : {"id": <int>, "ok": true, "result": {...}}
          {"id": <int>, "ok": false, "error": "<message>"}
  事件  : {"kind": <str>, "value": {...}}

事件 kind：
  log         value.{message, level}
  progress    value.{current, total, title}
  loginPrompt value.{message, request_login}
  done        value.{success, message, output_dir}
  error       value.{message}

说明：
  长操作在后台线程执行，主循环只负责读 stdin（这样登录完成 login_done 命令
  可以在 load/run 阻塞等待登录时被及时消费，避免死锁）。
  引擎的 print() 输出被重定向为 log 事件。
"""
from __future__ import annotations

import json
import os
import re
import sys
import threading
import traceback

_APP_DIR = os.path.dirname(os.path.abspath(__file__))
if _APP_DIR not in sys.path:
    sys.path.insert(0, _APP_DIR)

import chaoxing_spider as cs  # noqa: E402
from core import config  # noqa: E402
from core import chromium as chromium_mod  # noqa: E402
import repair as repair_mod  # noqa: E402

# =====================================================================
# 输出通道：真正的 stdout 只用于 NDJSON；引擎 print 被重定向为 log 事件
# =====================================================================
_REAL_STDOUT = sys.stdout
_EMIT_LOCK = threading.Lock()


def _emit(event: dict):
    """写一行 NDJSON 事件（线程安全）。"""
    data = json.dumps(event, ensure_ascii=False)
    with _EMIT_LOCK:
        try:
            _REAL_STDOUT.write(data + "\n")
            _REAL_STDOUT.flush()
        except Exception:
            pass


class _StreamToEvents:
    """把文本流按行转成 log 事件。

    级别优先从行内 `[LEVEL]` 标签解析，而不是依赖所在流：
    Python logging 默认写到 stderr（会被判为 error），但里头的
    [INFO]/[WARN] 等普通日志应保持各自级别。
    """

    _LEVEL_TOKEN = re.compile(r"^.*?\[(DEBUG|INFO|WARN|WARNING|ERROR|CRITICAL)\]")

    def __init__(self, level: str):
        self.level = level
        self._buf = ""

    @staticmethod
    def _normalize_level(tag: str) -> str:
        t = (tag or "").upper()
        if t == "DEBUG":
            return "debug"
        if t == "INFO":
            return "info"
        if t in ("WARN", "WARNING"):
            return "warn"
        return "error"  # ERROR / CRITICAL / 其它未知级别

    def write(self, s: str) -> int:
        self._buf += s
        while "\n" in self._buf:
            line, self._buf = self._buf.split("\n", 1)
            line = line.strip()
            if not line:
                continue
            m = self._LEVEL_TOKEN.match(line)
            if m:
                level = self._normalize_level(m.group(1))
                message = self._LEVEL_TOKEN.sub("", line, count=1).lstrip()
            else:
                level = self.level
                message = line
            _emit({"kind": "log", "value": {"message": message, "level": level}})
        return len(s)

    def flush(self):
        pass

    def isatty(self) -> bool:
        return False

    def writelines(self, lines):
        for ln in lines:
            self.write(ln)

    def fileno(self) -> int:
        return sys.__stdout__.fileno() if self.level == "info" else sys.__stderr__.fileno()


# 先确保底层 stdout 行缓冲（config.py 在 import 时已 line_buffering），再包装
if hasattr(sys.stdout, "reconfigure"):
    try:
        sys.stdout.reconfigure(line_buffering=True, write_through=True)
    except Exception:
        pass
sys.stdout = _StreamToEvents("info")
sys.stderr = _StreamToEvents("error")

# LOGGER 的控制台 handler 在 import 时绑定到了真实 stderr，会被 Swift 的
# readErr 一律判为 [error]。这里把它重定向到事件流，让 LOGGER 输出以正确级别进入 GUI。
from core import logger as _logger_mod
import logging as _logging

_ev_out = sys.stdout  # _StreamToEvents("info")
for _h in list(_logger_mod.LOGGER.handlers):
    if isinstance(_h, _logging.StreamHandler) and not isinstance(_h, _logging.handlers.RotatingFileHandler):
        try:
            _h.close()
        except Exception:
            pass
        _logger_mod.LOGGER.removeHandler(_h)
_console = _logging.StreamHandler(_ev_out)
_console.setLevel(_logging.INFO)
_console.setFormatter(_logging.Formatter("%(asctime)s [%(levelname)s] %(message)s", datefmt="%Y-%m-%d %H:%M:%S"))
_logger_mod.LOGGER.addHandler(_console)

# =====================================================================
# 引擎回调 -> 事件
# =====================================================================
def _progress_cb(current: int, total: int, title: str):
    _emit({"kind": "progress", "value": {"current": current, "total": total, "title": title}})


def _login_prompt_cb(message: str):
    _emit({"kind": "loginPrompt", "value": {"message": message, "request_login": True}})


def _login_qr_cb(image_b64: str, message: str):
    _emit({"kind": "loginQr", "value": {"image_b64": image_b64, "message": message or ""}})


def _login_success_cb(message: str):
    _emit({"kind": "loginSuccess", "value": {"message": message or "登录成功"}})


def _status_cb(url: str, title: str, status: str, progress: float | None = None,
               overall: float | None = None):
    value = {"url": url, "title": title, "status": status}
    # 作业内进度（0~1）仅在引擎有上报时携带，供 GUI 展示单个作业百分比进度
    if progress is not None:
        value["progress"] = round(progress, 3)
    # 总进度（0~1）：由单作业进度实时映射而来，供 GUI 总进度条与单作业进度联动
    if overall is not None:
        value["overall"] = round(overall, 3)
    _emit({"kind": "status", "value": value})


def _image_fail_cb(failed: int, title: str):
    _emit({"kind": "imageFail", "value": {"failed": failed, "title": title}})


cs.set_progress_callback(_progress_cb)
cs.set_login_prompt_callback(_login_prompt_cb)
config.set_login_qr_callback(_login_qr_cb)
config.set_login_success_callback(_login_success_cb)
cs.set_status_callback(_status_cb)
config.set_image_fail_callback(_image_fail_cb)

# 分发型启动：把内置的无头浏览器（chromium_headless_shell / ffmpeg）从 App 内
# 复制到用户可写目录（PLAYWRIGHT_BROWSERS_PATH），保证默认 headless 抓取离线可用；
# 完整 Chromium（登录组件）始终不内置，缺时按需下载。
def _copy_bundled_browsers():
    base = chromium_mod.browsers_dir()
    # 定位 App 内置的无头浏览器目录（Resources/ms-playwright）。
    # PyInstaller onedir：_MEIPASS = Resources/engine_xxt/_internal，向上两级的同层即 Resources；
    # 开发态（源码运行）无 _MEIPASS，退化为用 __file__ 推导（通常目录不存在，直接空操作）。
    try:
        root = sys._MEIPASS  # type: ignore[attr-defined]
    except AttributeError:
        root = os.path.dirname(os.path.abspath(__file__))
    bundle = os.path.normpath(os.path.join(root, "..", "..", "ms-playwright"))
    if not os.path.isdir(bundle):
        return
    try:
        os.makedirs(base, exist_ok=True)
    except Exception:
        return
    import shutil
    for name in os.listdir(bundle):
        src = os.path.join(bundle, name)
        dst = os.path.join(base, name)
        if name == chromium_mod._CHROMIUM_DIR:
            continue  # 完整 Chromium 不复制，按需下载
        if os.path.isdir(src) and not os.path.isdir(dst):
            try:
                shutil.copytree(src, dst)
                _emit({"kind": "log", "value": {"message": f"已就绪无头浏览器：{name}", "level": "info"}})
            except Exception as e:
                _emit({"kind": "log", "value": {"message": f"复制浏览器 {name} 失败：{e}", "level": "warn"}})

# 缓存最近一次加载的作业列表，供“选中并抓取”使用
_HOMEWORKS_CACHE: list = []


# =====================================================================
# 命令实现
# =====================================================================
def _normalize_settings(raw: dict) -> dict:
    """读取 Python 侧 settings 并转成 Swift 期望的字段。"""
    _a = cs.get_appearance()
    return {
        "course_url": cs.get_course_url() or "",
        "output_dir": config.BASE_OUTPUT_DIR,
        "show_browser": not cs.get_headless(),  # 与 Swift EngineSettings.headless 语义相反
        "auto_export_pdf": cs.get_auto_export_pdf(),
        "force_regrab": cs.get_force_regrab(),
        "open_dir_on_complete": config.get_open_dir_on_complete(),
        "show_source_url": config.get_show_source_url(),
        "appearance": _a,
    }


def _apply_settings(s: dict):
    if s.get("course_url"):
        cs.set_course_url(str(s["course_url"]))
    # show_browser 与 headless 语义相反；兼容两种键
    if "show_browser" in s:
        cs.set_headless(not bool(s["show_browser"]))
    elif "headless" in s:
        cs.set_headless(bool(s["headless"]))
    if "output_dir" in s and s["output_dir"]:
        cs.set_output_dir(str(s["output_dir"]))
    if "auto_export_pdf" in s:
        cs.set_auto_export_pdf(bool(s["auto_export_pdf"]))
    if "force_regrab" in s:
        cs.set_force_regrab(bool(s["force_regrab"]))
    if "open_dir_on_complete" in s:
        config.set_open_dir_on_complete(bool(s["open_dir_on_complete"]))
    if "show_source_url" in s:
        config.set_show_source_url(bool(s["show_source_url"]))
    if s.get("appearance") in ("system", "light", "dark"):
        cs.set_appearance(str(s["appearance"]))


def _do_load_homeworks(params: dict):
    """后台线程：加载作业列表并回结果事件。翻页过程中逐页回发 homeworkPage 供 UI 即时增量展示。"""
    url = params.get("url") or cs.get_course_url()

    def _emit_page(items):
        _emit({"kind": "homeworkPage", "value": {"items": items}})

    try:
        items = cs.load_homework_list(course_url=url, interactive=False, stream_callback=_emit_page)
        global _HOMEWORKS_CACHE
        _HOMEWORKS_CACHE = items
        _emit({"kind": "homeworkList", "value": {"items": items}})
        _emit({"kind": "done", "value": {"success": True, "message": f"已加载 {len(items)} 个作业"}})
    except Exception as e:
        _emit({"kind": "error", "value": {"message": f"加载作业失败：{e}"}})
        _emit({"kind": "done", "value": {"success": False, "message": f"加载作业失败：{e}"}})


def _do_standalone_login():
    """后台线程：独立发起扫码登录（设置中「登录学习通」）。"""
    try:
        cs.standalone_login()
    except Exception as e:
        _emit({"kind": "done", "value": {"success": False, "message": f"登录未完成：{e}"}})


def _do_run(params: dict):
    """后台线程：抓取选中的作业。"""
    ids = [str(i) for i in (params.get("homework_ids") or [])]
    if not ids:
        _emit({"kind": "done", "value": {"success": False, "message": "未指定要抓取的作业"}})
        return
    want = set(ids)

    def _matches(hw: dict) -> bool:
        # id / url / list_url 任一匹配即可；Swift 侧 id 可能退化为 url
        for key in ("id", "url", "list_url"):
            v = hw.get(key)
            if v is not None and str(v) in want:
                return True
        return False

    selected = [hw for hw in _HOMEWORKS_CACHE if _matches(hw)]
    if not selected:
        _emit({"kind": "done", "value": {
            "success": False,
            "message": "未在已加载的作业中找到选中的作业，请先重新加载作业列表",
        }})
        return
    try:
        cs.run(selected_homeworks=selected, interactive=False)
        _emit({"kind": "done", "value": {"success": True, "message": "抓取完成", "output_dir": cs.output_dir()}})
    except Exception as e:
        traceback.print_exc()
        _emit({"kind": "error", "value": {"message": f"抓取异常：{e}"}})
        _emit({"kind": "done", "value": {"success": False, "message": f"抓取异常：{e}"}})


def _do_repair(params: dict):
    """后台线程：修复选中的作业。"""
    paths = params.get("paths") or []
    if not paths:
        need_repair = repair_mod.collect_repair_items()
        paths = [r["path"] for r in need_repair]
    try:
        repair_mod.repair_selected([{"path": p, "title": os.path.basename(p), "url": ""} for p in paths])
        _emit({"kind": "done", "value": {"success": True, "message": "修复完成"}})
    except Exception as e:
        traceback.print_exc()
        _emit({"kind": "error", "value": {"message": f"修复异常:{e}"}})
        _emit({"kind": "done", "value": {"success": False, "message": f"修复异常:{e}"}})


def _do_export_pdf(params: dict):
    paths = params.get("paths") or []
    ok = 0
    for p in paths:
        try:
            from exporters.pdf import export_pdf
            if export_pdf(p):
                ok += 1
        except Exception as e:
            _emit({"kind": "log", "value": {"message": f"导出 PDF 失败 {p}: {e}", "level": "error"}})
    _emit({"kind": "done", "value": {"success": ok > 0, "message": f"已导出 {ok}/{len(paths)} 个 PDF"}})


def _run_on_worker(fn):
    threading.Thread(target=fn, daemon=True).start()


def _handle(cmd: str, params: dict) -> dict | None:
    """同步处理快速命令，返回应答；返回 None 表示已交给后台线程。"""
    if cmd == "get_settings":
        return {"ok": True, "result": _normalize_settings({})}
    if cmd == "set_settings":
        _apply_settings(params.get("settings") or {})
        return {"ok": True, "result": _normalize_settings(params.get("settings") or {})}
    if cmd == "stop":
        cs.force_stop()
        return {"ok": True, "result": {"stopped": True}}
    if cmd == "login_done":
        cs.notify_login_done()
        return {"ok": True, "result": {"logged_in": True}}
    if cmd == "login_cancel":
        # 用户在登录界面点击「取消登录」：置位取消标记，让登录流程尽快退出并终止任务
        config.cancel_login()
        return {"ok": True, "result": {"cancelled": True}}
    if cmd == "login_status":
        # 启动时检查是否已保存登录态（state.json 可读且非空）
        try:
            logged_in = config.load_state() is not None
        except Exception:
            logged_in = False
        return {"ok": True, "result": {"logged_in": logged_in}}
    if cmd == "login":
        # 独立发起扫码登录（设置中「登录学习通」入口）
        _run_on_worker(_do_standalone_login)
        return {"ok": True, "result": {"started": True}, "async": True}
    if cmd == "logout":
        # 退出登录：清除登录状态文件（state.json / cookies.txt）并关闭浏览器会话，
        # 避免复用旧的已登录上下文，下次抓取/扫码需重新登录。
        config.clear_browser_state()
        try:
            cs.force_stop()
        except Exception:
            pass
        removed = []
        for f in (config.STATE_FILE, config.COOKIE_FILE):
            try:
                if os.path.isfile(f):
                    os.remove(f)
                    removed.append(f)
            except Exception as e:
                _emit({"kind": "log", "value": {"message": f"清理 {f} 失败：{e}", "level": "error"}})
        msg = "已退出登录，并清除本地登录状态"
        if not removed:
            msg += "（无已保存的登录状态文件）"
        else:
            msg += "（" + "、".join(removed) + "）"
        _emit({"kind": "log", "value": {"message": msg, "level": "success"}})
        return {"ok": True, "result": {"removed": removed}}
    if cmd == "list_progress":
        items = cs.ProgressTracker().list_all()
        return {"ok": True, "result": {"items": items}}
    if cmd == "clear_progress":
        cs.ProgressTracker().clear()
        return {"ok": True, "result": {"cleared": True}}
    if cmd == "collect_repair_items":
        items = repair_mod.collect_repair_items()
        return {"ok": True, "result": {"repair_items": items}}
    if cmd == "load_homeworks":
        _run_on_worker(lambda: _do_load_homeworks(params))
        return {"ok": True, "result": {"accepted": True}}
    if cmd == "start":
        _run_on_worker(lambda: _do_run(params))
        return {"ok": True, "result": {"accepted": True}}
    if cmd == "repair_selected":
        _run_on_worker(lambda: _do_repair(params))
        return {"ok": True, "result": {"accepted": True}}
    if cmd == "export_pdf":
        _run_on_worker(lambda: _do_export_pdf(params))
        return {"ok": True, "result": {"accepted": True}}
    if cmd == "merge_docx":
        # 合并：优先使用最近一次输出子目录
        base = config.BASE_OUTPUT_DIR
        subdir = params.get("dir") or ""
        if not subdir:
            cand = [os.path.join(base, d) for d in sorted(os.listdir(base)) if os.path.isdir(os.path.join(base, d))]
            subdir = cand[-1] if cand else base
        from exporters.merge import merge_all_docx
        merge_all_docx(subdir)
        return {"ok": True, "result": {"dir": subdir}}
    return {"ok": False, "error": f"未知命令: {cmd}"}


# =====================================================================
# 主循环：读 stdin 命令
# =====================================================================
def main():
    while True:
        line = sys.stdin.readline()
        if not line:
            break  # Swift 端关闭 -> 退出
        line = line.strip()
        if not line:
            continue
        try:
            msg = json.loads(line)
        except Exception as e:
            _emit({"kind": "error", "value": {"message": f"命令解析失败：{e}"}})
            continue
        cmd_id = msg.get("id")
        cmd = msg.get("cmd")
        params = msg.get("params") or {}
        try:
            reply = _handle(cmd, params)
            if reply is not None:
                reply_payload = {"id": cmd_id}
                reply_payload.update(reply)
                _emit(reply_payload)
        except Exception as e:
            _emit({"id": cmd_id, "ok": False, "error": f"{e}"})


if __name__ == "__main__":
    # 配置加载、流重定向、回调注册均已完成；先就绪无头浏览器再进入主循环，
    # 此刻才视为“引擎真正就绪”，上报就绪日志让 Swift 端明确看到引擎已成功启动。
    _copy_bundled_browsers()
    _emit({"kind": "log", "value": {
        "message": "Python 引擎已启动，通信正常（pid %d）" % os.getpid(),
        "level": "info",
    }})
    try:
        main()
    except KeyboardInterrupt:
        pass
    except Exception as e:
        _emit({"kind": "error", "value": {"message": f"bridge 异常退出：{e}"}})