# vision/template_matcher.py

import cv2
import numpy as np
from typing import Optional, Tuple, List

class TemplateMatcher:
    def __init__(self, default_threshold: float = 0.8):
        self.templates = {}          # 原始彩色模板（备用）
        self.templates_gray = {}     # 灰度模板（用于匹配）
        self.templates_enhanced = {} # CLAHE 增强后的灰度模板（预计算，避免重复运算）
        self.default_threshold = default_threshold
        self._clahe = cv2.createCLAHE(clipLimit=2.0, tileGridSize=(8, 8))

    # =====================================
    # 📦 加载模板（存三份：彩色、灰度、增强灰度）
    # =====================================
    def load_templates(self, template_paths: dict):
        for name, path in template_paths.items():
            img = cv2.imread(path)
            if img is None:
                raise ValueError(f"Template '{name}' failed to load: {path}")
            self.templates[name] = img
            gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)
            self.templates_gray[name] = gray
            # 预计算 CLAHE 增强模板，避免每次匹配时重复运算
            self.templates_enhanced[name] = self._clahe.apply(gray)

    # =====================================
    # 🔧 内部方法：对灰度图做 CLAHE 增强
    # =====================================
    def _enhance_with_clahe(self, gray_img):
        """输入灰度图，输出增强后的灰度图"""
        return self._clahe.apply(gray_img)

    # =====================================
    # 🎯 单模板匹配
    # =====================================
    def find_from_image(
        self,
        screen,          # 可以是 BGR 或灰度
        name: str,
        threshold: float = 0.8,
        region: Optional[Tuple[int, int, int, int]] = None
    ) -> Optional[Tuple[int, int]]:
        if name not in self.templates_enhanced:
            raise ValueError(f"Template '{name}' not loaded")

        # 1. 把截图转为灰度（如果是彩色的）
        if len(screen.shape) == 3:
            screen_gray = cv2.cvtColor(screen, cv2.COLOR_BGR2GRAY)
        else:
            screen_gray = screen

        # 2. 如果传入了 region，裁剪灰度图（减少计算量）
        offset_x, offset_y = 0, 0
        if region:
            x1, y1, x2, y2 = region
            h, w = screen_gray.shape
            x1, y1 = max(0, x1), max(0, y1)
            x2, y2 = min(w, x2), min(h, y2)
            if x2 <= x1 or y2 <= y1:
                return None
            screen_gray = screen_gray[y1:y2, x1:x2]
            offset_x, offset_y = x1, y1

        # 3. 对截图做 CLAHE 增强，模板使用预计算版本
        screen_enhanced = self._enhance_with_clahe(screen_gray)
        template_enhanced = self.templates_enhanced[name]

        # 4. 模板匹配
        result = cv2.matchTemplate(
            screen_enhanced,
            template_enhanced,
            cv2.TM_CCOEFF_NORMED
        )
        _, max_val, _, max_loc = cv2.minMaxLoc(result)

        # 5. 判断是否超过阈值
        th = threshold if threshold is not None else self.default_threshold
        if max_val >= th:
            th, tw = template_enhanced.shape[:2]
            center_x = max_loc[0] + tw // 2 + offset_x
            center_y = max_loc[1] + th // 2 + offset_y
            return (center_x, center_y)

        return None

    # =====================================
    # 🎯 批量匹配：同一区域匹配多个模板，返回第一个命中的 (name, center)
    #    只做一次灰度转换 + 裁剪 + CLAHE，大幅减少 INSTANCE 热路径耗时
    # =====================================
    def find_first_from_image(
        self,
        screen,
        names: List[str],
        threshold: float = 0.8,
        region: Optional[Tuple[int, int, int, int]] = None
    ) -> Optional[Tuple[str, Tuple[int, int]]]:
        if len(screen.shape) == 3:
            screen_gray = cv2.cvtColor(screen, cv2.COLOR_BGR2GRAY)
        else:
            screen_gray = screen

        offset_x, offset_y = 0, 0
        if region:
            x1, y1, x2, y2 = region
            h, w = screen_gray.shape
            x1, y1 = max(0, x1), max(0, y1)
            x2, y2 = min(w, x2), min(h, y2)
            if x2 <= x1 or y2 <= y1:
                return None
            screen_gray = screen_gray[y1:y2, x1:x2]
            offset_x, offset_y = x1, y1

        screen_enhanced = self._enhance_with_clahe(screen_gray)

        th = threshold if threshold is not None else self.default_threshold
        for name in names:
            if name not in self.templates_enhanced:
                continue
            template_enhanced = self.templates_enhanced[name]
            result = cv2.matchTemplate(
                screen_enhanced, template_enhanced, cv2.TM_CCOEFF_NORMED
            )
            _, max_val, _, max_loc = cv2.minMaxLoc(result)
            if max_val >= th:
                th, tw = template_enhanced.shape[:2]
                center_x = max_loc[0] + tw // 2 + offset_x
                center_y = max_loc[1] + th // 2 + offset_y
                return (name, (center_x, center_y))

        return None

    # =====================================
    # 🎯 多阈值批量匹配：同一区域，每个模板独立阈值
    #    一次灰度转换 + 裁剪 + CLAHE，按顺序匹配，返回第一个命中的
    # =====================================
    def find_first_multi_threshold(
        self,
        screen,
        queries: List[Tuple[str, float]],  # [(name, threshold), ...]
        region: Optional[Tuple[int, int, int, int]] = None
    ) -> Optional[Tuple[str, Tuple[int, int]]]:
        if len(screen.shape) == 3:
            screen_gray = cv2.cvtColor(screen, cv2.COLOR_BGR2GRAY)
        else:
            screen_gray = screen

        offset_x, offset_y = 0, 0
        if region:
            x1, y1, x2, y2 = region
            h, w = screen_gray.shape
            x1, y1 = max(0, x1), max(0, y1)
            x2, y2 = min(w, x2), min(h, y2)
            if x2 <= x1 or y2 <= y1:
                return None
            screen_gray = screen_gray[y1:y2, x1:x2]
            offset_x, offset_y = x1, y1

        screen_enhanced = self._enhance_with_clahe(screen_gray)

        for name, threshold in queries:
            if name not in self.templates_enhanced:
                continue
            template_enhanced = self.templates_enhanced[name]
            result = cv2.matchTemplate(
                screen_enhanced, template_enhanced, cv2.TM_CCOEFF_NORMED
            )
            _, max_val, _, max_loc = cv2.minMaxLoc(result)
            th = threshold if threshold is not None else self.default_threshold
            if max_val >= th:
                th, tw = template_enhanced.shape[:2]
                center_x = max_loc[0] + tw // 2 + offset_x
                center_y = max_loc[1] + th // 2 + offset_y
                return (name, (center_x, center_y))

        return None

    # =====================================
    # 🎯 多目标匹配（支持 region + CLAHE 增强）
    # =====================================
    def find_all_from_image(
        self,
        screen,
        name: str,
        threshold: float = 0.8,
        nms_distance: int = 20,
        region: Optional[Tuple[int, int, int, int]] = None
    ) -> List[Tuple[int, int]]:
        if name not in self.templates_enhanced:
            raise ValueError(f"Template '{name}' not loaded")

        if len(screen.shape) == 3:
            screen_gray = cv2.cvtColor(screen, cv2.COLOR_BGR2GRAY)
        else:
            screen_gray = screen

        offset_x, offset_y = 0, 0
        if region:
            x1, y1, x2, y2 = region
            h, w = screen_gray.shape
            x1, y1 = max(0, x1), max(0, y1)
            x2, y2 = min(w, x2), min(h, y2)
            if x2 <= x1 or y2 <= y1:
                return []
            screen_gray = screen_gray[y1:y2, x1:x2]
            offset_x, offset_y = x1, y1

        screen_enhanced = self._enhance_with_clahe(screen_gray)
        template_enhanced = self.templates_enhanced[name]

        th = threshold if threshold is not None else self.default_threshold
        result = cv2.matchTemplate(
            screen_enhanced, template_enhanced, cv2.TM_CCOEFF_NORMED
        )
        locations = np.where(result >= th)
        points = []
        th, tw = template_enhanced.shape[:2]
        for pt in zip(*locations[::-1]):
            center = (pt[0] + tw // 2 + offset_x, pt[1] + th // 2 + offset_y)
            points.append(center)

        filtered = []
        for p in points:
            if all(np.linalg.norm(np.array(p) - np.array(fp)) > nms_distance
                   for fp in filtered):
                filtered.append(p)
        return filtered