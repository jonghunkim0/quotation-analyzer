"""
parsers/pdf_parser.py - PDF 견적서 파서 (텍스트형 + 스캔형 감지)
"""
import re
from typing import Optional
import fitz  # PyMuPDF
from quotation_analyzer.models.data_models import QuotationItem, QuotationFile, FileStatus
from quotation_analyzer.utils.helpers import (
    generate_id,
    parse_amount,
    is_total_row,
    normalize_text,
)
from quotation_analyzer.config import COLUMN_ALIASES


class PDFParser:
    """PDF 견적서 파서"""

    def __init__(self):
        self.is_scanned = False
        self.needs_ocr = False

    def check_scanned(self, file_path: str) -> bool:
        """
        스캔형 PDF인지 감지.
        텍스트 레이어가 없거나 극소수인 경우 스캔형으로 판단.
        """
        try:
            doc = fitz.open(file_path)
            total_text = ""
            for page in doc:
                total_text += page.get_text()
            doc.close()

            # 텍스트가 거의 없으면 스캔형
            text_length = len(total_text.strip())
            return text_length < 50
        except Exception:
            return True

    def parse(
        self,
        file_path: str,
        filename: str,
        scenario: str = "견적가",
    ) -> QuotationFile:
        """
        PDF 파일을 파싱하여 QuotationFile 반환.
        """
        qf = QuotationFile(
            file_id=generate_id("file_"),
            filename=filename,
            file_type="pdf",
            status=FileStatus.PROCESSING,
            scenario=scenario,
        )

        # 스캔형 감지
        self.is_scanned = self.check_scanned(file_path)
        qf.is_scanned = self.is_scanned
        qf.needs_ocr = self.is_scanned

        if self.is_scanned:
            qf.status = FileStatus.OCR_NEEDED
            qf.error_message = "스캔형 PDF입니다. OCR 처리가 필요합니다."
            return qf

        # 텍스트형 PDF 파싱
        try:
            doc = fitz.open(file_path)
        except Exception as e:
            qf.status = FileStatus.ERROR
            qf.error_message = f"PDF를 열 수 없습니다: {e}"
            return qf

        items = []
        original_total = 0.0
        tax_amount = 0.0
        page_count = len(doc)
        qf.sheets = [f"Page {i+1}" for i in range(page_count)]

        for page_num in range(page_count):
            page = doc[page_num]
            text = page.get_text()
            lines = [line.strip() for line in text.split("\n") if line.strip()]

            # 테이블 구조 감지: 숫자 패턴이 있는 행
            page_items = self._extract_items_from_lines(
                lines, filename, f"Page {page_num+1}", scenario
            )
            items.extend(page_items)

            # 합계 행에서 원본 총액 추출
            for line in lines:
                if is_total_row(line):
                    amounts = re.findall(r"[\d,]+\.?\d*", line)
                    if amounts:
                        val = parse_amount(amounts[-1])
                        if val > 0:
                            original_total = val
                    if any(kw in line for kw in ["부가세", "VAT", "세금"]):
                        amounts = re.findall(r"[\d,]+\.?\d*", line)
                        if amounts:
                            tax_amount = parse_amount(amounts[-1])

        doc.close()

        qf.items = items
        qf.original_total = original_total
        qf.extracted_total = sum(i.amount for i in items)
        qf.tax_amount = tax_amount
        qf.status = FileStatus.COMPLETED
        return qf

    def _extract_items_from_lines(
        self, lines: list, filename: str, page_label: str, scenario: str
    ) -> list:
        """
        PDF 텍스트 행에서 견적 항목 추출.
        행 구조: 품명 ... 수량 ... 단가 ... 금액
        """
        items = []
        row_num = 0

        for line in lines:
            row_num += 1

            # 합계/소계 행 스킵
            if is_total_row(line):
                continue

            # 빈 행 또는 페이지 번호 스킵
            if len(line) < 3 or line.isdigit():
                continue

            # 금액 패턴 감지 (최소 1개 숫자 포함)
            if not re.search(r"\d", line):
                continue

            # 행에서 숫자 추출
            # 패턴: 텍스트 부분 + 숫자들
            # 일반적인 견적서: "품명/사양 ... 수량 ... 단가 ... 금액"
            parts = self._split_line(line)

            if not parts:
                continue

            # 마지막 숫자를 금액으로, 그 전을 단가/수량으로 추정
            numbers = []
            text_parts = []
            for part in parts:
                num = parse_amount(part)
                if num != 0 or part.strip() in {"0", "0.0"}:
                    numbers.append((part.strip(), num))
                else:
                    text_parts.append(part.strip())

            if not numbers:
                continue

            # 금액은 보통 마지막 숫자
            amount = numbers[-1][1]

            # 수량과 단가 추정
            quantity = 1.0
            unit_price = 0.0
            if len(numbers) >= 3:
                quantity = numbers[-3][1]
                unit_price = numbers[-2][1]
            elif len(numbers) == 2:
                # 두 숫자: 수량과 단가, 또는 단가와 금액
                if numbers[0][1] <= 100:  # 수량으로 추정
                    quantity = numbers[0][1]
                    unit_price = numbers[1][1]
                else:
                    unit_price = numbers[0][1]
                    amount = numbers[1][1]

            # 품명: 텍스트 부분 합치기
            name = " ".join(text_parts[:2]) if text_parts else ""
            spec = " ".join(text_parts[2:]) if len(text_parts) > 2 else ""

            if not name and amount == 0:
                continue

            item = QuotationItem(
                item_id=generate_id("item_"),
                source_file=filename,
                source_sheet=page_label,
                source_row=row_num,
                name=name,
                spec=spec,
                quantity=quantity,
                unit_price=unit_price,
                amount=amount,
                scenario=scenario,
            )
            items.append(item)

        return items

    def _split_line(self, line: str) -> list:
        """
        PDF 행을 의미 있는 부분으로 분할.
        여러 공백 또는 탭으로 구분.
        """
        # 여러 공백/탭으로 분할
        parts = re.split(r"\s{2,}|\t+", line)
        return [p.strip() for p in parts if p.strip()]
