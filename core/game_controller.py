
# core/game_controller.py
from core.state import GameState
import time

class GameController:
    """
    游戏主逻辑控制器
    - 不负责截图
    - 不负责识别算法
    - 只负责决策
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
        self.tp_round = 0
        self.ensure_flag = 0
        self.last_state = None          # 上一次的状态
        self.last_change_time = time.time()  # 上次状态变更的时间
        self.stuck_threshold = 30        # 卡住阈值（秒），可根据需要调整或设为配置
        self.win_cnt = 0
        self.now_lt = 0
        self.fighting_flag = 0


    # =====================================
    # 🎮 主循环单次执行
    # =====================================
    def run_once(self):
        # ✅ 全系统唯一截图
        screen = self.detector.get_screen()
        if self.adb.mode1 == '爬塔':
            self.state = GameState.ACTIVITY
        if self.adb.mode1 == '御灵':
            self.state = GameState.YULING
        if self.adb.mode1 == '寮突':
            self.state = GameState.LIAOTU
        # ✅ 判断状态
        old_state = self.state
        self.state = self.detect_ex_state(screen)
        if self.state != old_state:
            print(f"[状态变更] {old_state} -> {self.state}")

        if self.state != self.last_state:
            print(f"[状态记录] 新状态 {self.state} 开始")
            self.last_state = self.state
            self.last_change_time = time.time()
        else:
            # 状态未变，检查是否卡住
            elapsed = time.time() - self.last_change_time
            if elapsed > self.stuck_threshold and self.state != GameState.PAUSE:
                print(f"[卡住检测] 状态 {self.state} 已停留 {elapsed:.1f} 秒，执行自检")
                if self.state == GameState.ACTIVITY or self.state == GameState.YULING or self.state == GameState.LIAOTU:
                    self.last_change_time = time.time()
                    return
                self.self_examine(screen)
                self.last_change_time = time.time()

        # ✅ 根据状态执行行为
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
        # 没有检测到特殊状态，返回当前状态
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
            # 检测其他图标并跳转状态
            if self.detector.detect_icon(screen, "menu"):
                print("  handle_XS: 检测到 menu，切换至 MENU")
                self.state = GameState.MENU
            if self.detector.detect_icon(screen, "entrance"):
                print("  handle_XS: 检测到 entrance，切换至 CHOOSING")
                self.state = GameState.CHOOSING
            if self.detector.detect_icon(screen, "instance"):
                print("  handle_XS: 检测到 instance，切换至 INSTANCE")
                self.state = GameState.INSTANCE
        if self.detector.detect_icon(screen, "fighting") or self.detector.detect_icon(screen, "ensure"):
            print("  self_examine: 检测到 fighting 或 ensure")
            if self.tp_round == 0 and self.tp_cnt == 0:
                if self.boss_flag == 0:
                    print("  self_examine: 设为 IN_BATTLE")
                    self.state = GameState.IN_BATTLE
                else :
                    print("  self_examine: 设为 BOSS")
                    self.state = GameState.BOSS
            else:
                print("  self_examine: 设为 TP_INBATTLE")
                self.state = GameState.TP_INBATTLE
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
                if self.detector.detect_icon(screen, "tp_full", threshold=0.9):
                    print("  handle_choosing: 检测到 tp_full (券满)，进入突破模式 FULL")
                    self.state = GameState.FULL
                    return
            case _:
                pass

        tansuo_btn = self.detector.detect_icon(screen, "entrance")
        if tansuo_btn:
            print(f"  handle_choosing: 检测到 entrance，点击 {tansuo_btn}")
            self.adb.tap(*tansuo_btn)
        if self.detector.detect_icon(screen, "instance"):
            print("  handle_choosing: 检测到 instance，切换至 INSTANCE")
            self.state = GameState.INSTANCE

    # =====================================
    # ⚔ 战斗中逻辑
    # =====================================
    def handle_instance(self, screen):
        print(f" handle_instance: 进入 INSTANCE 处理，trial={self.trial}, swipe_time={self.swipe_time}, boss_flag={self.boss_flag}")

        baoxiang_btn = self.detector.detect_icon(screen, "baoxiang")
        if baoxiang_btn:
            print(f"  handle_boss: 检测到 baoxiang，点击 {baoxiang_btn}")
            self.adb.tap(*baoxiang_btn)
            return

        ensure_btn = self.detector.detect_icon(screen, "ensure")
        if ensure_btn:
            print(f"  handle_boss: 检测到 ensure，点击 {ensure_btn}")
            self.adb.tap(*ensure_btn)
            return

        # 首领出现优先检测
        boss_btn = self.detector.detect_icon(screen, "boss_fight")
        if not boss_btn:
            boss_btn = self.detector.detect_icon(screen, "boss_fight2")
        if boss_btn:
            print(f"  handle_instance: 检测到 boss_fight，设置 boss_flag=1，点击 {boss_btn}")
            self.boss_flag = 1
            self.trial = 0
            self.swipe_time = 0
            self.adb.tap(*boss_btn)
            self.state = GameState.BOSS
            return

        # 检测到自动图标说明成功进入战斗
        if self.detector.detect_icon(screen, "fighting", threshold=0.5) or self.detector.detect_icon(screen, "fighting_a"):
            print("  handle_instance: 检测到 fighting 图标")
            if self.boss_flag == 1:
                print("  handle_instance: boss_flag=1，切换至 BOSS")
                self.state = GameState.BOSS
            else:
                print("  handle_instance: 切换至 IN_BATTLE")
                self.state = GameState.IN_BATTLE
            return

        # 无首领检测普通加成战斗
        if self.adb.mode2 == '只打加成':
            print("  handle_instance: mode2=只打加成，寻找离加成最近的战斗按钮")
            fight_btn = self.detector.find_nearest_B_to_first_A(screen, "bonus", "fight")
        else:
            print("  handle_instance: mode2=全打，直接检测 fight 图标")
            fight_btn = self.detector.detect_icon(screen, "fight")
            if not fight_btn:
                fight_btn = self.detector.detect_icon(screen, "fight2")

        self.trial += 1
        if fight_btn:
            print(f"  handle_instance: 检测到战斗按钮 {fight_btn}，点击，重置 trial")
            self.adb.tap(*fight_btn)
            self.state = GameState.IN_BATTLE
            self.trial = 0

        if not fight_btn:
            print(f"  handle_instance: 未检测到战斗按钮，trial={self.trial}")
            if self.trial >= 5:
                if self.swipe_time >= 3:
                    print(f"  handle_instance: swipe_time={self.swipe_time} >=3，切换至 QUITTING")
                    self.state = GameState.QUITTING
                    self.swipe_time = 0
                    return
                print(f"  handle_instance: 滑动屏幕，swipe_time 增加至 {self.swipe_time+1}")
                self.adb.swipe(1441, 808, 450, 813, 300)
                self.swipe_time += 1
                self.trial = 0

    def handle_in_battle(self, screen):
        print(" handle_in_battle: 进入 IN_BATTLE 处理")
        pfsp_btn = self.detector.detect_icon(screen, "pfsp")
        if pfsp_btn:
            print(f"  handle_in_battle: 检测到 pfsp，点击 {pfsp_btn}")
            self.adb.tap(*pfsp_btn)
            return
        
        ensure_btn = self.detector.detect_icon(screen, "ensure")
        if ensure_btn:
            print(f"  handle_in_battle: 检测到 ensure，点击 {ensure_btn}")
            self.adb.tap(*ensure_btn)
            self.win_cnt += 1
        if self.detector.detect_icon(screen, "instance"):
            print("  handle_in_battle: 检测到 instance，切换至 INSTANCE")
            self.state = GameState.INSTANCE

    def handle_boss(self, screen):
        print(" handle_boss: 进入 BOSS 处理")

        pfsp_btn = self.detector.detect_icon(screen, "pfsp")
        if pfsp_btn:
            print(f"  handle_in_battle: 检测到 pfsp，点击 {pfsp_btn}")
            self.adb.tap(*pfsp_btn)
            return
        
        if self.detector.detect_icon(screen, "instance") and self.boss_flag == 1:
            print("  handle_in_battle: 检测到 instance，切换至 INSTANCE")
            self.state = GameState.INSTANCE
        ensure_btn = self.detector.detect_icon(screen, "ensure")
        if ensure_btn:
            print(f"  handle_boss: 检测到 ensure，点击 {ensure_btn}")
            self.adb.tap(*ensure_btn)
            self.boss_flag = 0
            return
        reward_btn = self.detector.detect_icon(screen, "reward")
        if reward_btn:
            print("  handle_boss: 检测到 reward，切换至 REWARD")
            self.state = GameState.REWARD
            return
        if self.detector.detect_icon(screen, "menu"):
            print("  handle_boss: 检测到 menu，切换至 MENU")
            self.state = GameState.MENU
            return
        if self.detector.detect_icon(screen, "entrance"):
            print("  handle_boss: 检测到 entrance，切换至 CHOOSING")
            self.state = GameState.CHOOSING

    def handle_reward(self, screen):
        print(" handle_reward: 进入 REWARD 处理")
        reward_btn = self.detector.detect_icon(screen, "reward")
        if reward_btn:
            print(f"  handle_reward: 检测到 reward，点击 {reward_btn}")
            self.adb.tap(*reward_btn)
            time.sleep(0.5)
            print("  handle_reward: 点击 (100,100) 关闭弹窗")
            self.adb.tap(100, 100)
            return
        if self.detector.detect_icon(screen, "menu"):
            print("  handle_reward: 检测到 menu，切换至 MENU")
            self.state = GameState.MENU
            return
        if self.detector.detect_icon(screen, "entrance"):
            print("  handle_reward: 检测到 entrance，切换至 CHOOSING")
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
    # ⚔ 突破逻辑
    # =====================================
    def handle_full(self, screen):
        print(f" handle_full: 进入 FULL 处理，tp_round={self.tp_round}, tp_cnt={self.tp_cnt}")
        self.tp_cnt = 0
        self.ensure_flag = 0
        self.tp_cnt = 0
        self.lose_flag = 0
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
            print(f"  handle_full: 检测到 cross，点击 {tuichu_btn}")
            self.adb.tap(*tuichu_btn)
            return

    def handle_tp_menu(self, screen):
        print(f" handle_tp_menu: 进入 TP_MENU 处理，ensure_flag={self.ensure_flag}, tp_cnt={self.tp_cnt}, tp_round={self.tp_round}, lose_flag={self.lose_flag}")

        positions = [
            (489, 712),    # 1
            (972.5, 712),  # 2
            (1456, 712),   # 3
            (489, 512),    # 4
            (972.5, 512),  # 5
            (1456, 512),   # 6
            (489, 312),    # 7
            (972.5, 312),  # 8
            (1456, 312)    # 9
        ]

        if self.ensure_flag == 1:
            print("  handle_tp_menu: ensure_flag=1，等待确认按钮 ensure_s")
            ensure = self.detector.detect_icon(screen, "ensure_s")
            if ensure:
                print(f"  handle_tp_menu: 检测到 ensure_s，点击 {ensure}，清除 ensure_flag")
                self.adb.tap(*ensure)
                self.ensure_flag = 0
            return

        if self.detector.detect_icon(screen, "fighting") or self.detector.detect_icon(screen, "fighting_a"):
            print("  handle_tp_menu: 检测到 fighting，进入 TP_INBATTLE，tp_cnt 增加")
            self.state = GameState.TP_INBATTLE
            self.tp_cnt += 1
            return

        ensure_btn = self.detector.detect_icon(screen, "ensure")
        if ensure_btn:
            print(f"  handle_tp_menu: 检测到 ensure，点击 {ensure_btn}")
            self.adb.tap(*ensure_btn)
            return

        if self.tp_cnt >= 9:
            print(f"  handle_tp_menu: tp_cnt={self.tp_cnt} >=9，准备刷新")
            refresh_btn = self.detector.detect_icon(screen, "shuaxin")
            if refresh_btn:
                if self.lose_flag:
                    print(f"  handle_tp_menu: 检测到 shuaxin，点击，设置 ensure_flag")
                    self.adb.tap(*refresh_btn)
                    self.ensure_flag = 1
                self.tp_round += 1
                self.tp_cnt = 0
                self.lose_flag = 0
                print(f"  handle_tp_menu: 刷新后 tp_round={self.tp_round}")
                if self.tp_round >= 3:
                    print("  handle_tp_menu: tp_round >=3，切换至 TP_FIN")
                    self.state = GameState.TP_FIN
                    self.tp_round = 0
                return



        fight_btn = self.detector.detect_icon(screen, "fight_tp")
        if fight_btn:
            print("  handle_tp_menu: 检测到 fight_tp，点击")
            self.adb.tap(*fight_btn)
            return

        if self.tp_cnt <= 8 and self.detector.detect_icon(screen, "in_tp"):
            x, y = positions[self.tp_cnt]
            print(f"  handle_tp_menu: 点击第 {self.tp_cnt+1} 个对手位置 ({x}, {y})")
            self.adb.tap(x, y)
            return

    def handle_tp_inbattle(self, screen):
        print(" handle_tp_inbattle: 进入 TP_INBATTLE 处理")
        ensure_btn = self.detector.detect_icon(screen, "ensure")
        if ensure_btn:
            print(f"  handle_tp_inbattle: 检测到 ensure，点击 {ensure_btn}")
            self.adb.tap(*ensure_btn)
        if self.detector.detect_icon(screen, "in_tp"):
            print("  handle_tp_inbattle: 检测到 in_tp，切换至 TP_MENU")
            self.state = GameState.TP_MENU
        if self.detector.detect_icon(screen, "zaizhan"):
            print("  handle_tp_inbattle: 检测到 zaizhan，设置 lose_flag=1，点击 (100,1000)")
            self.lose_flag = 1
            self.adb.tap(100, 1000)

    def handle_tp_fin(self, screen):
        print(" handle_tp_fin: 进入 TP_FIN 处理")
        ensure = self.detector.detect_icon(screen, "ensure_s")
        if ensure:
            print(f"  handle_tp_menu: 检测到 ensure_s，点击 {ensure}，清除 ensure_flag")
            self.adb.tap(*ensure)
            self.ensure_flag = 0
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
        if self.detector.detect_icon(screen, "fighting") or self.detector.detect_icon(screen, "ensure"):
            print("  self_examine: 检测到 fighting 或 ensure")
            if self.tp_round == 0 and self.tp_cnt == 0:
                if self.boss_flag == 0:
                    print("  self_examine: 设为 IN_BATTLE")
                    self.state = GameState.IN_BATTLE
                else :
                    print("  self_examine: 设为 BOSS")
                    self.state = GameState.BOSS
            else:
                print("  self_examine: 设为 TP_INBATTLE")
                self.state = GameState.TP_INBATTLE
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
            print("  self_examine: 检测到 in_tp，设为 TP_MENU")
            self.state = GameState.TP_MENU
        if self.detector.detect_icon(screen, "pata"):
            print("  self_examine: 检测到 pata，设为 ACTIVITY")
            self.state = GameState.ACTIVITY

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
