# adb/ld_extras.py
"""
雷电模拟器(LDPlayer)截图增强：ctypes 复刻 MAA LDExtras。

依赖雷电安装目录下的 ldopengl64.dll，导出 C 函数：
    CreateScreenShotInstance(unsigned inst_index, unsigned pid) -> IScreenShotClass*
返回的 IScreenShotClass 是 C++ 抽象类，cap()/release() 为虚函数。
ctypes 通过解析对象 vtable 调用这两个虚函数。

⚠️ 已知风险：IScreenShotClass 头文件(LD/dnopengl/dnopengl.h)不在手，
   vtable 偏移按"cap 在槽0、release 在槽1"实现。若该类有虚析构，
   MSVC 会在 vtable 头部占 1-2 槽，实际偏移需上移。
   调用失败时 __init__ 抛 RuntimeError，由 device_assembler 捕获后
   回退到 ADB 截图——链式目标不受影响。需在雷电环境实测确认偏移。

参照：MaaAssistantArknights src/MaaCore/Controller/LDExtras.cpp/.h
"""

import ctypes
import os
import platform
import subprocess
import winreg
from typing import Optional, Tuple

import cv2
import numpy as np


class LDExtras:
    """雷电截图增强。构造失败（DLL 缺失/版本不支持/vtable 调用失败）抛 RuntimeError。"""

    def __init__(self, ld_path: str, inst_index: int, pid: int, width: int, height: int):
        if not LDExtras.is_supported():
            raise RuntimeError(f"当前平台不支持雷电增强: {platform.system()}")

        dll_path = LDExtras.find_dll(ld_path)
        if not dll_path:
            raise RuntimeError(f"未找到 ldopengl64.dll: {ld_path}")

        try:
            self._lib = ctypes.WinDLL(dll_path)
        except OSError as e:
            raise RuntimeError(f"加载 DLL 失败: {dll_path}: {e}")

        # CreateScreenShotInstance(unsigned inst_index, unsigned pid) -> IScreenShotClass*
        try:
            self._lib.CreateScreenShotInstance.restype = ctypes.c_void_p
            self._lib.CreateScreenShotInstance.argtypes = [ctypes.c_uint, ctypes.c_uint]
        except (AttributeError, OSError) as e:
            raise RuntimeError(f"DLL 未导出 CreateScreenShotInstance: {e}")

        ptr = self._lib.CreateScreenShotInstance(inst_index, pid)
        if not ptr:
            raise RuntimeError(f"CreateScreenShotInstance 返回 NULL (inst={inst_index}, pid={pid})")

        self._inst_ptr = ptr
        self._width = int(width)
        self._height = int(height)

        # 解析 vtable：对象首字段是 vptr，指向虚函数表。
        # ⚠️ 假设 cap 在槽0、release 在槽1（待雷电环境验证）。
        try:
            vptr = ctypes.cast(ptr, ctypes.POINTER(ctypes.c_void_p))[0]
            vtbl = ctypes.cast(vptr, ctypes.POINTER(ctypes.c_void_p))
            self._cap_fn_addr = vtbl[0]
            self._release_fn_addr = vtbl[1]
            # cap(this) -> void* (返回 BGR 像素缓冲区指针)
            self._cap_fn = ctypes.CFUNCTYPE(ctypes.c_void_p, ctypes.c_void_p)(self._cap_fn_addr)
            # release(this) -> void
            self._release_fn = ctypes.CFUNCTYPE(None, ctypes.c_void_p)(self._release_fn_addr)
        except Exception as e:
            raise RuntimeError(f"vtable 解析失败（偏移可能需调整）: {e}")

    def screencap(self) -> np.ndarray:
        """抓帧，返回 BGR np.ndarray（与 ScreenCapturer 输出一致）。"""
        pixels = self._cap_fn(self._inst_ptr)
        if not pixels:
            raise RuntimeError("LD cap() 返回 NULL")
        # 雷电返回 BGR（3通道），尺寸 display_width * display_height * 3
        count = self._width * self._height * 3
        raw = np.ctypeslib.as_array(
            ctypes.cast(pixels, ctypes.POINTER(ctypes.c_uint8)),
            shape=(self._height, self._width, 3),
        ).copy()  # 拷贝，下次 cap 会覆盖同一缓冲区
        if raw.size != count:
            raise RuntimeError(f"LD 像素数不符: 期望 {count}, 实际 {raw.size}")
        return cv2.flip(raw, 0)  # 垂直翻转，对齐 LDExtras.cpp:71

    def close(self):
        if getattr(self, "_release_fn", None) is not None and getattr(self, "_inst_ptr", 0):
            try:
                self._release_fn(self._inst_ptr)
            except Exception:
                pass
            self._inst_ptr = 0

    def __del__(self):
        try:
            self.close()
        except Exception:
            pass

    # =====================================
    # 静态工具方法（供 device_assembler 探测可用条件）
    # =====================================
    @staticmethod
    def is_supported() -> bool:
        return platform.system() == "Windows"

    @staticmethod
    def find_dll(ld_path: str) -> Optional[str]:
        """在雷电安装目录下查找 ldopengl64.dll。"""
        if not ld_path or not os.path.isdir(ld_path):
            return None
        full = os.path.join(ld_path, "ldopengl64.dll")
        return full if os.path.isfile(full) else None

    @staticmethod
    def get_ld_index(address: str) -> Optional[int]:
        """从 ADB 设备地址解析雷电实例编号（复刻 MAA get_ld_index）。"""
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
        # 127.0.0.1:5555 形式
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
        if port < 5555:
            return None
        return (port - 5555) // 2

    @staticmethod
    def get_ld_pid(ld_path: str, inst_index: int) -> Optional[int]:
        """调 ldconsole.exe list2 解析指定实例的 pid（第6列）。"""
        exe = os.path.join(ld_path, "ldconsole.exe")
        if not os.path.isfile(exe):
            return None
        try:
            result = subprocess.run(
                [exe, "list2"],
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True,
                timeout=10,
            )
        except Exception:
            return None
        for line in result.stdout.splitlines():
            parts = line.split(",")
            # 格式: index,title,top_wnd,bind_wnd,android_wnd,pid,...
            if len(parts) < 6:
                continue
            try:
                if int(parts[0]) == inst_index:
                    return int(parts[5])
            except ValueError:
                continue
        return None

    @staticmethod
    def find_ld_install_dir() -> Optional[str]:
        """读注册表探测雷电安装目录（ldplayer9 / ldplayer14 / mrfz）。"""
        for reg_path in (r"Software\leidian\ldplayer9", r"Software\leidian\ldplayer14", r"Software\mrfz\mrfz"):
            try:
                with winreg.OpenKey(winreg.HKEY_CURRENT_USER, reg_path) as key:
                    install_dir, _ = winreg.QueryValueEx(key, "InstallDir")
                    if install_dir and os.path.isdir(install_dir):
                        return install_dir
            except OSError:
                continue
        return None
