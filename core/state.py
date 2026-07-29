from enum import Enum


class GameState(Enum):
    #正常进程
    MENU      = 0   #探索主页面
    CHOOSING  = 1   #点击28章后
    INSTANCE  = 2   #进入28章
    IN_BATTLE = 3   #进入战斗
    BOSS      = 4   #首领出现
    REWARD    = 5   #小纸人
    QUITTING  = 6   #无加成无首领
    ENSURE_Q  = 7   #确认退出
    #打断进程
    XS        = 8   #悬赏
    PAUSE     = 9   #暂停脚本

    #结界突破用
    FULL      = 10
    TP_MENU   = 11
    TP_INBATTLE=12
    TP_FIN    = 13
    #活动
    ACTIVITY  = 14
    YULING    = 15
    LIAOTU    = 16
