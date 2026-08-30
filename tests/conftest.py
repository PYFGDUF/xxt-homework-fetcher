"""pytest 全局引导：把项目根目录加入 sys.path，保证 `import core / spider / exporters` 可用。

无论 pytest 从哪个目录启动，该文件都会定位到项目根（本文件所在目录的上一级）并注入 sys.path。
"""
import os
import sys

PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if PROJECT_ROOT not in sys.path:
    sys.path.insert(0, PROJECT_ROOT)