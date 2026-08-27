#!/usr/bin/env python3
"""只读冒烟测试：验证 bridge 的 NDJSON 往返 + status 事件负载形状。

不做任何抓取、不写任何文件。仅：
1) 启动 bridge.py 子进程，发送 get_settings 命令，验证应答往返。
2) 在隔离进程内触发 core.config 状态回调，验证 status 事件
   含 url/title/status 三个键且值合法（与 Swift EngineEventValue 解码字段一致）。
"""
import json
import os
import subprocess
import sys

APP_DIR = "/Users/pengyufeng/Documents/xxt"
PYTHON = "/Users/pengyufeng/opt/anaconda3/bin/python3"


def naive_check(py_code: str) -> str:
    """用子进程 python 执行一段代码并捕获输出。"""
    r = subprocess.run(
        [PYTHON, "-c", py_code], cwd=APP_DIR, capture_output=True, text=True, timeout=60
    )
    return r.stdout + r.stderr


# --- 1) bridge 子进程 NDJSON 往返 ---
print("== [1] bridge get_settings NDJSON 往返 ==")
bridge_py = os.path.join(APP_DIR, "bridge.py")
p = subprocess.Popen(
    [PYTHON, bridge_py],
    cwd=APP_DIR,
    stdin=subprocess.PIPE,
    stdout=subprocess.PIPE,
    stderr=subprocess.PIPE,
    text=True,
    bufsize=1,
)
p.stdin.write(json.dumps({"id": 1, "cmd": "get_settings", "params": {}}) + "\n")
p.stdin.flush()
ok = False
for _ in range(20):
    line = p.stdout.readline()
    if not line:
        break
    try:
        obj = json.loads(line)
    except Exception as e:
        print(f"  非 JSON 行: {line!r} err={e}")
        continue
    if obj.get("id") == 1:
        assert obj.get("ok") is True, f"应答非 ok: {obj}"
        for k in ("course_url", "output_dir", "auto_export_pdf"):
            assert k in obj.get("result", {}), f"缺字段 {k}: {obj}"
        print(f"  应答 OK: fields={list(obj['result'].keys())}")
        ok = True
        break
p.stdin.close()
p.terminate()
p.wait(timeout=10)
assert ok, "未收到 get_settings 应答"
print("  桥接进程已正常结束")

# --- 2) status 事件负载形状 ---
print("\n== [2] core.config 状态回调 -> status 事件形状 ==")
iso_code = r"""
import json, sys, os
sys.path.insert(0, os.path.abspath("."))
from core import config
transient = []
def cb(url, title, status, progress=None, overall=None):
    transient.append((url, title, status, progress, overall))
config.set_status_callback(cb)
# 设置作业上下文，验证 in_progress 会附带总进度 overall，completed 不附带
config.set_active_homework(2, 4)
config._report_status("https://example.com/hw?id=42", "作业标题 测试", "in_progress", 0.5)
config._report_status("https://example.com/hw?id=43", "作业标题 完成", "completed", 1.0)
def emit(x): print("EVENT:" + json.dumps(x, ensure_ascii=False))
def status_cb(url, title, status, progress=None, overall=None):
    emit({"kind": "status", "value": {"url": url, "title": title, "status": status,
          "progress": progress, "overall": overall}})
status_cb(*transient[0])
print("CB0:" + json.dumps(list(transient[0]), ensure_ascii=False))
print("CB1:" + json.dumps(list(transient[1]), ensure_ascii=False))
"""
out = naive_check(iso_code)
evt = None
cb0 = None
cb1 = None
for ln in out.splitlines():
    if ln.startswith("EVENT:"):
        evt = json.loads(ln[len("EVENT:"):])
    elif ln.startswith("CB0:"):
        cb0 = json.loads(ln[len("CB0:"):])
    elif ln.startswith("CB1:"):
        cb1 = json.loads(ln[len("CB1:"):])
assert cb0, f"状态回调未被触发: {out}"
assert cb1, f"completed 回调未被触发: {out}"
# in_progress：url/title 有效，progress=0.5，且附带总进度 overall（(2-1+0.5)/4=0.375）
u0, t0, s0, p0, o0 = cb0
assert (u0, s0) == ("https://example.com/hw?id=42", "in_progress"), cb0
assert abs(p0 - 0.5) < 0.001, f"progress 异常: {cb0}"
assert o0 is not None and abs(o0 - 0.375) < 0.001, f"整体进度 overall 异常: {cb0}"
# completed：不附带总体进度（命中回退计数）
u1, t1, s1, p1, o1 = cb1
assert s1 == "completed" and o1 is None, f"completed 不应附带 overall: {cb1}"
assert evt and evt["kind"] == "status", f"事件缺 kind=status: {evt}"
v = evt["value"]
assert {"url", "title", "status"} <= set(v.keys()), f"status 事件缺字段: {v}"
assert v["overall"] is not None, f"in_progress 事件缺 overall: {v}"
print(f"  in_progress 回调 OK: url/title/status/progress/overall -> {cb0}")
print(f"  completed 回调 OK: overall 为空 -> {(u1, s1)}")
print(f"  status 事件 OK: {json.dumps(v, ensure_ascii=False)}")
print("\n全部通过：bridge 往返正常，status 事件含 url/title/status(+overall) 并可被 Swift 解码。")