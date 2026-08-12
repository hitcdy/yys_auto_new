# core/device_assembler.py
"""
设备连接装配：统一两个 UI（qt_ui / gra_ui）的连接逻辑，消除重复。

截图链（自动按序尝试，前者不可用就跳过，不报错）：
    MuMu 强化 → 雷电强化 → ADB 基线
触摸链：
    MuMu 原生触摸 → minitouch → ADB input

通道选择全自动，无需 UI 开关。MuMu 触摸启用前强制校验 display 尺寸与
ADB 屏幕尺寸一致（对齐 MAA MumuController.cpp:40，否则点击全偏）。
"""

import struct
from typing import Optional, Tuple

from adb.adb_client import ADBClient
from adb.screenshot import ScreenCapturer
from adb.mumu_extras import MuMuExtras
from adb.minitouch import MinitouchChannel
from vision.template_matcher import TemplateMatcher
from vision.detector import Detector
from core.game_controller import GameController
from core.bot_controller import BotController

try:
    from adb.ld_extras import LDExtras
except Exception:  # 非平台/缺依赖时也不阻断（仅失去雷电强化）
    LDExtras = None  # type: ignore


def _adb_screen_size(adb: ADBClient) -> Tuple[int, int]:
    """获取设备屏幕尺寸。主路径：screencap header；备用：wm size。"""
    # 主路径：复用 screencap raw 头部（w, h 在前 8 字节，与 screenshot.py 一致）
    try:
        data = adb.screencap()
        if data and len(data) >= 12:
            w, h, _fmt = struct.unpack_from("<III", data, 0)
            if w > 0 and h > 0:
                return w, h
    except Exception:
        pass
    # 备用：wm size 解析 "Physical size: WxH"
    try:
        out = adb._run(["shell", "wm", "size"])
        for token in out.replace(",", " ").split():
            if "x" in token:
                parts = token.split("x")
                if len(parts) == 2 and parts[0].isdigit() and parts[1].isdigit():
                    return int(parts[0]), int(parts[1])
    except Exception:
        pass
    return 0, 0


def assemble_device(
    device_id: str,
    mumu_path: str = "",
    ld_path: str = "",
    ocr_engine=None,
):
    """
    装配设备连接，返回:
        (adb, capturer, matcher, detector, game_ctrl, bot, status_str)

    status_str 汇总各通道生效/跳过情况，供 UI 状态栏显示。
    模板加载由调用方在返回后执行（matcher.load_templates(...)）。
    """
    adb = ADBClient(device_id=device_id)
    capturer = ScreenCapturer(adb)
    status_parts = []
    touch_channel = None
    mumu_extras = None

    adb_w, adb_h = _adb_screen_size(adb)

    # === 截图链 + 触摸链：MuMu ===
    if MuMuExtras.is_supported() and mumu_path and MuMuExtras.find_dll(mumu_path):
        mumu_idx = MuMuExtras.get_mumu_index(device_id)
        if mumu_idx is not None:
            try:
                mumu_extras = MuMuExtras(mumu_path, mumu_idx)
                capturer.set_extras(mumu_extras)
                status_parts.append(f"MuMu截图[实例{mumu_idx}]")
            except Exception as e:
                mumu_extras = None
                status_parts.append(f"MuMu截图跳过:{e}")
        else:
            status_parts.append("MuMu截图跳过:无法解析实例编号")
    # mumu_path 为空也记一下，便于用户判断为何没启用
    elif MuMuExtras.is_supported() and not mumu_path:
        status_parts.append("MuMu截图跳过:未配置MuMu路径")

    # MuMu 触摸：需尺寸校验（对齐 MumuController.cpp:40）
    if mumu_extras is not None and getattr(mumu_extras, "input_available", False):
        if adb_w > 0 and adb_h > 0:
            mw, mh = mumu_extras.get_display_size()
            if (mw, mh) == (adb_w, adb_h):
                touch_channel = mumu_extras
                status_parts.append("MuMu触摸")
            else:
                status_parts.append(f"MuMu触摸尺寸不符({mw}x{mh}≠{adb_w}x{adb_h})")
        else:
            status_parts.append("MuMu触摸跳过:无法获取屏幕尺寸")

    # === 截图链：雷电（MuMu 截图未生效时尝试）===
    if mumu_extras is None and LDExtras is not None and LDExtras.is_supported():
        try:
            ld_dir = ld_path or LDExtras.find_ld_install_dir()
            if ld_dir and LDExtras.find_dll(ld_dir):
                ld_idx = LDExtras.get_ld_index(device_id)
                if ld_idx is not None:
                    ld_pid = LDExtras.get_ld_pid(ld_dir, ld_idx)
                    if ld_pid is not None and ld_pid > 0 and adb_w > 0 and adb_h > 0:
                        ld = LDExtras(ld_dir, ld_idx, ld_pid, adb_w, adb_h)
                        capturer.set_extras(ld)
                        status_parts.append(f"雷电截图[实例{ld_idx}]")
                    else:
                        status_parts.append("雷电截图跳过:无法获取pid或尺寸")
                else:
                    status_parts.append("雷电截图跳过:无法解析实例编号")
            else:
                status_parts.append("雷电截图跳过:未找到安装目录或DLL")
        except Exception as e:
            status_parts.append(f"雷电截图跳过:{e}")

    # === 触摸链：minitouch（MuMu 触摸未生效时）===
    if touch_channel is None and adb_w > 0 and adb_h > 0:
        try:
            touch_channel = MinitouchChannel(adb, adb_w, adb_h)
            status_parts.append("minitouch触摸")
        except Exception as e:
            touch_channel = None
            status_parts.append(f"minitouch跳过:{e}")

    adb.set_touch_channel(touch_channel)  # None → tap/swipe 回退 adb input

    # === 装配业务对象 ===
    matcher = TemplateMatcher()
    detector = Detector(matcher, ocr_engine, capturer)
    game_ctrl = GameController(detector, adb)
    bot = BotController(game_ctrl, interval=1.0)

    status = f"已连接: {device_id} [" + ", ".join(status_parts) + "]"
    return adb, capturer, matcher, detector, game_ctrl, bot, status
