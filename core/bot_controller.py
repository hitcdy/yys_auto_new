# core/bot_controller.py

import time
import threading
from core.state import GameState

class BotController:
    """
    机器人运行调度器
    负责：
    - 循环调度 GameController
    - 统计运行信息
    - 对接 UI
    """

    def __init__(self, game_controller, interval: float = 1.0):
        self.game_controller = game_controller
        self.interval = interval
        self._max_runtime = -1.0   # 新增

        # 线程控制
        self._running = False
        self._thread = None

        # 状态信息
        self._cycle_times = 0
        self._start_time = None
        self._state = "未启动"

        # 线程锁（防止UI和线程同时访问数据）
        self._lock = threading.Lock()

    # =====================================
    # ▶ 启动
    # =====================================
    '''def start(self):
        if self._running:
            return

        if not self.game_controller.is_device_connected():
            self._state = "未连接设备"
            return

        print("Bot started")
        self.game_controller.state = GameState.CHOOSING
        self._running = True
        self._state = "运行中"
        self._cycle_times = 0
        self._start_time = time.time()

        self._thread = threading.Thread(
            target=self._run_loop,
            daemon=True
        )
        self._thread.start()'''
    def start(self, max_runtime: float = -1.0):
        if self._running:
            return
        if not self.game_controller.is_device_connected():
            self._state = "未连接设备"
            return

        self._max_runtime = max_runtime   # 保存限制
        print("Bot started")
        self.game_controller.state = GameState.CHOOSING
        self._running = True
        self._state = "运行中"
        self._cycle_times = 0
        self._start_time = time.time()

        self._thread = threading.Thread(
            target=self._run_loop,
            daemon=True
        )
        self._thread.start()
    # =====================================
    # ⏹ 停止
    # =====================================
    def stop(self):
        if not self._running:
            return

        print("Bot stopped")
        self._running = False
        self._state = "已暂停"

    # =====================================
    # 🔁 主循环
    # =====================================
    '''def _run_loop(self):
        while self._running:
            try:
                self.game_controller.run_once()

                if self.game_controller.state == GameState.PAUSE:
                    print("检测到暂停请求，停止脚本")
                    with self._lock:
                        self._running = False
                        self._state = "暂停图标触发"
                    # 清除请求，以便下次启动时正常
                    break

                with self._lock:
                    self._cycle_times += 1

            except Exception as e:
                print("Error in run loop:", e)
                self._state = f"异常: {e}"
                self._running = False
                break

            time.sleep(self.interval)'''
    def _run_loop(self):
        while self._running:
            # 检查是否超过最大运行时长
            if self._max_runtime >= 0:
                elapsed = time.time() - self._start_time # type: ignore
                if elapsed > self._max_runtime:
                    print("达到最大运行时长，自动暂停")
                    with self._lock:
                        self._running = False
                        self._state = "达到运行时长限制"
                    break

            try:
                self.game_controller.run_once()

                if self.game_controller.state == GameState.PAUSE:
                    print("检测到暂停请求，停止脚本")
                    with self._lock:
                        self._running = False
                        self._state = "暂停图标触发"
                    break

                with self._lock:
                    self._cycle_times += 1

            except Exception as e:
                print("Error in run loop:", e)
                self._state = f"异常: {e}"
                self._running = False
                break

            time.sleep(self.interval)
    # =====================================
    # 📊 状态接口（给UI调用）
    # =====================================

    def get_cycle_times(self):
        with self._lock:
            return self._cycle_times
        
    def get_win_cnts(self):
        with self._lock:
            return self.game_controller.win_cnt
        
    def get_operating_time(self):
        if not self._start_time:
            return 0

        if not self._running:
            return round(time.time() - self._start_time, 1)

        return round(time.time() - self._start_time, 1)

    def get_state(self):
        return self._state
    
    def get_states(self):
        return self.game_controller.state

    # =====================================
    # 📱 设备相关
    # =====================================

    def get_devices(self):
        return self.game_controller.adb.list_devices()

    def connect_device(self, device):
        self.game_controller.adb.connect(device)
        self._state = f"已连接: {device}"

    # =====================================
    # 🎲 随机参数更新
    # =====================================

    def update_random_config(self, delay_range, offset_range, mode1, mode2):
        self.game_controller.adb.configure_random(
            delay_range=delay_range,
            offset_range=offset_range,
            mode1 = mode1,
            mode2 = mode2
        )
        print("随机参数已更新:", delay_range, offset_range,mode1, mode2)

    # =====================================
    # 🔌 设备状态检查
    # =====================================

    def is_running(self):
        return self._running