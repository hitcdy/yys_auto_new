# core/adb_client.py

import subprocess
import random
import time
import threading
from typing import List, Tuple, Optional


class ADBClient:
    """
    统一版 ADBClient
    兼容：
    - UI
    - BotController
    - GameController
    """

    def __init__(self, device_id: Optional[str] = None):
        self.device_id = device_id   # adb -s 使用
        self.device = device_id      # 给 GameController 使用

        # 随机参数
        self.random_delay_range: Tuple[float, float] = (0, 0)
        self.random_offset_range: Tuple[int, int] = (0, 0)
        self.mode1 = '无'
        self.mode2 = '只打加成'
        self._lock = threading.Lock()

    # =====================================
    # 构建 adb 命令
    # =====================================
    def _build_cmd(self, cmd: List[str]) -> List[str]:
        base = ["adb"]
        if self.device_id:
            base += ["-s", self.device_id]
        return base + cmd

    # =====================================
    # 执行命令
    # =====================================
    def _run(self, cmd: List[str], timeout: int = 10) -> str:
        full_cmd = self._build_cmd(cmd)

        with self._lock:
            result = subprocess.run(
                full_cmd,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True,
                timeout=timeout
            )

        if result.returncode != 0:
            raise RuntimeError(result.stderr.strip())

        return result.stdout.strip()

    # =====================================
    # 设备列表
    # =====================================
    @staticmethod
    def list_devices() -> List[str]:
        result = subprocess.run(
            ["adb", "devices"],
            stdout=subprocess.PIPE,
            text=True
        )

        lines = result.stdout.strip().split("\n")[1:]
        devices = []

        for line in lines:
            if not line.strip():
                continue

            parts = line.split("\t")
            if len(parts) == 2 and parts[1] == "device":
                devices.append(parts[0])

        return devices

    # =====================================
    # 连接设备
    # =====================================
    def connect(self, device_id: str):
        """
        切换控制设备
        """
        self.device_id = device_id
        self.device = device_id

    def is_connected(self) -> bool:
        if not self.device_id:
            return False
        return self.device_id in self.list_devices()

    # =====================================
    # 随机配置
    # =====================================
    def configure_random(
        self,
        delay_range: Tuple[float, float],
        offset_range: Tuple[int, int],
        mode1,
        mode2
    ):
        self.random_delay_range = delay_range
        self.random_offset_range = offset_range
        self.mode1 = mode1
        self.mode2 = mode2
    def _random_delay(self):
        if self.random_delay_range == (0, 0):
            return

        delay = random.uniform(
            self.random_delay_range[0],
            self.random_delay_range[1]
        )
        time.sleep(delay)

    def _random_offset(self) -> Tuple[int, int]:
        if self.random_offset_range == (0, 0):
            return 0, 0

        offset = random.randint(
            self.random_offset_range[0],
            self.random_offset_range[1]
        )

        return (
            random.choice([-offset, offset]),
            random.choice([-offset, offset])
        )

    # =====================================
    # 点击
    # =====================================
    def tap(self, x: int, y: int):
        self._random_delay()
        if not self.is_connected():
            raise RuntimeError("设备未连接")

        dx, dy = self._random_offset()
        x += dx
        y += dy

        self._run(["shell", "input", "tap", str(x), str(y)])


    # =====================================
    # 滑动
    # =====================================
    def swipe(self, x1, y1, x2, y2, duration=300):
        self._random_delay()
        if not self.is_connected():
            raise RuntimeError("设备未连接")

        self._run([
            "shell", "input", "swipe",
            str(x1), str(y1),
            str(x2), str(y2),
            str(duration)
        ])



    # =====================================
    # 截图（raw 格式，超时自动重试）
    # =====================================
    def screencap(self, retries=3) -> bytes:
        if not self.is_connected():
            raise RuntimeError("设备未连接")

        for attempt in range(retries):
            try:
                result = subprocess.run(
                    self._build_cmd(["exec-out", "screencap"]),
                    stdout=subprocess.PIPE,
                    stderr=subprocess.PIPE,
                    timeout=15
                )
                if result.returncode != 0:
                    raise RuntimeError("ADB screencap failed")
                return result.stdout
            except subprocess.TimeoutExpired:
                print(f"  screencap 超时 (第{attempt+1}次)，重试...")
            except Exception as e:
                print(f"  screencap 异常: {e}，重试...")

        raise RuntimeError("ADB screencap 多次重试后仍失败")