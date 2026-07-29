# vision/detector.py

from typing import Optional, Tuple, List

class Detector:
    def __init__(self, matcher, ocr_engine, capturer):
        self.matcher = matcher
        self.ocr = ocr_engine
        self.capturer = capturer

    # =====================================
    # 📸 截图入口（不变）
    # =====================================
    def get_screen(self):
        return self.capturer.capture()

    # =====================================
    # 🎯 单目标检测（新增 region 参数）
    # =====================================
    def detect_icon(
        self,
        screen,
        name: str,
        threshold: float = 0.8,
        region: Optional[Tuple[int, int, int, int]] = None
    ) -> Optional[Tuple[int, int]]:
        """
        :param screen: 截图
        :param name: 模板名
        :param threshold: 阈值
        :param region: 限制搜索区域 (x1, y1, x2, y2)，例如 (100, 200, 500, 600)
        """
        # 直接把 region 透传给 matcher，裁剪和增强都在 matcher 里完成
        return self.matcher.find_from_image(
            screen=screen,
            name=name,
            threshold=threshold,
            region=region
        )

    # =====================================
    # 🎯 多目标检测（支持 region）
    # =====================================
    def detect_icons(
        self,
        screen,
        name: str,
        threshold: float = 0.8,
        nms_distance: int = 20,
        region: Optional[Tuple[int, int, int, int]] = None
    ) -> List[Tuple[int, int]]:
        return self.matcher.find_all_from_image(
            screen=screen,
            name=name,
            threshold=threshold,
            nms_distance=nms_distance,
            region=region
        )

    # =====================================
    # 🧠 OCR 检测（不变）
    # =====================================
    def detect_text(self, screen, region=None):
        if self.ocr is None:
            return []
        return self.ocr.read(screen, region)

    # =====================================
    # 🎫 突破券数字识别
    # =====================================
    def read_ticket_count(self, screen, region):
        """读取突破券数量，返回 int，失败返回 -1"""
        if self.ocr is None:
            return -1
        result = self.ocr.read_digit(screen, region)
        return result if result is not None else -1

    # =====================================
    # 🔗 找最近 B（不变）
    # =====================================
    def find_nearest_B_to_first_A(
        self,
        screen,
        iconA: str,
        iconB: str,
        threshold: float = 0.65
    ) -> Optional[Tuple[int, int]]:
        posA = self.detect_icon(screen, iconA, threshold)
        if posA is None:
            return None
        allB = self.detect_icons(screen, iconB, threshold)
        if not allB:
            return None
        xA, yA = posA
        nearest = min(allB, key=lambda pos: (pos[0] - xA) ** 2 + (pos[1] - yA) ** 2)
        return nearest