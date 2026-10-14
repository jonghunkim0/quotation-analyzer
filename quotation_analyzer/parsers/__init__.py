from .excel_parser import ExcelParser

try:
    from .pdf_parser import PDFParser
    from .ocr_processor import OCRProcessor
    __all__ = ["ExcelParser", "PDFParser", "OCRProcessor"]
except ImportError:
    # PyMuPDF/pdfplumber 미설치 환경 (Excel 전용)
    PDFParser = None
    OCRProcessor = None
    __all__ = ["ExcelParser"]
