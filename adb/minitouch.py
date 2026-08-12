# adb/minitouch.py
"""
minitouch 触摸通道：ctypes/子进程复刻 MAA MinitouchController。

工作流程：
1. 按 ABI 探测设备架构，推送 resource/minitouch/<arch>/minitouch 到 /data/local/tmp/。
2. 起 `adb shell /data/local/tmp/minitouch -i` 常驻交互进程，读 banner：
   `^ max_contacts size_1 size_2 max_pressure $`，算出 x/y 缩放系数。
3. tap/swipe 通过写文本协议（d/m/u/c）注入触摸事件，坐标按缩放映射到 evdev 坐标系。

参照：MaaAssistantArknights src/MaaCore/Controller/MinitouchController.cpp/.h
仅 Windows + 模拟器场景；二进制只随项目带 x86/x86_64（模拟器用）。
"""

import os
import subprocess
import threading
from typing import Optional, Tuple

from paths import MINITOUCH_DIR


# ABI 优先级（与 MAA config.json minitouchProgramsOrder 对齐，但本项目只带 x86 系）
_ARCH_BY_ABI = [
    ("x86_64", "x86_64"),
    ("x86", "x86"),
]

# minitouch 文本协议（每行一命令，\n 结尾）
# d <contact> <x> <y> <pressure>  手指按下
# m <contact> <x> <y> <pressure>  手指移动
# u <contact>                     手指抬起
# c                               commit（提交本批事件，commit 前不生效）
_CMD_DOWN = "d {contact} {x} {y} {pressure}\n"
_CMD_MOVE = "m {contact} {x} {y} {pressure}\n"
_CMD_UP = "u {contact}\n"
_CMD_COMMIT = "c\n"

_DEFAULT_SWIPE_INTERVAL_MS = 2  # 对齐 Minitoucher::DefaultSwipeDelay


class MinitouchChannel:
    """minitouch 触摸通道。构造即推送+启动；失败抛 RuntimeError，由调用方回退。"""

    def __init__(self, adb_client, width: int, height: int):
        self._adb = adb_client
        self._w = int(width)
        self._h = int(height)
        self._proc: Optional[subprocess.Popen] = None
        self._lock = threading.Lock()  # 单管道不能并发写（加速线程与主循环并发）
        # (max_x, max_y, max_pressure, x_scaling, y_scaling)
        self._props: Optional[Tuple[int, int, int, float, float]] = None
        self._start()

    # =====================================
    # 启动：推送二进制 + 拉起进程 + 读 banner
    # =====================================
    def _start(self):
        self._push_binary()
        cmd = self._adb._build_cmd(["shell", "/data/local/tmp/minitouch", "-i"])
        self._proc = subprocess.Popen(
            cmd,
            stdin=subprocess.PIPE,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            bufsize=1,
        )

        # 读 banner直到 '$'（对齐 MinitouchController.cpp:46-63）
        buf = ""
        while "$" not in buf:
            ch = self._proc.stdout.read(1)
            if not ch:
                stderr = ""
                try:
                    stderr = self._proc.stderr.read()
                except Exception:
                    pass
                raise RuntimeError(f"minitouch banner EOF (stderr={stderr[:200]})")
            buf += ch

        # 解析 `^ max_contacts size_1 size_2 max_pressure`
        caret = buf.find("^")
        if caret < 0:
            raise RuntimeError(f"minitouch banner 无 '^': {buf!r}")
        nl = buf.find("\n", caret)
        line = buf[caret + 1: nl if nl >= 0 else len(buf)]
        parts = line.split()
        if len(parts) < 4:
            raise RuntimeError(f"minitouch banner 解析失败: {line!r}")
        _max_contacts, s1, s2, max_pressure = int(parts[0]), int(parts[1]), int(parts[2]), int(parts[3])
        # 模拟器竖屏时输出可能反转，取较大为 x、较小为 y（对齐 MinitouchController.cpp:87-88）
        max_x, max_y = max(s1, s2), min(s1, s2)
        if self._w <= 0 or self._h <= 0:
            raise RuntimeError(f"无效的屏幕尺寸: {self._w}x{self._h}")
        self._props = (
            max_x, max_y, max_pressure,
            max_x / self._w, max_y / self._h,
        )

    def _push_binary(self):
        abi = self._detect_abi()
        arch = self._arch_for_abi(abi)
        if arch is None:
            raise RuntimeError(f"无匹配的 minitouch 二进制（设备 ABI={abi}，仅带 x86/x86_64）")
        src = os.path.join(MINITOUCH_DIR, arch, "minitouch")
        if not os.path.isfile(src):
            raise RuntimeError(f"minitouch 二进制不存在: {src}")
        self._adb._run(["push", src, "/data/local/tmp/minitouch"])
        self._adb._run(["shell", "chmod", "700", "/data/local/tmp/minitouch"])

    def _detect_abi(self) -> str:
        out = self._adb._run(["shell", "getprop", "ro.product.cpu.abilist"])
        abis = [a.strip() for a in out.split(",") if a.strip()]
        return abis[0] if abis else "armeabi-v7a"

    @staticmethod
    def _arch_for_abi(abi: str) -> Optional[str]:
        # 优先精确命中，再按子串放宽
        for key, arch in _ARCH_BY_ABI:
            if key in abi:
                return arch
        return None

    # =====================================
    # 写协议（线程安全 + 断连自愈）
    # =====================================
    def _write(self, s: str):
        with self._lock:
            if self._proc is None or self._proc.poll() is not None:
                self._start()  # 进程已退出，重拉起
            try:
                self._proc.stdin.write(s)
                self._proc.stdin.flush()
            except (BrokenPipeError, OSError, ValueError):
                # 管道断开，重拉起后重写一次（对齐 MinitouchController.cpp:114-121）
                self._start()
                self._proc.stdin.write(s)
                self._proc.stdin.flush()

    def _scale(self, x: int, y: int) -> Tuple[int, int]:
        _mx, _my, _mp, xs, ys = self._props
        return int(x * xs), int(y * ys)

    # =====================================
    # 对外接口（与 MuMuExtras.touch_* 语义平行）
    # =====================================
    def tap(self, x: int, y: int):
        if self._props is None:
            raise RuntimeError("minitouch 未初始化")
        _mx, _my, mp, _xs, _ys = self._props
        cx, cy = self._scale(x, y)
        # down + commit + up + commit
        self._write(_CMD_DOWN.format(contact=1, x=cx, y=cy, pressure=mp) + _CMD_COMMIT)
        self._write(_CMD_UP.format(contact=1) + _CMD_COMMIT)

    def swipe(self, x1: int, y1: int, x2: int, y2: int, duration: int = 300):
        if self._props is None:
            raise RuntimeError("minitouch 未初始化")
        _mx, _my, mp, _xs, _ys = self._props
        cx1, cy1 = self._scale(x1, y1)
        cx2, cy2 = self._scale(x2, y2)
        # 按时长分步，每步 _DEFAULT_SWIPE_INTERVAL_MS（对齐 Minitoucher::DefaultSwipeDelay）
        steps = max(1, duration // _DEFAULT_SWIPE_INTERVAL_MS)
        self._write(_CMD_DOWN.format(contact=1, x=cx1, y=cy1, pressure=mp) + _CMD_COMMIT)
        for i in range(1, steps + 1):
            cx = int(cx1 + (cx2 - cx1) * i / steps)
            cy = int(cy1 + (cy2 - cy1) * i / steps)
            self._write(_CMD_MOVE.format(contact=1, x=cx, y=cy, pressure=mp) + _CMD_COMMIT)
        self._write(_CMD_UP.format(contact=1) + _CMD_COMMIT)

    def close(self):
        with self._lock:
            if self._proc is not None:
                try:
                    self._proc.terminate()
                except Exception:
                    pass
                self._proc = None
