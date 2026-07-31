# adb/mumu_extras.py
"""
MuMu 截图增强：ctypes 复刻 MAA 的 MumuExtras。

绕过 ADB screencap，直接通过 MuMu 的 external_renderer_ipc.dll 从模拟器显存抓帧。
仅 Windows + MuMu 模拟器可用；初始化或截图失败时由调用方回退到 ADB 截图。

参考：MaaAssistantArknights src/MaaCore/Controller/MumuExtras.cpp
"""

import os
import platform
import ctypes
from typing import Optional

import numpy as np
import cv2

# MuMu 安装目录下 external_renderer_ipc.dll 的候选相对路径（新版本优先，与 MAA 一致）
_CANDIDATE_DLL_PATHS = [
    "nx_device/15.0/shell/sdk/external_renderer_ipc.dll",  # MuMu 6.0
    "nx_device/12.0/shell/sdk/external_renderer_ipc.dll",  # MuMu 5.0 / MuMu 12
    "shell/sdk/external_renderer_ipc.dll",                 # MuMu 旧版本
    "nx_main/sdk/external_renderer_ipc.dll",               # nx_main 下的位置
]


class MuMuExtras:
    """MuMu 截图增强（仅截图，不含触控）。"""

    def __init__(self, mumu_path: str, inst_index: int):
        if not MuMuExtras.is_supported():
            raise RuntimeError(f"当前平台不支持 MuMu 截图增强: {platform.system()}")

        self.mumu_path = mumu_path
        self.inst_index = inst_index
        self._handle = 0
        self._display_id = 0
        self._width = 0
        self._height = 0
        self._buffer = None
        self._lib = None

        dll_path = MuMuExtras.find_dll(mumu_path)
        if not dll_path:
            raise RuntimeError(f"未找到 external_renderer_ipc.dll，检查 MuMu 路径: {mumu_path}")

        try:
            self._lib = ctypes.WinDLL(dll_path)
        except OSError as e:
            raise RuntimeError(f"加载 DLL 失败: {dll_path}: {e}")

        # 声明函数签名（参数类型据 MAA 用法推断，导出符号已验证）
        # nemu_connect(const wchar_t* path, int inst_index) -> int handle
        self._lib.nemu_connect.restype = ctypes.c_int
        self._lib.nemu_connect.argtypes = [ctypes.c_wchar_p, ctypes.c_int]

        # nemu_disconnect(int handle)
        self._lib.nemu_disconnect.restype = ctypes.c_int
        self._lib.nemu_disconnect.argtypes = [ctypes.c_int]

        # nemu_get_display_id(int handle, const char* pkg, int screen) -> int
        self._lib.nemu_get_display_id.restype = ctypes.c_int
        self._lib.nemu_get_display_id.argtypes = [ctypes.c_int, ctypes.c_char_p, ctypes.c_int]

        # nemu_capture_display(int handle, int disp_id, int buf_size,
        #                      int* w, int* h, void* buf) -> int  (0 = 成功)
        self._lib.nemu_capture_display.restype = ctypes.c_int
        self._lib.nemu_capture_display.argtypes = [
            ctypes.c_int, ctypes.c_int, ctypes.c_int,
            ctypes.POINTER(ctypes.c_int), ctypes.POINTER(ctypes.c_int), ctypes.c_void_p,
        ]

        # 连接 MuMu
        self._handle = self._lib.nemu_connect(mumu_path, inst_index)
        if self._handle == 0:
            raise RuntimeError(f"nemu_connect 失败: path={mumu_path}, index={inst_index}")

        # 获取 display id：用 "default"（最前端 tab），免去包名探测
        self._display_id = self._lib.nemu_get_display_id(self._handle, b"default", 0)
        if self._display_id < 0:
            # 旧版本或失败时回退到主 display 0
            self._display_id = 0

        # 首帧探测尺寸（buffer 传 NULL，仅查询 width/height）
        w = ctypes.c_int(0)
        h = ctypes.c_int(0)
        ret = self._lib.nemu_capture_display(
            self._handle, self._display_id, 0, ctypes.byref(w), ctypes.byref(h), None
        )
        # MuMu 文档写反了：0 才是成功
        if ret != 0:
            raise RuntimeError(f"nemu_capture_display 探测尺寸失败: ret={ret}")
        self._width = w.value
        self._height = h.value
        if self._width <= 0 or self._height <= 0:
            raise RuntimeError(f"无效的显示尺寸: {self._width}x{self._height}")

        self._buffer = (ctypes.c_ubyte * (self._width * self._height * 4))()

    def screencap(self) -> np.ndarray:
        """抓帧，返回 BGR np.ndarray（与 ScreenCapturer.capture 输出一致）。"""
        if not self._handle:
            raise RuntimeError("MuMuExtras 未初始化或已关闭")

        w = ctypes.c_int(self._width)
        h = ctypes.c_int(self._height)
        ret = self._lib.nemu_capture_display(
            self._handle, self._display_id, ctypes.sizeof(self._buffer),
            ctypes.byref(w), ctypes.byref(h), self._buffer
        )
        if ret != 0:
            raise RuntimeError(f"nemu_capture_display 失败: ret={ret}")

        raw = np.frombuffer(self._buffer, dtype=np.uint8).reshape(self._height, self._width, 4)
        bgr = cv2.cvtColor(raw, cv2.COLOR_RGBA2BGR)
        return cv2.flip(bgr, 0)  # 垂直翻转，与 MAA 一致

    def close(self):
        if self._handle and self._lib:
            try:
                self._lib.nemu_disconnect(self._handle)
            except Exception:
                pass
        self._handle = 0

    def __del__(self):
        try:
            self.close()
        except Exception:
            pass

    # =====================================
    # 静态工具方法（供 UI 探测可用条件）
    # =====================================
    @staticmethod
    def is_supported() -> bool:
        """是否在 Windows 平台（ctypes.WinDLL 仅 Windows 可用）。"""
        return platform.system() == "Windows"

    @staticmethod
    def find_dll(mumu_path: str) -> Optional[str]:
        """在 MuMu 安装目录下查找 external_renderer_ipc.dll，返回首个命中路径。"""
        if not mumu_path or not os.path.isdir(mumu_path):
            return None
        for rel in _CANDIDATE_DLL_PATHS:
            full = os.path.join(mumu_path, rel)
            if os.path.isfile(full):
                return full
        return None

    @staticmethod
    def get_mumu_index(address: str) -> Optional[int]:
        """从 ADB 设备地址解析 MuMu 实例编号（复刻 MAA get_mumu_index）。"""
        if not address:
            return None

        # emulator-5554 形式
        if address.startswith("emulator-"):
            try:
                port = int(address[len("emulator-"):])
            except ValueError:
                return None
            if port < 5554 or (port - 5554) % 2 != 0:
                return None
            return (port - 5554) // 2

        # 127.0.0.1:port 形式
        pos = address.find(":")
        if pos <= 0:
            return None
        host = address[:pos]
        if host not in ("127.0.0.1", "localhost"):
            return None
        port_str = address[pos + 1:]
        if not port_str.isdigit():
            return None
        port = int(port_str)

        if port >= 16384:
            # MuMu 12：port = 16384 + (index % 32) * 32 + floor(index/32) * 4
            k = (port - 16384) // 4
            return ((k & 7) << 5) | (k >> 3)
        if port == 7555:
            return 0  # MuMu 6 老端口
        if port >= 5555:
            return (port - 5555) // 2
        return None
