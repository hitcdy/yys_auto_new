import os
import sys
from PySide6.QtWidgets import QApplication
from ui.qt_ui import MainWindow
from paths import TEMPLATE_DIR

def main():
    # 模板路径字典（基于 __file__ 绝对化，不再依赖启动时的当前工作目录）
    _t = lambda name: os.path.join(TEMPLATE_DIR, name)
    template_paths = {
        "menu": _t("ershibazhang.png"),
        "entrance": _t("tansuo.png"),
        "instance": _t("fuben.png"),
        "bonus": _t("jiacheng.png"),
        "fight": _t("zhandou.png"),
        "fighting": _t("zhandouzhong.png"),
        "ensure": _t("win.png"),
        "boss_fight": _t("shoulingzhandou.png"),
        "reward": _t("xiaozhiren.png"),
        "tuichu": _t("tuichu.png"),
        "queren": _t("querentuichu.png"),
        "xs_flag": _t("xuanshang.png"),
        "reject_btn": _t("jujuexs.png"),
        "intrp_flag": _t("dinghao.png"),
        "tp_full": _t("tp_full.png"),
        "cross": _t("cross_tp.png"),
        "fight_tp": _t("fight_tp.png"),
        "jiejie": _t("jiejie.png"),
        "quit_b": _t("quit_battle.png"),
        "shuaxin": _t("shuaxin.png"),
        "zaizhan": _t("re_fight.png"),
        "ensure_s": _t("ensure_s.png"),
        "in_tp": _t("in_tp.png"),
        "fighting_a": _t("another.jpeg"),
        "fight2": _t("zhandou2.png"),
        "boss_fight2": _t("shoulingzhandou2.png"),
        "baoxiang": _t("baoxiang.png"),
        "pfsp": _t("pfsp.png"),
        "pata": _t("pata.png"),
        "yuling": _t("yuling.png"),
        "jingong": _t("jingong.png"),
        "win_lt": _t("win_lt.png")
    }
    app = QApplication(sys.argv)
    win = MainWindow(template_paths)
    win.show()
    sys.exit(app.exec())

if __name__ == "__main__":
    main()
