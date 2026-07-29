# core/ocr_engine.py

import os
import cv2
import pytesseract

# 使用相对路径，便携化打包
_tess_dir = os.path.join(os.path.dirname(os.path.abspath(__file__)), '..', 'Tesseract-OCR')
pytesseract.pytesseract.tesseract_cmd = os.path.join(_tess_dir, 'tesseract.exe')


class OCREngine:
    def __init__(self, debug=False):
        self.debug = debug
        self._digit_templates = {}
        self._load_digit_templates()

    def _load_digit_templates(self):
        """加载 digits/ 目录下的数字模板"""
        tmpl_dir = os.path.join(os.path.dirname(os.path.abspath(__file__)), '..', 'template', 'digits')
        if not os.path.isdir(tmpl_dir):
            return
        for fname in os.listdir(tmpl_dir):
            if fname.endswith('.png') and fname[:-4].isdigit():
                digit = fname[:-4]
                path = os.path.join(tmpl_dir, fname)
                tmpl = cv2.imread(path, cv2.IMREAD_GRAYSCALE)
                if tmpl is not None:
                    self._digit_templates[digit] = tmpl
        if self.debug and self._digit_templates:
            print(f"  [OCR] 已加载数字模板: {list(self._digit_templates.keys())}")

    def read(self, image, region=None):
        """读取图像中的文字"""
        if region:
            x1, y1, x2, y2 = region
            image = image[y1:y2, x1:x2]

        try:
            data = pytesseract.image_to_data(image, output_type=pytesseract.Output.DICT)
        except Exception as e:
            if self.debug:
                print(f"  [OCR] tesseract error: {e}")
            return []

        texts = []
        for i in range(len(data['text'])):
            text = data['text'][i].strip()
            conf = int(data['conf'][i]) if data['conf'][i] != '-1' else 0
            if text:
                texts.append({
                    "text": text,
                    "confidence": conf / 100.0,
                    "bbox": (data['left'][i], data['top'][i],
                             data['left'][i] + data['width'][i],
                             data['top'][i] + data['height'][i])
                })
        return texts

    def _ocr_digit_template(self, bw):
        """模板匹配：对二值化图像逐一匹配已加载的数字模板"""
        if not self._digit_templates:
            return ''

        h, w = bw.shape[:2]
        best_digit = ''
        best_score = 0.5

        for digit, tmpl in self._digit_templates.items():
            tmpl_resized = cv2.resize(tmpl, (w, h), interpolation=cv2.INTER_NEAREST)
            result = cv2.matchTemplate(bw, tmpl_resized, cv2.TM_CCOEFF_NORMED)
            _, max_val, _, _ = cv2.minMaxLoc(result)

            result_inv = cv2.matchTemplate(cv2.bitwise_not(bw), tmpl_resized, cv2.TM_CCOEFF_NORMED)
            _, max_val_inv, _, _ = cv2.minMaxLoc(result_inv)
            max_val = max(max_val, max_val_inv)

            if max_val > best_score:
                best_score = max_val
                best_digit = digit

        if self.debug:
            print(f"  [OCR] 模板匹配: '{best_digit}' (score={best_score:.3f})" if best_digit else
                  f"  [OCR] 模板匹配失败 (best={best_score:.3f})")
        return best_digit

    def _ocr_digit_core(self, gray):
        """识别数字：先 Tesseract，失败则模板匹配"""
        whitelist = '--psm 7 -c tessedit_char_whitelist=0123456789'

        # Tesseract OTSU 二值化
        _, bw = cv2.threshold(gray, 0, 255, cv2.THRESH_BINARY + cv2.THRESH_OTSU)
        text = pytesseract.image_to_string(bw, config=whitelist).strip()
        digits = ''.join(c for c in text if c.isdigit())
        if digits:
            return digits

        # 模板匹配后备（专治 "0"）
        return self._ocr_digit_template(bw)

    def read_digit(self, image, region=None):
        """从小 ROI 中读取数字，返回 int 或 None"""
        try:
            if region:
                x1, y1, x2, y2 = region
                image = image[y1:y2, x1:x2]

            if image.size == 0:
                return None

            gray = cv2.cvtColor(image, cv2.COLOR_BGR2GRAY)
            gray = cv2.resize(gray, None, fx=3, fy=3, interpolation=cv2.INTER_CUBIC)

            digits = self._ocr_digit_core(gray)
            if self.debug:
                print(f"  [OCR] digits='{digits}'")
            if digits:
                return int(digits)
            if self.debug:
                print("  [OCR] read_digit 未识别到数字")
            return None
        except Exception as e:
            print(f"  [OCR] ERROR: {e}")
            return None
