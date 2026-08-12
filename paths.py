# paths.py
"""
项目路径基准：一切文件定位以此为准，摆脱对当前工作目录 (CWD) 的依赖。

历史问题：main.py 的模板路径、config.py 的 config.json 都用相对路径，
依赖 os.getcwd() 解析；从非 yys_auto/ 目录启动会概率性失效。
本模块基于 __file__ 绝对定位（打包时用 _MEIPASS），与 vision/ocr_engine.py 的做法一致。
"""

import os
import sys

if getattr(sys, "frozen", False):
    # PyInstaller 打包后，资源解压到 _MEIPASS
    BASE_DIR = sys._MEIPASS  # type: ignore[attr-defined]
else:
    BASE_DIR = os.path.dirname(os.path.abspath(__file__))

TEMPLATE_DIR = os.path.join(BASE_DIR, "template")
CONFIG_PATH = os.path.join(BASE_DIR, "config.json")
RESOURCE_DIR = os.path.join(BASE_DIR, "resource")
MINITOUCH_DIR = os.path.join(RESOURCE_DIR, "minitouch")
