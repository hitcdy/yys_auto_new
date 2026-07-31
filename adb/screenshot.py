import cv2
import numpy as np
import struct
from adb.adb_client import ADBClient


class ScreenCapturer:
    def __init__(self, adb_client: ADBClient, extras=None):
        self.adb_client = adb_client
        self._extras = extras

    def set_extras(self, extras):
        """注入截图增强通道（如 MuMuExtras），优先于 ADB screencap。"""
        self._extras = extras

    def _capture_adb(self) -> np.ndarray:
        data = self.adb_client.screencap()
        if not data:
            raise RuntimeError("Screenshot failed: empty image data")

        w, h, fmt = struct.unpack_from("<III", data, 0)
        expected = w * h * 4
        header_size = len(data) - expected

        if header_size < 12 or header_size > 64:
            raise RuntimeError(f"Unexpected screencap header size: {header_size}")

        pixels = data[header_size:]

        if fmt == 1:  # RGBA_8888
            img = np.frombuffer(pixels, np.uint8).reshape(h, w, 4)
            img = cv2.cvtColor(img, cv2.COLOR_RGBA2BGR)
        else:
            img = np.frombuffer(pixels, np.uint8)
            img = cv2.imdecode(img, cv2.IMREAD_COLOR)
            if img is None:
                raise RuntimeError("Failed to decode screenshot")

        return img

    def capture(self) -> np.ndarray:
        # 优先使用截图增强通道，失败时单次回退 ADB screencap
        if self._extras is not None:
            try:
                return self._extras.screencap()
            except Exception as e:
                print(f"[截图] 截图增强失败，回退 ADB: {e}")
        return self._capture_adb()

    def capture_gray(self) -> np.ndarray:
        img = self.capture()
        return cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)

    def save(self, path: str):
        img = self.capture()
        cv2.imwrite(path, img)
