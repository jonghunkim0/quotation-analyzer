"""
parsers/ocr_processor.py - 스캔형 PDF OCR 처리
"""
import io
from typing import Optional
import fitz  # PyMuPDF

try:
    import pytesseract
    from PIL import Image
    HAS_OCR = True
except ImportError:
    HAS_OCR = False


class OCRProcessor:
    """
    스캔형 PDF를 OCR로 텍스트로 변환.
    pytesseract + Tesseract OCR 엔진 사용 (로컬 실행).
    """

    def __init__(self, lang: str = "kor+eng"):
        self.lang = lang
        self.available = HAS_OCR

    def is_available(self) -> bool:
        """OCR 엔진 사용 가능 여부"""
        if not HAS_OCR:
            return False
        try:
            pytesseract.get_tesseract_version()
            return True
        except Exception:
            return False

    def process_pdf(self, file_path: str) -> list:
        """
        스캔형 PDF를 페이지별로 OCR 처리.
        각 페이지의 텍스트를 반환.
        """
        if not self.is_available():
            raise RuntimeError(
                "OCR 엔진이 설치되어 있지 않습니다. "
                "Tesseract OCR를 설치하고 pytesseract를 확인해 주세요."
            )

        doc = fitz.open(file_path)
        pages_text = []

        for page_num in range(len(doc)):
            page = doc[page_num]
            # 고해상도 이미지로 렌더링 (300 DPI)
            mat = fitz.Matrix(300 / 72, 300 / 72)
            pix = page.get_pixmap(matrix=mat)
            img_data = pix.tobytes("png")

            # OCR
            image = Image.open(io.BytesIO(img_data))
            text = pytesseract.image_to_string(image, lang=self.lang)
            pages_text.append(text)

        doc.close()
        return pages_text

    def process_image(self, image_bytes: bytes) -> str:
        """이미지 바이트를 OCR 처리"""
        if not self.is_available():
            raise RuntimeError("OCR 엔진이 설치되어 있지 않습니다.")
        image = Image.open(io.BytesIO(image_bytes))
        return pytesseract.image_to_string(image, lang=self.lang)
