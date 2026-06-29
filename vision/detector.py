# core/detector.py

from typing import Optional, Tuple, List


class Detector:
    """
    统一视觉检测入口
    - 统一截图
    - 统一模板匹配
    - 统一 OCR
    """

    def __init__(self, matcher, ocr_engine, capturer):
        self.matcher = matcher
        self.ocr = ocr_engine
        self.capturer = capturer

    # =====================================
    # 📸 截图入口（全系统唯一截图来源）
    # =====================================
    def get_screen(self):
        """
        获取当前屏幕图像（BGR）
        """
        return self.capturer.capture()

    # =====================================
    # 🎯 单目标检测
    # =====================================
    def detect_icon(
        self,
        screen,
        name: str,
        threshold: float = 0.8
    ) -> Optional[Tuple[int, int]]:
        """
        在指定 screen 上检测模板

        :param screen: 传入当前截图
        :param name: 模板名称
        :param threshold: 可选阈值
        :return: (x, y) 或 None
        """
        return self.matcher.find_from_image(
            screen=screen,
            name=name,
            threshold=threshold
        )

    # =====================================
    # 🎯 多目标检测
    # =====================================
    def detect_icons(
        self,
        screen,
        name: str,
        threshold: float = 0.8,
        nms_distance: int = 20
    ) -> List[Tuple[int, int]]:
        """
        返回多个匹配结果
        """
        return self.matcher.find_all_from_image(
            screen=screen,
            name=name,
            threshold=threshold,
            nms_distance=nms_distance
        )

    # =====================================
    # 🧠 OCR 检测
    # =====================================
    def detect_text(self, screen, region=None):
        """
        OCR识别

        :param screen: 当前截图
        :param region: (x1, y1, x2, y2)
        """
        if self.ocr is None:
            return []

        return self.ocr.read(screen, region)
    
    # 在 core/detector.py 的 Detector 类中添加

    def find_nearest_B_to_first_A(
        self,
        screen,
        iconA: str,
        iconB: str,
        threshold: float = 0.65
    ) -> Optional[Tuple[int, int]]:
        """
        检测第一个目标A（匹配度最高），然后找出离它最近的目标B的坐标。

        :param screen: 屏幕图像（BGR）
        :param iconA: 目标A的模板名称
        :param iconB: 目标B的模板名称
        :param threshold: 匹配阈值
        :return: 离A最近的B的中心坐标 (x, y)，如果A或B未检测到则返回 None
        """
        # 1. 检测第一个A（匹配度最高的位置）
        posA = self.detect_icon(screen, iconA, threshold)
        if posA is None:
            return None

        # 2. 检测所有B的位置
        allB = self.detect_icons(screen, iconB, threshold)
        if not allB:
            return None

        # 3. 计算距离，找出离A最近的B
        xA, yA = posA
        nearest = min(allB, key=lambda pos: (pos[0] - xA) ** 2 + (pos[1] - yA) ** 2)
        return nearest
