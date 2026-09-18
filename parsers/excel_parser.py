"""
parsers/excel_parser.py - Excel 견적서 파서
"""
import pandas as pd
from typing import Optional
from models.data_models import QuotationItem, QuotationFile, FileStatus
from utils.helpers import (
    generate_id,
    parse_amount,
    match_column,
    is_total_row,
    is_blank_row,
    normalize_text,
)
from config import COLUMN_ALIASES


class ExcelParser:
    """Excel 견적서 파서"""

    def __init__(self):
        self.column_map = {}  # {canonical_name: col_index}

    def list_sheets(self, file_path: str) -> list:
        """Excel 파일의 시트 목록 반환"""
        try:
            with pd.ExcelFile(file_path) as xls:
                return list(xls.sheet_names)
        except Exception as e:
            raise ValueError(f"Excel 파일을 열 수 없습니다: {e}")

    def detect_header_row(self, df: pd.DataFrame, max_scan: int = 15) -> int:
        """
        헤더 행을 자동 탐지.
        품명/금액/수량 등 핵심 열 이름이 포함된 행을 찾음.
        """
        best_row = -1
        best_score = 0

        for i in range(min(max_scan, len(df))):
            row_values = [str(v) for v in df.iloc[i].tolist() if pd.notna(v)]
            score = 0
            for canonical, aliases in COLUMN_ALIASES.items():
                for cell in row_values:
                    if match_column(cell, aliases):
                        score += 1
                        break
            if score > best_score:
                best_score = score
                best_row = i

        # 최소 2개 핵심 열이 있어야 헤더로 인정
        if best_score >= 2:
            return best_row
        return -1

    def map_columns(self, header_row: pd.Series) -> dict:
        """헤더 행을 정규화된 열 이름으로 매핑"""
        self.column_map = {}
        for idx, value in header_row.items():
            if pd.isna(value):
                continue
            header = str(value).strip()
            for canonical, aliases in COLUMN_ALIASES.items():
                if canonical not in self.column_map:
                    if match_column(header, aliases):
                        self.column_map[canonical] = idx
                        break
        return self.column_map

    def parse_sheet(
        self,
        file_path: str,
        sheet_name: str,
        filename: str,
        scenario: str = "견적가",
    ) -> QuotationFile:
        """
        특정 시트를 파싱하여 QuotationFile 반환.
        """
        qf = QuotationFile(
            file_id=generate_id("file_"),
            filename=filename,
            file_type="excel",
            status=FileStatus.PROCESSING,
            sheets=[sheet_name],
            selected_sheet=sheet_name,
            scenario=scenario,
        )

        try:
            df = pd.read_excel(file_path, sheet_name=sheet_name, header=None)
        except Exception as e:
            qf.status = FileStatus.ERROR
            qf.error_message = f"시트 '{sheet_name}' 읽기 실패: {e}"
            return qf

        # 헤더 행 탐지
        header_idx = self.detect_header_row(df)
        if header_idx < 0:
            qf.status = FileStatus.ERROR
            qf.error_message = "헤더 행을 찾을 수 없습니다. 열 이름을 확인해 주세요."
            return qf

        # 열 매핑
        header_row = df.iloc[header_idx]
        self.map_columns(header_row)

        required_cols = ["품명", "금액"]
        if "품명" not in self.column_map:
            # 품명 대신 '항목' 또는 첫 번째 텍스트 열 사용
            for idx, value in header_row.items():
                if pd.notna(value) and str(value).strip():
                    self.column_map["품명"] = idx
                    break

        if "금액" not in self.column_map:
            # 금액이 없으면 수량×단가로 계산 예정
            pass

        # 데이터 행 처리
        items = []
        original_total = 0.0
        tax_amount = 0.0

        for row_idx in range(header_idx + 1, len(df)):
            row = df.iloc[row_idx]
            values = row.tolist()

            # 빈 행 스킵
            if is_blank_row(values):
                continue

            # 각 필드 추출
            name = self._get_cell(row, "품명")
            spec = self._get_cell(row, "사양")
            qty_raw = self._get_cell(row, "수량")
            price_raw = self._get_cell(row, "단가")
            amount_raw = self._get_cell(row, "금액")
            remark = self._get_cell(row, "비고")
            category_hint = self._get_cell(row, "구분")
            vendor = self._get_cell(row, "업체명")
            tax_raw = self._get_cell(row, "부가세")

            # 합계/소계 행 감지
            row_text = " ".join(
                str(v) for v in values if pd.notna(v)
            )
            is_total = is_total_row(row_text)
            is_tax = is_total and any(
                normalize_text(kw) in normalize_text(row_text)
                for kw in ["부가세", "vat", "세금", "tax"]
            )

            # 금액 계산
            amount = parse_amount(amount_raw)
            quantity = parse_amount(qty_raw) if qty_raw else 1.0
            unit_price = parse_amount(price_raw) if price_raw else 0.0

            # 금액이 없으면 수량 × 단가
            if amount == 0 and quantity and unit_price:
                amount = quantity * unit_price

            # 부가세 처리
            if is_tax:
                tax_amount += abs(amount)
                continue

            # 합계 행은 원본 총액으로만 사용
            if is_total:
                if amount > 0:
                    original_total = amount
                continue

            # 품명이 비어 있으면 스킵 (단, 금액이 있는 경우 제외)
            if not name and amount == 0:
                continue

            item = QuotationItem(
                item_id=generate_id("item_"),
                source_file=filename,
                source_sheet=sheet_name,
                source_row=row_idx + 1,  # 1-based
                name=str(name).strip() if name else "",
                spec=str(spec).strip() if spec else "",
                quantity=quantity,
                unit_price=unit_price,
                amount=amount,
                remark=str(remark).strip() if remark else "",
                category_hint=str(category_hint).strip() if category_hint else "",
                vendor=str(vendor).strip() if vendor else "",
                scenario=scenario,
            )
            items.append(item)

        qf.items = items
        qf.original_total = original_total
        qf.extracted_total = sum(i.amount for i in items)
        qf.tax_amount = tax_amount
        qf.status = FileStatus.COMPLETED
        return qf

    def _get_cell(self, row: pd.Series, canonical: str):
        """정규화된 열 이름으로 셀 값 가져오기"""
        col_idx = self.column_map.get(canonical)
        if col_idx is None:
            return None
        try:
            value = row.iloc[col_idx]
            if pd.isna(value):
                return None
            return value
        except (IndexError, KeyError):
            return None
