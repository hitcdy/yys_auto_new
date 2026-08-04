import sys
from PySide6.QtWidgets import QApplication
from ui.qt_ui import MainWindow

def main():
    # 模板路径字典（与原代码完全一致）
    template_paths = {
        "menu": "template/ershibazhang.png",
        "entrance": "template/tansuo.png",
        "instance": "template/fuben.png",
        "bonus": "template/jiacheng.png",
        "fight": "template/zhandou.png",
        "fighting": "template/zhandouzhong.png",
        "ensure": "template/win.png",
        "boss_fight": "template/shoulingzhandou.png",
        "reward": "template/xiaozhiren.png",
        "tuichu": "template/tuichu.png",
        "queren": "template/querentuichu.png",
        "xs_flag": "template/xuanshang.png",
        "reject_btn": "template/jujuexs.png",
        "intrp_flag": "template/dinghao.png",
        "tp_full": "template/tp_full.png",
        "cross": "template/cross_tp.png",
        "fight_tp": "template/fight_tp.png",
        "jiejie": "template/jiejie.png",
        "quit_b": "template/quit_battle.png",
        "shuaxin": "template/shuaxin.png",
        "zaizhan": "template/re_fight.png",
        "ensure_s": "template/ensure_s.png",
        "in_tp": "template/in_tp.png",
        "fighting_a": "template/another.jpeg",
        "fight2": "template/zhandou2.png",
        "boss_fight2": "template/shoulingzhandou2.png",
        "baoxiang": "template/baoxiang.png",
        "pfsp": "template/pfsp.png",
        "pata": "template/pata.png",
        "yuling": "template/yuling.png",
        "jingong": "template/jingong.png",
        "win_lt": "template/win_lt.png"
    }
    app = QApplication(sys.argv)
    win = MainWindow(template_paths)
    win.show()
    sys.exit(app.exec())

if __name__ == "__main__":
    main()
