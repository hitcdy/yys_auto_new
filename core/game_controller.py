
# core/game_controller.py
from core.state import GameState
import time
import threading
import random

class GameController:
    """
    游戏主逻辑控制器
    """

    def __init__(self, detector, adb):
        self.detector = detector
        self.adb = adb
        self.state = GameState.CHOOSING
        self.trial = 0
        self.swipe_time = 0
        self.boss_flag = 0
        self.tp_cnt = 0
        self.lose_flag = 0
        self.ensure_flag = 0
        self.last_state = None
        self.last_change_time = time.time()
        self.stuck_threshold = 30
        self.win_cnt = 0
        self.now_lt = 0
        self.fighting_flag = 0

        self._enter_battle_time = 0.0
        self.ACCEL_POS = (1743, 136)
        self.TP_ACCEL_POS = (32, 578)
        self.accel_enabled = True    # 加速模式开关
        self._instance_gone = False  # 战斗期间 instance 是否消失过
        self._miss_cnt = 0          # 连续点空次数
        self._inst_entry = True     # 首次进入 INSTANCE 标志

        # 突破 OCR 驱动变量
        self.CHOOSING_TICKET_ROI = (1408, 22, 1452, 64)
        self.TP_TICKET_ROI = (1717, 22, 1765, 70)
        self._tp_last_tickets = 0       # 进战斗前票数(基准值)
        self._tp_wins = 0               # 当前轮胜利数
        self._had_loss = False          # 当前轮是否有败绩
        self._in_tp_gone = False        # in_tp 是否消失过(类比 _instance_gone)
        self._just_returned = False     # 是否刚从 TP_INBATTLE 返回
        self._tp_empty_clicks = 0       # 连续点空位置计数
        self._last_manual_refresh = 0.0 # 上次手动刷新时间戳
        self._tp_waiting_refresh = False # 是否在等待刷新冷却
        self._tp_test_jumped = False     # 仅突破模式一次性跳转标记
        self._tp_cached_tickets = None   # OCR 缓存，Phase A 更新，Phase C 复用

        self._accel_running = False
        self._accel_thread = None
        self._accel_pos = self.ACCEL_POS

    def set_accel(self, enabled: bool):
        self.accel_enabled = enabled

    def _reset_round(self):
        self.trial = 0
        self.swipe_time = 0
        self.boss_flag = 0
        self._miss_cnt = 0

    # =====================================
    # 🔄 动态循环间隔
    # =====================================
    def get_interval(self) -> float:
        if self.state == GameState.INSTANCE:
            return 0.3
        return 1.0

    # =====================================
    # ⚡ 加速点击线程（独立于截图循环）
    # =====================================
    def _start_accel(self, pos=None):
        if self._accel_running or not self.accel_enabled:
            return
        if pos is not None:
            self._accel_pos = pos
        else:
            self._accel_pos = self.ACCEL_POS
        self._accel_running = True
        self._accel_thread = threading.Thread(target=self._accel_loop, daemon=True)
        self._accel_thread.start()

    def _stop_accel(self):
        self._accel_running = False

    def _accel_loop(self):
        pos = self._accel_pos
        while self._accel_running:
            self.adb.tap(*pos)
            time.sleep(0.2 + random.uniform(-0.03, 0.03))

    # =====================================
    # 🎮 主循环单次执行
    # =====================================
    def run_once(self):
        screen = self.detector.get_screen()

        # mode1 强制进入活动状态（爬塔/御灵/寮突/仅突破），每轮重设以保持在该模式
        if self.adb.mode1 == '爬塔':
            self.state = GameState.ACTIVITY
        if self.adb.mode1 == '御灵':
            self.state = GameState.YULING
        if self.adb.mode1 == '寮突':
            self.state = GameState.LIAOTU
        if self.adb.mode1 == '仅突破' and not self._tp_test_jumped:
            self._tp_test_jumped = True
            self.state = GameState.TP_MENU

        old_state = self.state
        self.state = self.detect_ex_state(screen)
        if self.state != old_state:
            print(f"[状态变更] {old_state} -> {self.state}")

        if self.state != self.last_state:
            print(f"[状态记录] 新状态 {self.state} 开始")
            self.last_state = self.state
            self.last_change_time = time.time()
        else:
            elapsed = time.time() - self.last_change_time
            if elapsed > self.stuck_threshold and self.state != GameState.PAUSE:
                print(f"[卡住检测] 状态 {self.state} 已停留 {elapsed:.1f} 秒，执行自检")
                # 长耗时活动状态（活动/御灵/寮突）不触发自检，仅刷新计时后返回
                if self.state in (GameState.ACTIVITY, GameState.YULING, GameState.LIAOTU):
                    self.last_change_time = time.time()
                    return
                self.self_examine(screen)
                self.last_change_time = time.time()

        match self.state:
            case GameState.PAUSE:
                print("[PAUSE] 暂停状态，跳过操作")
                return
            case GameState.XS:
                self.handle_XS(screen)
            case GameState.MENU:
                self.handle_menu(screen)
            case GameState.CHOOSING:
                self.handle_choosing(screen)
            case GameState.INSTANCE:
                self.handle_instance(screen)
            case GameState.IN_BATTLE:
                self.handle_in_battle(screen)
            case GameState.BOSS:
                self.handle_boss(screen)
            case GameState.REWARD:
                self.handle_reward(screen)
            case GameState.QUITTING:
                self.handle_quitting(screen)
            case GameState.ENSURE_Q:
                self.handle_ensure_q(screen)
            case GameState.FULL:
                self.handle_full(screen)
            case GameState.TP_MENU:
                self.handle_tp_menu(screen)
            case GameState.TP_INBATTLE:
                self.handle_tp_inbattle(screen)
            case GameState.TP_FIN:
                self.handle_tp_fin(screen)
            case GameState.ACTIVITY:
                self.handle_activity(screen)
            case GameState.YULING:
                self.handle_yuling(screen)
            case GameState.LIAOTU:
                self.handle_liaotu(screen)
            case _:
                print(f"无法识别的状态 {self.state}")
                return

    # =====================================
    # 🧠 状态识别
    # =====================================
    def detect_ex_state(self, screen):
        if self.detector.detect_icon(screen, "xs_flag"):
            print(" detect_ex_state: 检测到 xs_flag")
            return GameState.XS
        if self.detector.detect_icon(screen, "intrp_flag"):
            print(" detect_ex_state: 检测到 intrp_flag -> PAUSE")
            return GameState.PAUSE

        # 基础状态自纠正（不覆盖战斗/奖励状态）
        if self.state in (GameState.MENU, GameState.CHOOSING, GameState.INSTANCE):
            if self.detector.detect_icon(screen, "instance"):
                return GameState.INSTANCE
            if self.detector.detect_icon(screen, "entrance"):
                return GameState.CHOOSING
            if self.detector.detect_icon(screen, "menu"):
                return GameState.MENU

        return self.state

    # =====================================
    # 🏠 主菜单逻辑
    # =====================================
    def handle_menu(self, screen):
        print(" handle_menu: 进入 MENU 处理")
        start_btn = self.detector.detect_icon(screen, "menu")
        if start_btn:
            print(f"  handle_menu: 检测到 menu 图标，点击 {start_btn}")
            self.adb.tap(*start_btn)
        if self.detector.detect_icon(screen, "entrance"):
            print("  handle_menu: 检测到 entrance 图标，状态切换为 CHOOSING")
            self.state = GameState.CHOOSING

    def handle_XS(self, screen):
        print(" handle_XS: 进入 XS 处理")
        reject_btn = self.detector.detect_icon(screen, "reject_btn")
        if reject_btn:
            print(f"  handle_XS: 检测到 reject_btn，点击 {reject_btn}")
            self.adb.tap(*reject_btn)
        if not reject_btn:
            if self.detector.detect_icon(screen, "menu"):
                print("  handle_XS: 检测到 menu，切换至 MENU")
                self.state = GameState.MENU
            if self.detector.detect_icon(screen, "entrance"):
                print("  handle_XS: 检测到 entrance，切换至 CHOOSING")
                self.state = GameState.CHOOSING
            if self.detector.detect_icon(screen, "instance"):
                print("  handle_XS: 检测到 instance，切换至 INSTANCE")
                self.state = GameState.INSTANCE
        if self.detector.detect_icon(screen, "ensure"):
            print("  handle_XS: 检测到 ensure")
            if not self.accel_enabled:
                ensure_btn = self.detector.detect_icon(screen, "ensure")
                if ensure_btn:
                    print(f"  handle_XS: 点击 ensure {ensure_btn}")
                    self.adb.tap(*ensure_btn)
        if self.detector.detect_icon(screen, "boss_fight"):
            print("  handle_XS: 检测到 boss_fight，切换至 BOSS")
            self.state = GameState.BOSS
        if self.detector.detect_icon(screen, "reward"):
            print("  handle_XS: 检测到 reward，切换至 REWARD")
            self.state = GameState.REWARD
        if self.detector.detect_icon(screen, "queren"):
            print("  handle_XS: 检测到 queren，切换至 ENSURE_Q")
            self.state = GameState.ENSURE_Q
        if self.detector.detect_icon(screen, "entrance"):
            print("  handle_XS: 检测到 entrance，切换至 CHOOSING")
            self.state = GameState.CHOOSING
        if self.detector.detect_icon(screen, "in_tp"):
            print("  handle_XS: 检测到 in_tp，切换至 TP_MENU")
            self.state = GameState.TP_MENU
        if self.detector.detect_icon(screen, "pata"):
            print("  handle_XS: 检测到 pata，切换至 ACTIVITY")
            self.state = GameState.ACTIVITY

    def handle_choosing(self, screen):
        print(f" handle_choosing: 进入 CHOOSING 处理，mode1={self.adb.mode1}")
        match self.adb.mode1:
            case '无':
                pass
            case '券满暂停':
                if self.detector.detect_icon(screen, "tp_full", threshold=0.9):
                    print("  handle_choosing: 检测到 tp_full (券满)，暂停脚本")
                    self.state = GameState.PAUSE
                    return
            case '自动突破':
                tickets = self.detector.read_ticket_count(screen, self.CHOOSING_TICKET_ROI)
                print(f"  handle_choosing: OCR 票数={tickets}")
                if tickets == 30:
                    print("  handle_choosing: 票数=30，进入突破模式 FULL")
                    self.state = GameState.FULL
                    return
                # 旧逻辑：模板匹配券满图标（保留备用）
                # if self.detector.detect_icon(screen, "tp_full", threshold=0.9):
                #     print("  handle_choosing: 检测到 tp_full (券满)，进入突破模式 FULL")
                #     self.state = GameState.FULL
                #     return

        tansuo_btn = self.detector.detect_icon(screen, "entrance")
        if tansuo_btn:
            print(f"  handle_choosing: 检测到 entrance，点击 {tansuo_btn}")
            self.adb.tap(*tansuo_btn)
        if self.detector.detect_icon(screen, "instance"):
            print("  handle_choosing: 检测到 instance，切换至 INSTANCE")
            self._inst_entry = True
            self.state = GameState.INSTANCE

    # =====================================
    # ⚔ 副本界面逻辑（INSTANCE）
    #
    # trial 语义：累计"未成功完成战斗"的轮数。
    #   - 找到 fight 点击 → trial++ 后切 IN_BATTLE（trial 不归零）
    #   - IN_BATTLE 中点空（instance 立即可见，无 ensure）→ trial 累加带回
    #   - IN_BATTLE 中战斗完成（点过 ensure）→ trial 归零
    #   - trial >= 5 → 滑动
    #
    # 全打模式：boss_fight + fight 合并一次 CLAHE 多阈值匹配。
    # 只打加成模式：boss 先检，再走 bonus 距离逻辑。
    # =====================================
    def handle_instance(self, screen):
        print(
            f" handle_instance: INSTANCE trial={self.trial} swipe={self.swipe_time} boss={self.boss_flag} miss={self._miss_cnt}")

        if self._inst_entry:
            self._inst_entry = False
            print("  handle_instance: 首次进入，等待 2s")
            time.sleep(2)

        if self._miss_cnt >= 10:
            print("  handle_instance: miss>=10 退出副本")
            self._reset_round()
            self.state = GameState.QUITTING
            return

        h, w = screen.shape[:2]
        region = (0, int(h / 3), w, h)

        # ============================================================
        # 第1步（全打）：boss_fight + fight 合并一次 CLAHE
        #   boss 阈值 0.82，fight 阈值 0.7
        # ============================================================
        if self.adb.mode2 != '只打加成':
            result = self.detector.matcher.find_first_multi_threshold(
                screen, [
                    ("boss_fight", 0.82), ("boss_fight2", 0.82),
                    ("fight", 0.78), ("fight2", 0.78),
                ],
                region=region
            )
            if result:
                name, btn = result
                if name.startswith("boss"):
                    print(f"  handle_instance: BOSS {name} {btn}")
                    self.boss_flag = 1
                    self.trial = 0
                    self.swipe_time = 0
                    self.adb.tap(*btn)
    
                    self._enter_battle_time = time.time()
                    self._instance_gone = False
                    self._start_accel()
                    self.state = GameState.BOSS
                    return

                # 普通 fight：切 IN_BATTLE
                print(f"  handle_instance: fight {btn}")
                self.adb.tap(*btn)

                self._enter_battle_time = time.time()
                self._instance_gone = False
                self._start_accel()
                self.state = GameState.IN_BATTLE
                return

        # ============================================================
        # 第1步（分支-只打加成）
        # ============================================================
        else:
            boss_result = self.detector.matcher.find_first_from_image(
                screen, ["boss_fight", "boss_fight2"],
                threshold=0.82, region=region
            )
            if boss_result:
                name, boss_btn = boss_result
                print(f"  handle_instance: BOSS {name} {boss_btn}")
                self.boss_flag = 1
                self.trial = 0
                self.swipe_time = 0
                self.adb.tap(*boss_btn)

                self._enter_battle_time = time.time()
                self._instance_gone = False
                self._start_accel()
                self.state = GameState.BOSS
                return

            bonus_pos = self.detector.detect_icon(screen, "bonus", threshold=0.65, region=region)
            if bonus_pos:
                fight_list = self.detector.detect_icons(screen, "fight", threshold=0.78, region=region)
                if not fight_list:
                    fight_list = self.detector.detect_icons(screen, "fight2", threshold=0.78, region=region)
                if fight_list:
                    xA, yA = bonus_pos
                    fight_btn = min(fight_list, key=lambda p: (p[0] - xA) ** 2 + (p[1] - yA) ** 2)
                else:
                    fight_btn = None
            else:
                fight_btn = None

            if fight_btn:
                print(f"  handle_instance: 加成 fight {fight_btn}")
                self.adb.tap(*fight_btn)

                self._enter_battle_time = time.time()
                self._instance_gone = False
                self._start_accel()
                self.state = GameState.IN_BATTLE
                return

        # ============================================================
        # 第2步：无任何战斗图标 → trial++
        # ============================================================
        self.trial += 1
        print(f"  handle_instance: 无图标 trial={self.trial}")

        # ============================================================
        # 第3步：边缘情况 reward / baoxiang / ensure（trial >= 3 才查）
        # ============================================================
        if self.trial >= 3:
            edge = self.detector.matcher.find_first_from_image(
                screen, ["reward", "baoxiang", "ensure"],
                threshold=0.75, region=region
            )
            if edge:
                name, btn = edge
                print(f"  handle_instance: 边缘 {name} {btn}")
                self.adb.tap(*btn)
                self.trial = 0
                if name == "reward":
                    self.state = GameState.REWARD
                return

        # ============================================================
        # 第4步：trial >= 3 → 滑动
        # ============================================================
        if self.trial >= 3:
            self._do_swipe()

    def _do_swipe(self):
        if self.swipe_time >= 3:
            print("  handle_instance: swipe>=3 退出副本")
            self.state = GameState.QUITTING
            self.swipe_time = 0
            self.trial = 0
            return
        self.swipe_time += 1
        self.trial = 0
        print(f"  handle_instance: 滑动 swipe={self.swipe_time}")
        self.adb.swipe(1441, 808, 450, 813, 300)

    # =====================================
    # ⚔ 普通战斗（IN_BATTLE）
    # fighting 图标在战斗中几乎检测不到，流程靠 ensure/instance 驱动：
    #   - 点空时：进 IN_BATTLE 后 instance 仍可见 → 切回 INSTANCE（trial 累加）
    #   - 正常时：若干轮空转 → ensure 出现 → 点击 → instance 出现 → 切回 INSTANCE（trial 归零）
    # =====================================
    def handle_in_battle(self, screen):
        pfsp_btn = self.detector.detect_icon(screen, "pfsp")
        if pfsp_btn:
            print(f"  handle_in_battle: 检测到 pfsp，点击 {pfsp_btn}")
            self.adb.tap(*pfsp_btn)
            return

        if self.detector.detect_icon(screen, "reward"):
            print("  handle_in_battle: 检测到 reward（boss战），切换至 REWARD")
            self._stop_accel()
            self.state = GameState.REWARD
            return

        if not self.accel_enabled:
            ensure_btn = self.detector.detect_icon(screen, "ensure")
            if ensure_btn:
                print(f"  handle_in_battle: 非加速模式，检测到 ensure，点击 {ensure_btn}")
                self.adb.tap(*ensure_btn)

        if self.detector.detect_icon(screen, "instance"):
            self._stop_accel()
            elapsed = time.time() - self._enter_battle_time
            if self._instance_gone:
                print(f"  handle_in_battle: instance消失过 t={elapsed:.1f}s trial=0")
                self.trial = 0
                self._miss_cnt = 0
                self.win_cnt += 1
            else:
                self._miss_cnt += 1
                print(f"  handle_in_battle: instance一直在 t={elapsed:.1f}s miss={self._miss_cnt}")
                time.sleep(3)
            self.state = GameState.INSTANCE
        else:
            self._instance_gone = True

    # =====================================
    # ⚔ 首领战（BOSS）
    # =====================================
    def handle_boss(self, screen):
        pfsp_btn = self.detector.detect_icon(screen, "pfsp")
        if pfsp_btn:
            print(f"  handle_boss: 检测到 pfsp，点击 {pfsp_btn}")
            self.adb.tap(*pfsp_btn)
            return

        # reward 始终检测（加速和非加速都需要）
        reward_btn = self.detector.detect_icon(screen, "reward")
        if reward_btn:
            print("  handle_boss: 检测到 reward，切换至 REWARD")
            self.boss_flag = 0
            self._stop_accel()
            self.state = GameState.REWARD
            return

        # 加速超过10s自动停止，让后续 ensure 检测能生效
        elapsed = time.time() - self._enter_battle_time
        if self._accel_running and elapsed > 10:
            print(f"  handle_boss: 加速已运行 {elapsed:.1f}s，停止加速")
            self._stop_accel()

        ensure_btn = self.detector.detect_icon(screen, "ensure")
        if ensure_btn:
            print(f"  handle_boss: 检测到 ensure，点击 {ensure_btn}")
            self.adb.tap(*ensure_btn)
            self.boss_flag = 0
            return

        if self.detector.detect_icon(screen, "instance") and self.boss_flag == 1:
            self._stop_accel()
            elapsed = time.time() - self._enter_battle_time
            if self._instance_gone:
                print(f"  handle_boss: instance消失过 t={elapsed:.1f}s boss结束 trial=0")
                self.boss_flag = 0
                self.trial = 0
                self._miss_cnt = 0
                self.win_cnt += 1
                # boss 真打完了，优先检查 reward 再决定去向
                if self.detector.detect_icon(screen, "reward"):
                    print("  handle_boss: boss结束后检测到 reward，切换至 REWARD")
                    self._stop_accel()
                    self.state = GameState.REWARD
                    return
            else:
                self._miss_cnt += 1
                print(f"  handle_boss: instance一直在 t={elapsed:.1f}s miss={self._miss_cnt}")
                time.sleep(3)
            self.state = GameState.INSTANCE
            return

        if self.detector.detect_icon(screen, "menu"):
            print("  handle_boss: 检测到 menu，切换至 MENU")
            self._reset_round()
            self._stop_accel()
            self.state = GameState.MENU
            return
        if self.detector.detect_icon(screen, "entrance"):
            print("  handle_boss: 检测到 entrance，切换至 CHOOSING")
            self._reset_round()
            self._stop_accel()
            self.state = GameState.CHOOSING
            return

        self._instance_gone = True

    def handle_reward(self, screen):
        print(" handle_reward: 进入 REWARD 处理")
        reward_btn = self.detector.detect_icon(screen, "reward", threshold=0.75)
        if reward_btn:
            print(f"  handle_reward: 检测到 reward，点击 {reward_btn}")
            self.adb.tap(*reward_btn)
            time.sleep(0.5)
            self.adb.tap(100, 100)
            return
        if self.detector.detect_icon(screen, "menu"):
            print("  handle_reward: 检测到 menu，切换至 MENU")
            self._reset_round()
            self.state = GameState.MENU
            return
        if self.detector.detect_icon(screen, "entrance"):
            print("  handle_reward: 检测到 entrance，切换至 CHOOSING")
            self._reset_round()
            self.state = GameState.CHOOSING
            return
        print("  handle_reward: 未检测到任何图标，点击 (200,200) 尝试退出")
        self.adb.tap(200, 200)

    def handle_quitting(self, screen):
        print(" handle_quitting: 进入 QUITTING 处理")
        quit_btn = self.detector.detect_icon(screen, "tuichu")
        if quit_btn:
            print(f"  handle_quitting: 检测到 tuichu，点击 {quit_btn}")
            self.adb.tap(*quit_btn)
        if self.detector.detect_icon(screen, "queren"):
            print("  handle_quitting: 检测到 queren，切换至 ENSURE_Q")
            self.state = GameState.ENSURE_Q

    def handle_ensure_q(self, screen):
        print(" handle_ensure_q: 进入 ENSURE_Q 处理")
        ensure_btn = self.detector.detect_icon(screen, "queren")
        if ensure_btn:
            print(f"  handle_ensure_q: 检测到 queren，点击 {ensure_btn}")
            self.adb.tap(*ensure_btn)
            return
        if self.detector.detect_icon(screen, "entrance"):
            print("  handle_ensure_q: 检测到 entrance，切换至 CHOOSING")
            self.state = GameState.CHOOSING

    # =====================================
    # ⚔ 突破逻辑 (OCR驱动)
    # =====================================

    def handle_full(self, screen):
        """券满 → 退出 CHOOSING → 点结界入口 → TP_MENU"""
        # 只清易失状态，保留 tp_cnt/_had_loss/_tp_wins 接续上次进度
        self._tp_empty_clicks = 0
        self._tp_waiting_refresh = False
        self._tp_cached_tickets = None
        self.ensure_flag = 0

        if self.detector.detect_icon(screen, "in_tp"):
            print("  handle_full: 检测到 in_tp，切换至 TP_MENU")
            self.state = GameState.TP_MENU
            return

        jiejie_entrance = self.detector.detect_icon(screen, "jiejie")
        if jiejie_entrance:
            print(f"  handle_full: 检测到 jiejie 入口，点击 {jiejie_entrance}")
            self.adb.tap(*jiejie_entrance)
            return

        tuichu_btn = self.detector.detect_icon(screen, "tuichu")
        if tuichu_btn:
            print(f"  handle_full: 检测到 tuichu，点击 {tuichu_btn}")
            self.adb.tap(*tuichu_btn)

    def _tp_reset_round(self):
        """新一轮对手：重置位置和胜负记录"""
        self.tp_cnt = 0
        self._tp_wins = 0
        self._had_loss = False
        self._tp_empty_clicks = 0
        self._tp_waiting_refresh = False
        self._tp_cached_tickets = None

    def _tp_try_refresh(self, screen):
        """尝试手动刷新，成功返回 True，冷却中返回 False 并进入等待"""
        refresh_btn = self.detector.detect_icon(screen, "shuaxin")
        if refresh_btn:
            print(f"  _tp_try_refresh: 检测到 shuaxin，点击 {refresh_btn}")
            self.adb.tap(*refresh_btn)
            self.ensure_flag = 1
            self._last_manual_refresh = time.time()
            self._tp_reset_round()
            return True
        else:
            print("  _tp_try_refresh: shuaxin 不可用，进入等待刷新冷却")
            self._tp_waiting_refresh = True
            return False

    def handle_tp_menu(self, screen):
        print(f" handle_tp_menu: tp_cnt={self.tp_cnt} wins={self._tp_wins} "
              f"had_loss={self._had_loss} waiting_refresh={self._tp_waiting_refresh} "
              f"just_returned={self._just_returned}")

        positions = [
            (489, 712),
            (972.5, 712),
            (1456, 712),
            (489, 512),
            (972.5, 512),
            (1456, 512),
            (489, 312),
            (972.5, 312),
            (1456, 312)
        ]

        # 进入 tp_menu 立即停加速，防止残留点击
        self._stop_accel()

        # 常驻：奖励弹窗检测
        reward_btn = self.detector.detect_icon(screen, "reward")
        if reward_btn:
            print(f"  handle_tp_menu: 检测到 reward，点击 {reward_btn}")
            self.adb.tap(*reward_btn)
            return

        # ===== Phase A: 刚从战斗返回 → OCR 判断胜负 =====
        if self._just_returned:
            self._just_returned = False
            tickets = self.detector.read_ticket_count(screen, self.TP_TICKET_ROI)
            print(f"  handle_tp_menu: 战后 OCR 票数={tickets}, 战前={self._tp_last_tickets}")

            if tickets < 0:
                print("  handle_tp_menu: OCR 失败，清缓存等待重试")
                self._tp_cached_tickets = None
                return

            if tickets == self._tp_last_tickets - 1:
                print("  handle_tp_menu: 票数-1 → 胜利")
                self._tp_wins += 1
                self.tp_cnt += 1
                self.win_cnt += 1
            elif tickets == self._tp_last_tickets:
                print("  handle_tp_menu: 票数未变 → 失败，跳过此对手")
                self._had_loss = True
                self.tp_cnt += 1
            else:
                print(f"  handle_tp_menu: 票数={tickets} 异常（期望{self._tp_last_tickets}或{self._tp_last_tickets - 1}），重新识别")
                self._tp_cached_tickets = None
                return

            self._tp_cached_tickets = tickets  # 缓存，Phase C 复用

            # 有败绩且遍历完 9 位 → 手动刷新
            if self.tp_cnt >= 9 and self._had_loss:
                print(f"  handle_tp_menu: 9位遍历完，有败绩，尝试手动刷新")
                self._tp_try_refresh(screen)
            return

        # ===== Phase B: 等待手动刷新冷却 =====
        if self._tp_waiting_refresh:
            self._tp_cached_tickets = self.detector.read_ticket_count(screen, self.TP_TICKET_ROI)
            tickets = self._tp_cached_tickets
            print(f"  handle_tp_menu: 等待刷新冷却，票数={tickets}")
            if tickets == 0:
                print("  handle_tp_menu: 票数=0，退出突破")
                self.state = GameState.TP_FIN
                return
            # 每帧检测 shuaxin 是否可用
            self._tp_try_refresh(screen)
            return

        # ===== Phase C: 正常对手选择 =====
        # 复用 Phase A 缓存的票数，缓存无效时重新 OCR
        if self._tp_cached_tickets is None or self._tp_cached_tickets < 0:
            self._tp_cached_tickets = self.detector.read_ticket_count(screen, self.TP_TICKET_ROI)
        tickets = self._tp_cached_tickets

        if tickets == 0:
            print("  handle_tp_menu: 票数=0，退出突破")
            self.state = GameState.TP_FIN
            return

        # 处理弹窗
        if self.ensure_flag == 1:
            print("  handle_tp_menu: ensure_flag=1，等待确认按钮 ensure_s")
            ensure = self.detector.detect_icon(screen, "ensure_s")
            if ensure:
                print(f"  handle_tp_menu: 检测到 ensure_s，点击 {ensure}")
                self.adb.tap(*ensure)
                self.ensure_flag = 0
            return

        ensure_btn = self.detector.detect_icon(screen, "ensure")
        if ensure_btn:
            print(f"  handle_tp_menu: 检测到 ensure，点击 {ensure_btn}")
            self.adb.tap(*ensure_btn)
            return

        ensure_s_btn = self.detector.detect_icon(screen, "ensure_s")
        if ensure_s_btn:
            print(f"  handle_tp_menu: 检测到 ensure_s，点击 {ensure_s_btn}")
            self.adb.tap(*ensure_s_btn)
            return

        # 有败绩且遍历完 9 位 → 手动刷新
        if self.tp_cnt >= 9 and self._had_loss:
            print("  handle_tp_menu: tp_cnt>=9 有败绩，尝试手动刷新")
            self._tp_try_refresh(screen)
            return

        # 选对手
        if not self.detector.detect_icon(screen, "in_tp"):
            return  # 不在主界面，等待

        # 已点击过位置，检查 fight_tp 是否出现
        if self._tp_empty_clicks > 0:
            self._tp_empty_clicks = 0
            fight_btn = self.detector.detect_icon(screen, "fight_tp")
            if fight_btn:
                print(f"  handle_tp_menu: 检测到 fight_tp，点击 {fight_btn}")
                self.adb.tap(*fight_btn)
                self._tp_last_tickets = tickets
                self._in_tp_gone = False
                self._enter_battle_time = time.time()
                self._start_accel(pos=self.TP_ACCEL_POS)
                self.state = GameState.TP_INBATTLE
            else:
                print(f"  handle_tp_menu: 位置 {self.tp_cnt%9+1} 为空，跳过")
                self.tp_cnt += 1
            return

        # 点击当前对手位置
        x, y = positions[self.tp_cnt % 9]
        print(f"  handle_tp_menu: 点击第 {self.tp_cnt%9+1} 个对手位置 ({x}, {y})")
        self.adb.tap(x, y)
        self._tp_empty_clicks = 1  # 标记：下一帧检查 fight_tp
        return

    def handle_tp_inbattle(self, screen):
        """突破战斗：_in_tp_gone 模式判断战斗起止，加速独立线程"""
        # 确保加速在运行（内部有运行中判断）
        self._start_accel(pos=self.TP_ACCEL_POS)

        in_tp_visible = self.detector.detect_icon(screen, "in_tp") is not None

        elapsed = time.time() - self._enter_battle_time

        if not in_tp_visible:
            self._in_tp_gone = True  # in_tp 消失 → 确认已进入战斗

        if in_tp_visible and self._in_tp_gone:
            # in_tp 消失过又出现 → 战斗结束
            print(f"  handle_tp_inbattle: 检测到 in_tp 重现 t={elapsed:.1f}s，战斗结束")
            self._stop_accel()
            self._just_returned = True
            self._in_tp_gone = False
            self.state = GameState.TP_MENU
            return

        # 超时保护：8秒 in_tp 从未消失 → 可能未进入战斗
        if elapsed > 8 and not self._in_tp_gone:
            print(f"  handle_tp_inbattle: 超时 t={elapsed:.1f}s in_tp 从未消失，返回菜单")
            self._stop_accel()
            self.state = GameState.TP_MENU
            return

        # 非加速模式：靠 ensure 判断战斗结束
        if not self.accel_enabled:
            ensure_btn = self.detector.detect_icon(screen, "ensure")
            if ensure_btn:
                print(f"  handle_tp_inbattle: 非加速模式，检测到 ensure，点击 {ensure_btn}")
                self.adb.tap(*ensure_btn)

        if self.detector.detect_icon(screen, "zaizhan"):
            print("  handle_tp_inbattle: 检测到 zaizhan，点击关闭失败界面")
            self.adb.tap(100, 1000)

    def handle_tp_fin(self, screen):
        print(" handle_tp_fin: 进入 TP_FIN 处理")
        ensure = self.detector.detect_icon(screen, "ensure_s")
        if ensure:
            print(f"  handle_tp_fin: 检测到 ensure_s，点击 {ensure}")
            self.adb.tap(*ensure)
            return
        quit_btn = self.detector.detect_icon(screen, "cross")
        if quit_btn:
            print(f"  handle_tp_fin: 检测到 cross，点击 {quit_btn}")
            self.adb.tap(*quit_btn)
        if self.detector.detect_icon(screen, "menu"):
            print("  handle_tp_fin: 检测到 menu，切换至 MENU")
            self.state = GameState.MENU

    # 自检
    def self_examine(self, screen):
        print(" self_examine: 执行自检，尝试识别当前界面")
        if self.detector.detect_icon(screen, "menu"):
            print("  self_examine: 检测到 menu，设为 MENU")
            self.state = GameState.MENU
        if self.detector.detect_icon(screen, "entrance"):
            print("  self_examine: 检测到 entrance，设为 CHOOSING")
            self.state = GameState.CHOOSING
        if self.detector.detect_icon(screen, "instance"):
            print("  self_examine: 检测到 instance，设为 INSTANCE")
            self.state = GameState.INSTANCE
        if self.detector.detect_icon(screen, "ensure"):
            print("  self_examine: 检测到 ensure")
            if not self.accel_enabled:
                ensure_btn = self.detector.detect_icon(screen, "ensure")
                if ensure_btn:
                    print(f"  self_examine: 点击 ensure {ensure_btn}")
                    self.adb.tap(*ensure_btn)
        if self.detector.detect_icon(screen, "boss_fight") or self.detector.detect_icon(screen, "boss_fight2"):
            print("  self_examine: 检测到 boss_fight，设为 BOSS")
            self.state = GameState.BOSS
        if self.detector.detect_icon(screen, "reward"):
            print("  self_examine: 检测到 reward，设为 REWARD")
            self.state = GameState.REWARD
        if self.detector.detect_icon(screen, "queren"):
            print("  self_examine: 检测到 queren，设为 ENSURE_Q")
            self.state = GameState.ENSURE_Q
        if self.detector.detect_icon(screen, "in_tp"):
            print("  self_examine: 检测到 in_tp")
            if self.state == GameState.TP_INBATTLE:
                print("  self_examine: 从 TP_INBATTLE 返回，停止加速，设置 _just_returned")
                self._stop_accel()
                self._just_returned = True
                self._in_tp_gone = False
            self.state = GameState.TP_MENU
        if self.detector.detect_icon(screen, "pata"):
            print("  self_examine: 检测到 pata，设为 ACTIVITY")
            self.state = GameState.ACTIVITY

    # =====================================
    # 🎯 活动模式（爬塔 / 御灵 / 寮突）
    # =====================================
    def handle_activity(self, screen):
        print(" handle_activity: 进入 ACTIVITY 处理")
        pata_btn = self.detector.detect_icon(screen, "pata")
        if pata_btn:
            print(f"  handle_activity: 检测到 pata，点击 {pata_btn}")
            self.adb.tap(*pata_btn)
            return

        ensure_btn = self.detector.detect_icon(screen, "ensure")
        if ensure_btn:
            print(f"  handle_in_battle: 检测到 ensure，点击 {ensure_btn}")
            self.adb.tap(*ensure_btn)
            return

    def handle_yuling(self, screen):
        print(" handle_activity: 进入 YULING 处理")
        yuling_btn = self.detector.detect_icon(screen, "yuling")
        if yuling_btn:
            print(f"  handle_activity: 检测到 yuling，点击 {yuling_btn}")
            self.adb.tap(*yuling_btn)
            return

        ensure_btn = self.detector.detect_icon(screen, "ensure")
        if ensure_btn:
            print(f"  handle_in_battle: 检测到 ensure，点击 {ensure_btn}")
            self.adb.tap(*ensure_btn)
            return

    def handle_liaotu(self, screen):
        print(" handle_activity: 进入 LIAOTU 处理")
        positions2 = [
            (882, 311),   # 1
            (1373, 311),  # 2
            (882, 501),   # 3
            (1373, 501),  # 4
            (882, 690),   # 5
            (1373, 690),  # 6
            (882, 880),   # 7
            (1373, 880)   # 8
        ]
        ensure_btn = self.detector.detect_icon(screen, "ensure")
        if ensure_btn:
            print(f"  handle_tp_inbattle: 检测到 ensure，点击 {ensure_btn}")
            self.adb.tap(*ensure_btn)
            self.fighting_flag = 0
            return
        if self.detector.detect_icon(screen, "zaizhan"):
            print("  handle_tp_inbattle: 检测到 zaizhan，设置 lose_flag=1，点击 (100,1000)")
            self.now_lt += 1
            if self.now_lt >= 8:
                self.state = GameState.PAUSE
                print("战败次数过多，脚本暂停")
                return
            self.adb.tap(100, 1000)
            self.fighting_flag = 0
            return
        fight_btn = self.detector.detect_icon(screen, "jingong")
        if fight_btn:
            print(f"  handle_tp_liaotu: 检测到 fighting，点击 {fight_btn}")
            self.adb.tap(*fight_btn)
            self.fighting_flag = 1
            return
        if self.fighting_flag == 0:
            x, y = positions2[self.now_lt]
            win_flag = self.detector.detect_icons(screen, "win_lt")

            # 检查是否完成
            half_w, half_h = 250, 90
            left, right = x - half_w, x + half_w
            top, bottom = y - half_h, y + half_h
            has_win_in_cell = any(
                left <= px <= right and top <= py <= bottom
                for px, py in win_flag
            )
            if has_win_in_cell:
                print("寮突完成，暂停脚本")
                self.state = GameState.PAUSE
                return

            print(f"  handle_tp_menu: 点击第 {self.now_lt+1} 个对手位置 ({x}, {y})")
            self.adb.tap(x, y)
            return

    def is_device_connected(self):
        return self.adb.device is not None
