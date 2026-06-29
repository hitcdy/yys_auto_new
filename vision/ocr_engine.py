# core/ocr_engine.py

import cv2


class OCREngine:
    def __init__(self, reader=None, debug=False):
        """
        reader: 外部OCR实例（例如easyocr.Reader）
        """
        self.reader = reader
        self.debug = debug

    def read(self, image, region=None):
        """
        读取图像中的文字

        image: numpy图像
        region: (x1, y1, x2, y2)
        """
        if region:
            x1, y1, x2, y2 = region
            image = image[y1:y2, x1:x2]

        if self.reader is None:
            print("OCR reader未初始化")
            return []

        results = self.reader.readtext(image)

        texts = []
        for bbox, text, conf in results:
            texts.append({
                "text": text,
                "confidence": conf,
                "bbox": bbox
            })

        return texts