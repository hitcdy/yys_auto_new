# core/template_matcher.py

import cv2
import numpy as np
from typing import Optional, Tuple, List


class TemplateMatcher:
    """
    纯模板匹配算法类
    不负责截图
    不负责逻辑判断
    """

    def __init__(self, default_threshold: float = 0.8):
        self.templates = {}
        self.default_threshold = default_threshold

    # =====================================
    # 📦 加载模板
    # =====================================
    def load_templates(self, template_paths: dict):
        """
        template_paths = {
            "name": "path/to/image.png"
        }
        """
        for name, path in template_paths.items():
            img = cv2.imread(path)
            if img is None:
                raise ValueError(f"Template '{name}' failed to load: {path}")
            self.templates[name] = img

    # =====================================
    # 🎯 单个目标匹配
    # =====================================
    def find_from_image(
        self,
        screen,
        name: str,
        threshold: float = 0.8
    ) -> Optional[Tuple[int, int]]:
        """
        返回匹配中心点 (x, y) 或 None
        """

        if name not in self.templates:
            raise ValueError(f"Template '{name}' not loaded")

        template = self.templates[name]
        th = threshold if threshold is not None else self.default_threshold

        result = cv2.matchTemplate(
            screen,
            template,
            cv2.TM_CCOEFF_NORMED
        )

        min_val, max_val, min_loc, max_loc = cv2.minMaxLoc(result)

        if max_val >= th:
            h, w = template.shape[:2]
            center_x = max_loc[0] + w // 2
            center_y = max_loc[1] + h // 2
            return (center_x, center_y)

        return None

    # =====================================
    # 🎯 多个目标匹配
    # =====================================
    def find_all_from_image(
        self,
        screen,
        name: str,
        threshold: float = 0.8,
        nms_distance: int = 20
    ) -> List[Tuple[int, int]]:
        """
        返回多个匹配点
        """

        if name not in self.templates:
            raise ValueError(f"Template '{name}' not loaded")

        template = self.templates[name]
        th = threshold if threshold is not None else self.default_threshold

        result = cv2.matchTemplate(
            screen,
            template,
            cv2.TM_CCOEFF_NORMED
        )

        locations = np.where(result >= th)
        points = []

        h, w = template.shape[:2]

        for pt in zip(*locations[::-1]):
            center = (pt[0] + w // 2, pt[1] + h // 2)
            points.append(center)

        # 简单 NMS 去重
        filtered = []
        for p in points:
            if all(
                np.linalg.norm(np.array(p) - np.array(fp)) > nms_distance
                for fp in filtered
            ):
                filtered.append(p)

        return filtered