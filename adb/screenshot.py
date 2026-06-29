import cv2
import numpy as np
from adb.adb_client import ADBClient


class ScreenCapturer:
    def __init__(self, adb_client: ADBClient):
        self.adb_client = adb_client

    def capture(self) -> np.ndarray:
        """
        浠庤澶囨埅灞忓苟杩斿洖 OpenCV 鏍煎紡鍥惧儚 (BGR)
        """
        # 1?? 鑾峰彇 PNG 瀛楄妭娴�
        img_bytes = self.adb_client.screencap()

        if not img_bytes:
            raise RuntimeError("Screenshot failed: empty image data")

        # 2?? 杞负 numpy 鏁扮粍
        img_array = np.frombuffer(img_bytes, np.uint8)

        # 3?? 瑙ｇ爜涓� OpenCV 鍥惧儚
        img = cv2.imdecode(img_array, cv2.IMREAD_COLOR)

        if img is None:
            raise RuntimeError("Failed to decode screenshot")

        return img

    def capture_gray(self) -> np.ndarray:
        """
        杩斿洖鐏板害鍥撅紙鐢ㄤ簬妯℃澘鍖归厤绛夛級
        """
        img = self.capture()
        gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)
        return gray

    def save(self, path: str):
        """
        鎴浘骞朵繚瀛樺埌鏈湴锛堣皟璇曠敤锛�
        """
        img = self.capture()
        cv2.imwrite(path, img)