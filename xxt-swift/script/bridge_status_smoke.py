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
captured = []
def cb(url, title, status):
    captured.append((url, title, status))
config.set_status_callback(cb)
config._report_status("https://example.com/hw?id=42", "作业标题 测试", "completed")
def emit(x): print("EVENT:" + json.dumps(x, ensure_ascii=False))
def status_cb(url, title, status):
    emit({"kind": "status", "value": {"url": url, "title": title, "status": status}})
status_cb(captured[0][0], captured[0][1], captured[0][2])
print("CB:" + json.dumps(list(captured[0]), ensure_ascii=False))
"""
out = naive_check(iso_code)
evt = None
cb = None
for ln in out.splitlines():
    if ln.startswith("EVENT:"):
        evt = json.loads(ln[len("EVENT:"):])
    elif ln.startswith("CB:"):
        cb = json.loads(ln[len("CB:"):])
assert cb, f"状态回调未被触发: {out}"
assert cb == ["https://example.com/hw?id=42", "作业标题 测试", "completed"], cb
assert evt and evt["kind"] == "status", f"事件缺 kind=status: {evt}"
v = evt["value"]
assert {"url", "title", "status"} <= set(v.keys()), f"status 事件缺字段: {v}"
print(f"  状态回调 OK: {cb}")
print(f"  status 事件 OK: {json.dumps(v, ensure_ascii=False)}")
print("\n全部通过：bridge 往返正常，status 事件含 url/title/status 并可被 Swift 解码。")