# -*- coding: utf-8 -*-
"""
PySide6 原生桌面 UI（替代 gra_ui.py）

- 静态 4 Tab，每 Tab 一个独立 BotController
- 控件/业务逻辑与 gra_ui 对齐
- 新增实时截图预览：QTimer 200ms 读 detector.get_preview()，
  BGR->QImage，QPainter 画命中框(红框+模板名)，贴 QLabel
- 状态区 5 项：QTimer 1s 刷新所有 Tab
"""

import sys
import time
import subprocess

import cv2
import numpy as np

from PySide6.QtCore import Qt, QTimer
from PySide6.QtGui import QImage, QPixmap, QPainter, QColor, QPen, QFont
from PySide6.QtWidgets import (
    QWidget, QMainWindow, QApplication, QTabWidget,
    QVBoxLayout, QHBoxLayout, QFormLayout,
    QPushButton, QComboBox, QLineEdit, QDoubleSpinBox, QCheckBox, QLabel,
    QSizePolicy,
)

from config import load_config, save_config
from core.device_assembler import assemble_device
from vision.ocr_engine import OCREngine
from adb.adb_client import ADBClient

# OCR 全局懒加载单例（与 gra_ui 一致，首次连接时初始化 Tesseract）
_ocr_engine = None


def _get_ocr_engine():
    global _ocr_engine
    if _ocr_engine is None:
        print("[OCR] 初始化 Tesseract...")
        _ocr_engine = OCREngine(debug=True)
        print("[OCR] 初始化完成")
    return _ocr_engine


def _cv2_to_qimage(bgr: np.ndarray) -> QImage:
    """BGR ndarray -> QImage(RGB888)。把源 ndarray 挂到返回对象上，
    防止其 buffer 在 QPixmap 拷贝完成前被 GC（否则花屏/崩溃）。"""
    rgb = cv2.cvtColor(bgr, cv2.COLOR_BGR2RGB)
    h, w, _ = rgb.shape
    qimg = QImage(rgb.data, w, h, w * 3, QImage.Format_RGB888)
    qimg.ndarray = rgb  # 保活引用
    return qimg


MODE1_CHOICES = ['无', '券满暂停', '自动突破', '仅突破', '爬塔', '御灵', '寮突']
MODE2_CHOICES = ['只打加成', '全打']
ACCEL_CHOICES = ['加速', '非加速']


class DeviceTab(QWidget):
    """单设备控制面板（对应 gra_ui 的一个 TabItem）。"""

    def __init__(self, template_paths, parent=None):
        super().__init__(parent)
        self.template_paths = template_paths
        self.bot = None
        self._last_pix_source = None  # 持有上帧 QImage 源 ndarray，防 GC
        self._build_ui()

    # =====================================
    # UI 构建
    # =====================================
    def _build_ui(self):
        config = load_config()
        root = QHBoxLayout(self)

        # ===== 左列：参数控制 =====
        left = QVBoxLayout()
        form = QFormLayout()

        self.choose = QComboBox()
        form.addRow("设备选择:", self.choose)

        btn_row = QHBoxLayout()
        self.connect_btn = QPushButton("连接")
        self.refresh_btn = QPushButton("刷新设备")
        self.restart_adb_btn = QPushButton("重启 ADB")
        btn_row.addWidget(self.connect_btn)
        btn_row.addWidget(self.refresh_btn)
        btn_row.addWidget(self.restart_adb_btn)
        form.addRow("设备操作:", btn_row)

        self.delay = QLineEdit(str(config["delay_ms"]))
        form.addRow("随机延迟最大值(ms):", self.delay)
        self.click_offset = QLineEdit(str(config["offset_px"]))
        form.addRow("点击偏移(像素):", self.click_offset)

        self.mode1 = QComboBox()
        self.mode1.addItems(MODE1_CHOICES)
        self.mode1.setCurrentText(str(config["mode1"]))
        form.addRow("功能选择:", self.mode1)

        self.max_runtime = QDoubleSpinBox()
        self.max_runtime.setRange(-1.0, 999999.0)
        self.max_runtime.setDecimals(1)
        self.max_runtime.setValue(float(config["max_runtime"]))
        form.addRow("最大运行时长(分,-1无限):", self.max_runtime)

        self.mode2 = QComboBox()
        self.mode2.addItems(MODE2_CHOICES)
        self.mode2.setCurrentText(str(config["mode2"]))
        form.addRow("探索模式:", self.mode2)

        self.accel = QComboBox()
        self.accel.addItems(ACCEL_CHOICES)
        self.accel.setCurrentText("加速" if config.get("accel", True) else "非加速")
        form.addRow("加速:", self.accel)

        self.mumu_path = QLineEdit(config.get("mumu_path", r"D:\Program Files\Netease\MuMu"))
        form.addRow("MuMu 安装路径:", self.mumu_path)

        self.ld_path = QLineEdit(config.get("ld_path", ""))
        self.ld_path.setPlaceholderText("留空自动探测注册表")
        form.addRow("雷电安装路径:", self.ld_path)

        self.hint_label = QLabel(
            "截图/触摸强化自动启用，无需手动勾选：\n"
            "截图按序尝试 MuMu → 雷电 → ADB；触摸按序尝试 MuMu → minitouch → ADB。\n"
            "前者不可用则自动跳过，不报错。MuMu 路径需含 external_renderer_ipc.dll；"
            "雷电路径需含 ldopengl64.dll，留空则读注册表自动探测。"
        )
        self.hint_label.setWordWrap(True)
        self.hint_label.setStyleSheet("color: gray; font-size: 11px;")

        self.shutdown_cb = QCheckBox("达到最大运行时长后自动关机(每次需手动勾选)")
        form.addRow("", self.shutdown_cb)

        ctrl_row = QHBoxLayout()
        self.submit_btn = QPushButton("提交参数")
        self.start_btn = QPushButton("开始")
        self.stop_btn = QPushButton("暂停")
        ctrl_row.addWidget(self.submit_btn)
        ctrl_row.addWidget(self.start_btn)
        ctrl_row.addWidget(self.stop_btn)
        form.addRow("运行:", ctrl_row)

        left.addLayout(form)
        left.addWidget(self.hint_label)

        # ===== 右列：预览 + 状态 =====
        right = QVBoxLayout()

        self.preview_label = QLabel("未连接设备")
        self.preview_label.setAlignment(Qt.AlignCenter)
        self.preview_label.setMinimumSize(480, 270)
        self.preview_label.setStyleSheet("background: #222; color: #aaa; border: 1px solid #555;")
        self.preview_label.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)
        right.addWidget(self.preview_label, stretch=1)

        status_form = QFormLayout()
        self.ot1 = QLineEdit("0"); self.ot1.setReadOnly(True)
        self.ot2 = QLineEdit("0 s"); self.ot2.setReadOnly(True)
        self.ot3 = QLineEdit("未启动"); self.ot3.setReadOnly(True)
        self.ot4 = QLineEdit("无"); self.ot4.setReadOnly(True)
        self.ot5 = QLineEdit("0"); self.ot5.setReadOnly(True)
        status_form.addRow("循环次数:", self.ot1)
        status_form.addRow("运行时间:", self.ot2)
        status_form.addRow("脚本状态:", self.ot3)
        status_form.addRow("当前状态机:", self.ot4)
        status_form.addRow("战斗次数:", self.ot5)
        right.addLayout(status_form)

        root.addLayout(left, 1)
        root.addLayout(right, 2)

        # ===== 信号绑定 =====
        self.refresh_btn.clicked.connect(self.on_refresh)
        self.restart_adb_btn.clicked.connect(self.on_restart_adb)
        self.connect_btn.clicked.connect(self.on_connect)
        self.submit_btn.clicked.connect(self.on_submit)
        self.start_btn.clicked.connect(self.on_start)
        self.stop_btn.clicked.connect(self.on_stop)

    # =====================================
    # 设备操作
    # =====================================
    def _fill_devices(self, devs):
        self.choose.clear()
        if devs:
            self.choose.addItems(devs)

    def on_refresh(self):
        try:
            devs = ADBClient.list_devices()
        except Exception as e:
            self._set_status(f"刷新失败: {e}")
            return
        self._fill_devices(devs)
        self._set_status(f"检测到 {len(devs) if devs else 0} 个设备")

    def on_restart_adb(self):
        if self.bot and self.bot.is_running():
            self._set_status("脚本正在运行，无法重启 ADB")
            return
        try:
            subprocess.run(["adb", "kill-server"], timeout=5, stderr=subprocess.PIPE)
            time.sleep(1)
            devs = ADBClient.list_devices()
            self._fill_devices(devs)
            self._set_status("ADB 服务已重启")
        except Exception as e:
            self._set_status(f"重启 ADB 失败: {e}")

    # =====================================
    # 连接设备（构造控制器链 + MuMu 截图增强 try/回退）
    # =====================================
    def on_connect(self):
        device = self.choose.currentText()
        if not device:
            self._set_status("未选择设备")
            return
        try:
            mumu_path = self.mumu_path.text().strip()
            ld_path = self.ld_path.text().strip()
            adb, capturer, matcher, detector, game_ctrl, bot, status = assemble_device(
                device, mumu_path=mumu_path, ld_path=ld_path, ocr_engine=_get_ocr_engine()
            )
            matcher.load_templates(self.template_paths)
            self.bot = bot

            # 应用当前控件配置
            try:
                delay_ms = float(self.delay.text())
                offset_px = int(self.click_offset.text())
                mode1_val = self.mode1.currentText()
                mode2_val = self.mode2.currentText()
                accel_val = (self.accel.currentText() == '加速')
                bot.update_random_config(
                    (0, delay_ms / 1000), (offset_px, offset_px),
                    mode1_val, mode2_val, accel_val,
                )
            except Exception as e:
                print(f"应用配置失败: {e}")

            self.preview_label.setText("已连接，点击「开始」运行")
            self._set_status(status)
        except Exception as e:
            self._set_status(f"连接失败: {e}")

    # =====================================
    # 提交参数
    # =====================================
    def on_submit(self):
        try:
            delay_ms = float(self.delay.text())
            offset_px = int(self.click_offset.text())
            max_runtime_val = float(self.max_runtime.value())
        except Exception:
            self._set_status("参数错误")
            return
        mode1_val = self.mode1.currentText()
        mode2_val = self.mode2.currentText()
        accel_bool = (self.accel.currentText() == '加速')
        if self.bot:
            self.bot.update_random_config(
                (0, delay_ms / 1000), (offset_px, offset_px),
                mode1_val, mode2_val, accel_bool,
            )
        save_config({
            "delay_ms": delay_ms,
            "offset_px": offset_px,
            "mode1": mode1_val,
            "max_runtime": max_runtime_val,
            "mode2": mode2_val,
            "accel": accel_bool,
            "mumu_path": self.mumu_path.text().strip() or "",
            "ld_path": getattr(self, "ld_path", None) and self.ld_path.text().strip() or "",
        })
        self._set_status("参数已更新")

    # =====================================
    # 开始 / 暂停
    # =====================================
    def on_start(self):
        if not self.bot:
            self._set_status("请先连接设备")
            return
        max_runtime_val = float(self.max_runtime.value())
        shutdown_val = bool(self.shutdown_cb.isChecked())
        self.bot.start(
            max_runtime=60 * max_runtime_val,
            shutdown_on_timeout=shutdown_val,
        )
        # 关机开关仅本次启动生效，启动后立即复位
        self.shutdown_cb.setChecked(False)
        self._set_status("运行中")

    def on_stop(self):
        if not self.bot:
            self._set_status("未连接")
            return
        self.bot.stop()
        self._set_status("已暂停")

    # =====================================
    # 状态刷新（QTimer 1s 调用，刷所有 Tab）
    # =====================================
    def refresh_status(self):
        if not self.bot:
            self.ot1.setText("0")
            self.ot2.setText("0 s")
            self.ot3.setText("未连接")
            self.ot4.setText("无")
            self.ot5.setText("0")
            return
        self.ot1.setText(str(self.bot.get_cycle_times()))
        self.ot2.setText(f"{self.bot.get_operating_time()} s")
        self.ot3.setText(str(self.bot.get_state()))
        self.ot4.setText(str(self.bot.get_states()))
        self.ot5.setText(str(self.bot.get_win_cnts()))

    # =====================================
    # 截图预览刷新（QTimer 200ms 调用，只刷当前 Tab）
    # =====================================
    def refresh_preview(self):
        if not self.bot:
            return
        try:
            detector = self.bot.game_controller.detector
            frame, hits = detector.get_preview()
        except Exception:
            return
        if frame is None:
            return
        try:
            qimg = _cv2_to_qimage(frame)
            pix = QPixmap.fromImage(qimg)

            # 在原始尺寸 pixmap 上画命中框（坐标为全屏坐标，scaled 后框跟随缩放）
            if hits:
                painter = QPainter(pix)
                painter.setPen(QPen(QColor(255, 60, 60), 2))
                font = QFont("Arial", 10)
                font.setBold(True)
                painter.setFont(font)
                for name, cx, cy, w, h in hits:
                    x = int(cx - w / 2)
                    y = int(cy - h / 2)
                    painter.drawRect(x, y, w, h)
                    painter.drawText(x, max(0, y - 3), name)
                painter.end()

            scaled = pix.scaled(
                self.preview_label.size(),
                Qt.KeepAspectRatio,
                Qt.SmoothTransformation,
            )
            self.preview_label.setPixmap(scaled)
            self._last_pix_source = qimg  # 保活，防下一帧前被 GC
        except Exception as e:
            self.preview_label.setText(f"预览渲染失败: {e}")

    def _set_status(self, text):
        self.ot3.setText(str(text))


class MainWindow(QMainWindow):
    """主窗口：4 个设备 Tab + 状态/预览定时器。"""

    def __init__(self, template_paths):
        super().__init__()
        self.template_paths = template_paths
        self.setWindowTitle("yys_auto - 阴阳师自动化 (PySide6)")
        self.resize(1280, 760)

        self.tabs = QTabWidget()
        self.device_tabs = []
        for i in range(1, 5):
            tab = DeviceTab(template_paths)
            self.tabs.addTab(tab, f"设备 {i}")
            self.device_tabs.append(tab)
        self.setCentralWidget(self.tabs)

        # 状态刷新：1s，刷所有 Tab（开销小）
        self.status_timer = QTimer(self)
        self.status_timer.setInterval(1000)
        self.status_timer.timeout.connect(self._tick_status)
        self.status_timer.start()

        # 预览刷新：200ms，只刷当前 Tab
        self.preview_timer = QTimer(self)
        self.preview_timer.setInterval(200)
        self.preview_timer.timeout.connect(self._tick_preview)
        self.preview_timer.start()

        # 启动后自动刷新各 Tab 设备列表
        QTimer.singleShot(100, self._initial_refresh)

    def _initial_refresh(self):
        for tab in self.device_tabs:
            tab.on_refresh()

    def _tick_status(self):
        for tab in self.device_tabs:
            tab.refresh_status()

    def _tick_preview(self):
        idx = self.tabs.currentIndex()
        if 0 <= idx < len(self.device_tabs):
            self.device_tabs[idx].refresh_preview()

    def closeEvent(self, event):
        # 关窗时停止所有运行中的 bot
        for tab in self.device_tabs:
            if tab.bot:
                try:
                    tab.bot.stop()
                except Exception:
                    pass
        event.accept()


def create_ui(template_paths):
    """兼容 gra_ui.create_ui 的工厂入口，返回 MainWindow（调用方 show + exec）。"""
    return MainWindow(template_paths)
