#!/usr/bin/env python3
"""只读冒烟测试（有界）：通过 bridge 加载作业列表，验证引擎与真实后端连通。

不抓取、不下载、不写文件。仅发送 load_homeworks 命令，观察事件流。
若登录态失效，接口会在约数秒内返回 loginPrompt（不执行任何抓取）。
无论结果如何，测试都会在超时后干净地关闭桥接进程。
"""
import json
import os
import subprocess
import sys
import time

APP_DIR = os.path.abspath(os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", ".."))
PYTHON = os.environ.get("XXT_PYTHON", "python3")
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

# 发送 load_homeworks 命令
p.stdin.write(json.dumps({"id": 100, "cmd": "load_homeworks", "params": {}}) + "\n")
p.stdin.flush()
p.stdin.close()

events = []
seen_kind = {}
deadline = time.time() + 60  # 有界等待
try:
    while time.time() < deadline:
        import select
        r, _, _ = select.select([p.stdout], [], [], 5)
        if not r:
            continue
        line = p.stdout.readline()
        if not line:
            break
        try:
            obj = json.loads(line)
        except Exception as e:
            print(f"  非 JSON 行: {line!r} err={e}")
            continue
        events.append(obj)
        kind = obj.get("kind", obj.get("id"))
        seen_kind[kind] = seen_kind.get(kind, 0) + 1
        # 遇到 done/homeworkList/loginPrompt → 该阶段结束
        if obj.get("kind") in ("done", "homeworkList", "loginPrompt", "error"):
            print(f"  事件: kind={obj.get('kind')} <- {json.dumps(obj.get('value', {}), ensure_ascii=False)[:120]}")
        # 收到 done 即停止（避免无谓等待）
        if obj.get("kind") == "done":
            break
except Exception as e:
    print(f"  读取异常: {e}")
finally:
    try:
        p.terminate()
    except Exception:
        pass
    try:
        p.wait(timeout=10)
    except Exception:
        p.kill()

print("\n== 观察到的 kind 计数 ==")
for k, v in seen_kind.items():
    print(f"  {k}: {v}")

# 判定
kinds = set(seen_kind.keys())
if "homeworkList" in kinds:
    print("\n结论: 登录态有效，引擎成功加载了真实作业列表（只读，未抓取）。")
    n = next(e.get("value", {}).get("items") for e in events if e.get("kind") == "homeworkList")
    print(f"  作业数量: {len(n)}")
elif "loginPrompt" in kinds:
    print("\n结论: 会话需登录（loginPrompt）。登录态过期或 Cookie 无效，需用户重新登录。")
    print("  这是预期保护行为，未执行任何抓取。")
elif "error" in kinds:
    print("\n结论: 引擎报错。")
    for e in events:
        if e.get("kind") == "error":
            print("  ", e.get("value", {}).get("message"))
else:
    print("\n结论: 超时未得到明确结果，桥接可能卡在浏览器等待。")