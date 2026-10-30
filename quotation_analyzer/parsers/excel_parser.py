"""
parsers/excel_parser.py - Excel 견적서 파서
"""
import math
import re
import pandas as pd
from typing import Optional
from quotation_analyzer.models.data_models import QuotationItem, QuotationFile, FileStatus
from quotation_analyzer.utils.helpers import (
    generate_id,
    parse_amount,
    match_column,
    is_total_row,
    is_blank_row,
    normalize_text,
)
from quotation_analyzer.config import COLUMN_ALIASES, COST_CATEGORIES

# ─── 모듈 레벨 상수/정규식 (매 호출마다 재생성 방지) ─────────────
_REF_RE = re.compile(r"(?<![A-Za-z0-9_])([A-Z]{1,3})(\d+)")
_PAREN_RE = re.compile(r"^\((\d+)\)\s*(.+)")
_BRACKET_RE = re.compile(r"^\[(\d+)\](.*)$")
_BRACKET_ONLY_RE = re.compile(r"^\[(\d+)\]$")
_PAREN_ONLY_RE = re.compile(r"^\(\d+\)$")
_BRACKET_PREFIX_RE = re.compile(r"^\[\d+\]")
_PAREN_PREFIX_RE = re.compile(r"^\(\d+\)")
_SUM_RANGE_RE = re.compile(r"=SUM\(([A-Z]{1,3})(\d+):([A-Z]{1,3})(\d+)\)", re.IGNORECASE)

_SECTION_KW = ["전장", "제어", "전기", "electrical", "control"]
_SECTION_NAMES = ("구매품", "가공품", "기구", "재료비", "인건비", "경비")
# 비용 성격 섹션 라벨 — 헤더 없는 구분 열(B열 등) 감지용
_SECTION_COL_LABELS = {
    "인건비", "자재비", "재료비", "경비", "자체비", "기구", "전장", "제어",
    "전기", "구매품", "가공품", "사급품", "마진",
}
_SUBTOTAL_CATS = {
    "기구 구매품", "전장 구매품", "제어 구매품",
    "기구 가공품", "전장 가공품",
    "사급품",
}
_TAX_KWS = ["부가세", "vat", "세금", "tax"]


def _is_section_marker(text: str) -> bool:
    """섹션 마커인지 판별.
    [n]+이름, 소계, 합계, Unit명, "구매품 소개"/"가공품 소개" → True
    (n)+텍스트 → False (항목 번호)
    숫자만 있는 [n]/(n) → False"""
    h = text.replace(" ", "").replace("\n", "")
    if not h:
        return False
    if h.lower().startswith("[remark]") or h.lower() == "remark":
        return True
    if _PAREN_PREFIX_RE.match(h):
        return False
    if _BRACKET_RE.match(h):
        return True
    if _PAREN_ONLY_RE.match(h) or _BRACKET_ONLY_RE.match(h):
        return False
    if "소계" in h or "합계" in h:
        return True
    if h.lower().startswith("unit명"):
        return True
    # "구매품 소개", "가공품 소개" 등 섹션 소개 헤더
    if "소개" in h and any(sec in h for sec in _SECTION_NAMES):
        return True
    return False


def _is_section_level_hint(text: str) -> bool:
    """구분 셀 값이 섹션 레벨 마커인지 판별."""
    h = text.replace(" ", "").replace("\n", "")
    if not h:
        return False
    if _BRACKET_PREFIX_RE.match(h):
        return True
    if "소계" in h:
        return True
    if "합계" in h:
        return False
    if "(" in h or "（" in h:
        return False
    if any(kw in h for kw in _SECTION_KW):
        return True
    if h in _SECTION_NAMES:
        return True
    # "구매품 소개", "가공품 소개" 등 섹션 소개 헤더
    if "소개" in h and any(sec in h for sec in _SECTION_NAMES):
        return True
    for cat in COST_CATEGORIES:
        if normalize_text(cat) == h:
            return True
    return False


class ExcelParser:
    """Excel 견적서 파서"""

    def __init__(self):
        self.column_map = {}  # {canonical_name: col_index}
        self.section_cols = []  # 무헤더 섹션 열 인덱스 (B열 등)

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

    def _detect_section_columns(self, df: pd.DataFrame, header_idx: int) -> list:
        """헤더가 없으면서 비용 성격 섹션 라벨(인건비/자재비/경비 등)을 가진 열 인덱스 반환.
        이미 canonical 열로 매핑된 열은 제외. (B열 같은 무헤더 구분 열 감지)"""
        mapped = set(self.column_map.values())
        cols = []
        n_cols = len(df.columns)
        for c in range(n_cols):
            if c in mapped:
                continue
            hits = 0
            for r in range(header_idx + 1, len(df)):
                v = df.iat[r, c]
                if pd.notna(v):
                    h = normalize_text(str(v))
                    if h in _SECTION_COL_LABELS:
                        hits += 1
            if hits >= 1:
                cols.append(c)
        return cols

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

        # 병합 셀 전파 (헤더 탐지 이전 — 병합된 헤더 셀 값이 채워져야 열 매핑이 정확)
        df = self._fill_merged_cells(file_path, sheet_name, df)

        # 헤더 행 탐지
        header_idx = self.detect_header_row(df)
        if header_idx < 0:
            qf.status = FileStatus.ERROR
            qf.error_message = "헤더 행을 찾을 수 없습니다. 열 이름을 확인해 주세요."
            return qf

        # 열 매핑
        header_row = df.iloc[header_idx]
        self.map_columns(header_row)

        if "품명" not in self.column_map:
            for idx, value in header_row.items():
                if pd.notna(value) and str(value).strip():
                    self.column_map["품명"] = idx
                    break

        # 구분 열 폴백: 헤더에 "구분"이 없으면, 첫 열에 섹션 힌트(구매품/가공품 등)가 있으면 그 열을 구분으로 사용
        if "구분" not in self.column_map:
            first_col = 0
            sample = df.iloc[header_idx + 1: header_idx + 20, first_col]
            if sample.apply(lambda v: _is_section_level_hint(str(v)) if pd.notna(v) else False).any():
                self.column_map["구분"] = first_col

        # 무헤더 섹션 열(B열 등) 감지: 헤더가 없으면서 비용 성격 라벨(인건비/자재비/경비)을 가진 열
        self.section_cols = self._detect_section_columns(df, header_idx)

        # 수식(합산) 행 감지 (열 매핑 이후 — 금액/단가 열 인덱스 필요)
        # 다른 행들의 합산으로 산출된 값(=SUM(I5:I14), =I15+I17)은
        # 세부 항목과 금액이 중복되므로 견적 항목에서 제외
        formula_rows = self._detect_formula_rows(file_path, sheet_name)
        # 배경색이 다수 데이터 행과 다른 행(섹션 헤더/요약 행) 감지
        color_summary_rows = self._detect_color_summary_rows(
            file_path, sheet_name, header_idx
        )
        # 색상과 무관하게, 아래 여러 행의 합산으로 계산된 값인 행을 요약 행으로 감지
        # (색상 구분이 없는 견적서도 대응. 정상 가격 항목은 제외)
        summary_rows = self._verify_summary_by_sum(
            df, header_idx, color_summary_rows
        )

        # No 열 인덱스 탐지
        no_col_idx = None
        for idx, value in header_row.items():
            if pd.notna(value) and normalize_text(str(value).strip()) in ("no", "no.", "번호", "itemno", "n"):
                no_col_idx = idx
                break

        # 소계 행의 =SUM(Xa:Xb) 수식 범위 추출 (섹션 경계 정확화)
        sum_ranges = self._detect_subtotal_sum_ranges(file_path, sheet_name)

        # 섹션 컨텍스트 계산
        section_hint_map, section_marker_rows = self._compute_section_context(
            df, header_idx, no_col_idx, sum_ranges
        )

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

            # 합산 수식 행 → 합산금액 항목으로 생성 (원가분석에는 포함 안 함)
            if row_idx in formula_rows:
                _nm = self._get_cell(row, "품명")
                _am = parse_amount(self._get_cell(row, "금액"))
                _fm = formula_rows[row_idx]
                items.append(QuotationItem(
                    item_id=generate_id("item_"),
                    source_file=filename,
                    source_sheet=sheet_name,
                    source_row=row_idx + 1,
                    name=str(_nm).strip() if _nm else "",
                    amount=_am,
                    is_sum_row=True,
                    sum_formula=_fm,
                    auto_category="합산금액",
                    final_category="합산금액",
                    confidence=100.0,
                    reason=f"합산 행: {_fm}",
                    scenario=scenario,
                ))
                continue
            # 색상 행 + 아래 행 합산 수치 검증 통과 → 합산금액 항목으로 생성
            if row_idx in summary_rows:
                _nm = self._get_cell(row, "품명")
                _am = parse_amount(self._get_cell(row, "금액"))
                _fm = summary_rows[row_idx]
                items.append(QuotationItem(
                    item_id=generate_id("item_"),
                    source_file=filename,
                    source_sheet=sheet_name,
                    source_row=row_idx + 1,
                    name=str(_nm).strip() if _nm else "",
                    amount=_am,
                    is_sum_row=True,
                    sum_formula=_fm,
                    auto_category="합산금액",
                    final_category="합산금액",
                    confidence=100.0,
                    reason=f"합산 행: {_fm}",
                    scenario=scenario,
                ))
                continue
            # 섹션 마커 행 슂 (예: "[2] 전장/제어", "(1) Unit명" — 견적 항목이 아님)
            # 품명이 비어 있거나 섹션 이름만 있는 행은 데이터가 아님
            # 단, 합계/소계 행은 슂하지 않음 (총액 감지용)
            if row_idx in section_marker_rows:
                name_check = self._get_cell(row, "품명")
                name_check_h = str(name_check).replace(" ", "").replace("\n", "") if name_check else ""
                is_total_name = name_check_h and is_total_row(name_check_h)
                # 섹션 라벨과 실제 데이터(금액/단가)가 같은 행이면 데이터 행으로 유지
                _amt_chk = parse_amount(self._get_cell(row, "금액"))
                _prc_chk = parse_amount(self._get_cell(row, "단가"))
                has_real_value = (abs(_amt_chk) >= 1) or (abs(_prc_chk) >= 1)
                if not is_total_name and not has_real_value and (
                    not name_check_h
                    or _is_section_level_hint(name_check_h)
                    or name_check_h.lower().startswith("unit명")
                ):
                    continue
            # Remark 섹션 행 스킵 (참고사항 — 견적 항목이 아님)
            _sec_hint = section_hint_map.get(row_idx, "")
            if "remark" in _sec_hint.lower():
                _amt_chk2 = parse_amount(self._get_cell(row, "금액"))
                if abs(_amt_chk2) < 1:
                    continue
            # 각 필드 추출
            name = self._get_cell(row, "품명")
            spec = self._get_cell(row, "사양")
            qty_raw = self._get_cell(row, "수량")
            price_raw = self._get_cell(row, "단가")
            amount_raw = self._get_cell(row, "금액")
            remark = self._get_cell(row, "비고")
            category_hint = self._get_cell(row, "구분")

            # 무헤더 섹션 열(B열 등) 값 조합 → "인건비 > 경비"
            _sub_parts = []
            for _c in self.section_cols:
                _v = row.iloc[_c] if _c < len(row) else None
                if pd.notna(_v) and str(_v).strip() and str(_v).strip() not in ("-", "--", "—"):
                    _sub_parts.append(str(_v).strip())
            _sub_str = " ".join(_sub_parts)
            if _sub_str:
                if category_hint:
                    _top = str(category_hint).strip()
                    if normalize_text(_top) != normalize_text(_sub_str):
                        category_hint = f"{_top} > {_sub_str}"
                    else:
                        category_hint = _sub_str
                else:
                    category_hint = _sub_str

            # 품명이 "-" 또는 비어 있으면 "(n)이름" 패턴에서 추출
            name_str = str(name).strip() if name else ""
            if not name_str or name_str in ("-", "--", "—"):
                for v in values:
                    if pd.isna(v):
                        continue
                    m = _PAREN_RE.match(str(v).strip())
                    if m and len(m.group(2).strip()) > 1:
                        name = m.group(2).strip()
                        break
            section_hint = section_hint_map.get(row_idx, "")
            if not category_hint:
                category_hint = section_hint
            elif section_hint and str(category_hint) != section_hint:
                # 행의 구분 + 섹션 컨텍스트 조합 (예: "구매품" + "전장/제어" → "전장/제어 구매품")
                category_hint = f"{section_hint} {category_hint}"
            vendor = self._get_cell(row, "업체명")
            tax_raw = self._get_cell(row, "부가세")

            # 원본 행 전체 셀 텍스트 (분류 시 모든 내용 참고)
            row_all_text = " ".join(
                str(v).strip() for v in values if pd.notna(v) and str(v).strip()
            )

            # 합계/소계 행 감지
            is_total = is_total_row(row_all_text)
            if not is_total:
                norm_name_check = normalize_text(str(name).strip()) if name else ""
                if norm_name_check:
                    for cat in _SUBTOTAL_CATS:
                        if normalize_text(cat) == norm_name_check:
                            is_total = True
                            break
            is_tax = is_total and any(
                normalize_text(kw) in normalize_text(row_all_text)
                for kw in _TAX_KWS
            )

            # 금액 계산
            amount = parse_amount(amount_raw)
            # 수량이 0이면 0으로 유지 (None일 때만 기본값 1.0)
            # 수량=0, 단가=실제단가, 금액=0 인 행은 원본에서 제외된 항목이므로
            # 1×단가로 재계산하면 원본 총합계와 불일치
            quantity = parse_amount(qty_raw) if qty_raw is not None else 1.0
            unit_price = parse_amount(price_raw) if price_raw is not None else 0.0

            # 금액이 없으면 수량 × 단가 (수량이 0이면 재계산하지 않음)
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
                raw_row_text=row_all_text,
                scenario=scenario,
            )
            items.append(item)

        qf.items = items
        qf.original_total = original_total
        qf.extracted_total = sum(i.amount for i in items if not i.is_sum_row)
        qf.tax_amount = tax_amount
        qf.status = FileStatus.COMPLETED
        return qf

    def _fill_merged_cells(self, file_path: str, sheet_name: str, df: pd.DataFrame) -> pd.DataFrame:
        """병합 셀의 값을 모든 병합 행에 동일하게 전파.
        헤더 탐지/열 매핑 전에 실행해야 병합된 헤더 셀 값이 채워져 열 매핑이 정확해진다."""
        try:
            import openpyxl
            wb = openpyxl.load_workbook(file_path, data_only=True, read_only=False)
            ws = wb[sheet_name]
            for merged_range in ws.merged_cells.ranges:
                top_value = ws.cell(row=merged_range.min_row, column=merged_range.min_col).value
                if top_value is None:
                    continue
                for r in range(merged_range.min_row, merged_range.max_row + 1):
                    for c in range(merged_range.min_col, merged_range.max_col + 1):
                        ri, ci = r - 1, c - 1
                        if ri < len(df) and ci < len(df.columns):
                            df.iat[ri, ci] = top_value
            wb.close()
        except Exception:
            pass
        return df

    def _detect_formula_rows(self, file_path: str, sheet_name: str) -> dict:
        """금액/단가 셀의 수식이 다른 행을 참조하는 행 인덱스(0-based) → 수식 문자열 반환.
        - =I18+I27, =SUM(I5:I14) (다른 행 참조) → 합산 표기 행 → 합산금액
        - =H5*F5 (같은 행의 단가×수량) → 실제 견적 항목 → 유지
        Returns: {row_idx_0based: "I18+I27" | "SUM(I5:I14)"}
        ※ read_only=False로 로드해야 수식 문자열을 정확히 읽을 수 있다
        (read_only=True는 캐시된 값만 읽어 수식 감지가 실패함)"""
        try:
            import openpyxl
            wb = openpyxl.load_workbook(file_path, data_only=False, read_only=False)
            ws = wb[sheet_name]
            check_cols = {
                self.column_map[c] + 1
                for c in ("금액", "단가")
                if c in self.column_map
            }
            rows = {}
            if check_cols:
                for row in ws.iter_rows(min_col=1, max_col=max(check_cols)):
                    for cell in row:
                        if cell.column not in check_cols:
                            continue
                        if cell.data_type == "f" or (
                            isinstance(cell.value, str) and cell.value.startswith("=")
                        ):
                            refs = _REF_RE.findall(str(cell.value))
                            if any(int(r) != cell.row for _, r in refs):
                                formula = str(cell.value).lstrip("=")
                                rows[cell.row - 1] = formula
                            break
            wb.close()
            return rows
        except Exception:
            return {}

    def _detect_subtotal_sum_ranges(self, file_path: str, sheet_name: str) -> list:
        """소계/합계 행의 =SUM(Xa:Xb) 수식에서 합산 범위 추출.
        Returns: [(start_0based, end_0based, subtotal_row_0based), ...]
        이 범위의 행은 해당 소계의 섹션에 속한다.
        예: "구매품 소계" =SUM(I1830:I2149) → (1829, 2148, 소계행_0based)"""
        try:
            import openpyxl
            wb = openpyxl.load_workbook(file_path, data_only=False, read_only=False)
            ws = wb[sheet_name]
            check_cols = {
                self.column_map[c] + 1
                for c in ("금액", "단가")
                if c in self.column_map
            }
            ranges = []
            if check_cols:
                for row in ws.iter_rows(min_col=1, max_col=max(check_cols)):
                    for cell in row:
                        if cell.column not in check_cols:
                            continue
                        val = cell.value
                        if isinstance(val, str) and val.startswith("="):
                            m = _SUM_RANGE_RE.match(val.strip())
                            if m:
                                start_row = int(m.group(2))
                                end_row = int(m.group(4))
                                ranges.append((start_row - 1, end_row - 1, cell.row - 1))
                                break  # SUM 수식 발견 → 이 행 처리 완료
                        # 수식 없으면 다음 check_col 셀 확인 (break 안 함)
            wb.close()
            return ranges
        except Exception:
            return []

    def _detect_color_summary_rows(
        self, file_path: str, sheet_name: str, header_idx: int
    ) -> set:
        """배경색이 다수 데이터 행과 다른 행(섹션 헤더/요약 행) 인덱스(0-based) 반환.
        견적서에서 Unit 요약 행, 섹션 헤더 행은 데이터 행과 배경색이 다르게
        표시되는 경우가 많다. 다수 색(데이터 행 색)과 다른 색을 가진 행을
        요약 행으로 간주해 금액 중복을 방지한다."""
        try:
            import openpyxl
            from collections import Counter
            wb = openpyxl.load_workbook(file_path, data_only=True, read_only=False)
            ws = wb[sheet_name]
            # 각 행의 대표 배경색 수집 (1열 셀 기준, 헤더 다음부터)
            # 데이터 행은 무색(None), 요약/섹션 행만 색이 있는 경우가 많음
            row_colors = {}
            for r in range(header_idx + 2, ws.max_row + 1):  # 1-based
                cell = ws.cell(row=r, column=1)
                fill = cell.fill
                color = None
                if fill and fill.patternType:
                    raw = fill.fgColor.rgb if fill.fgColor else None
                    if raw and raw not in ("00000000", "FFFFFFFF", "0"):
                        color = raw
                row_colors[r] = color  # 무색은 None
            wb.close()
            if not row_colors:
                return set()
            # 다수 색 = 데이터 행 색 (보통 무색 None)
            dominant = Counter(row_colors.values()).most_common(1)[0][0]
            # 다수 색과 다른 행 (0-based) — 색이 다른 행만 후보
            return {r - 1 for r, c in row_colors.items() if c != dominant}
        except Exception:
            return set()

    def _verify_summary_by_sum(
        self, df: pd.DataFrame, header_idx: int, color_rows: set
    ) -> set:
        """아래 여러 행의 합산으로 계산된 값인 행을 요약 행으로 감지.
        (0-based 인덱스 반환)

        색상과 무관하게 적용: 색상 구분이 없는 견적서도 대응.
        다만 거짓 양성(실제 항목이 우연히 아래 행 합과 일치)을 방지하기 위해
        두 가드를 적용한다:
          1) 아래 2개 이상 행의 합과 일치해야 함 (단일 행 일치 제외)
          2) 해당 행이 정상 가격 항목(수량×단가=금액)이면 제외 대상 아님

        검증 로직:
        - 대상 행의 금액(A)을 가져옴 (금액 열 우선, 없으면 단가 열)
        - 아래 행을 순차적으로 누적합산하며, 소계/합계/빈 행은 건너뜀
        - 누적합이 A와 일치(±1원)하고 2개 이상 행을 합산했을 때 요약 행 확정
        - 최대 50행까지 탐색 (과도한 탐색 방지)"""
        amount_col = self.column_map.get("금액")
        price_col = self.column_map.get("단가")
        qty_col = self.column_map.get("수량")
        if amount_col is None and price_col is None:
            return set()

        def _row_amount(r: int) -> float:
            """행의 금액(금액 열 우선, 없으면 단가 열) 반환.
            NaN/0은 유효하지 않아 다음 열로 폴백."""
            if amount_col is not None:
                v = parse_amount(df.iat[r, amount_col])
                if v and not math.isnan(v):
                    return v
            if price_col is not None:
                v = parse_amount(df.iat[r, price_col])
                if v and not math.isnan(v):
                    return v
            return 0.0

        def _is_priced_item(r: int) -> bool:
            """정상 가격 항목인지: 수량×단가=금액이면 실제 견적 항목."""
            if qty_col is None or price_col is None:
                return False
            qty = parse_amount(df.iat[r, qty_col])
            price = parse_amount(df.iat[r, price_col])
            amt = _row_amount(r)
            if not qty or not price or not amt:
                return False
            if math.isnan(qty) or math.isnan(price) or math.isnan(amt):
                return False
            return abs(qty * price - amt) <= 1.0

        # 검증 대상: 모든 데이터 행 (색상 무관)
        # ※ 수식 합산 행은 parse_sheet에서 formula_rows로 먼저 처리됨
        confirmed = {}
        for row_idx in range(header_idx + 1, len(df)):
            # 정상 가격 항목(수량×단가=금액)은 실제 견적 항목 → 제외 대상 아님
            if _is_priced_item(row_idx):
                continue
            target = _row_amount(row_idx)
            if not target or abs(target) < 1:
                continue
            # 아래 행 누적합산 (2개 이상 행 합산 필요)
            running = 0.0
            count = 0
            found = False
            first_sum_row = None
            for r in range(row_idx + 1, min(row_idx + 51, len(df))):
                row_vals = df.iloc[r].tolist()
                if is_blank_row(row_vals):
                    continue
                # 소계/합계 행은 누적에 포함하지 않음 (중복 방지)
                row_text = " ".join(
                    str(v) for v in row_vals if pd.notna(v)
                )
                if is_total_row(row_text):
                    continue
                amt = _row_amount(r)
                if not amt:
                    continue
                if first_sum_row is None:
                    first_sum_row = r
                running += amt
                count += 1
                if count >= 2 and abs(running - target) <= 1.0:
                    found = True
                    break
            if found:
                confirmed[row_idx] = f"SUM(행{first_sum_row + 1}:행{r + 1})"
        return confirmed

    def _compute_section_context(
        self, df: pd.DataFrame, header_idx: int, no_col_idx: Optional[int],
        sum_ranges: Optional[list] = None,
    ) -> tuple:
        """섹션 컨텍스트 계산: 마커 감지 → forward propagation → 소계 백필 → SUM 범위 백필.
        Returns: (section_hint_map, section_marker_rows)"""
        name_col_idx = self.column_map.get("품명")

        def _marker(row) -> str:
            """행의 모든 열을 스캔해 섹션 마커 추출.
            - 품명에 섹션 키워드(가공품/구매품/인건비 등) 포함 → 섹션 헤더 (예: "가공품 소개")
            - 품명에 일반 항목명 → 데이터 행 → 섹션 마커 아님
            - 품명 비어있고 금액 있음 → 데이터 행 → 섹션 마커 아님
            - 품명 비어있고 금액 없음 → 다른 열에서 마커 탐색"""
            # 1) 품명 열 체크
            if name_col_idx is not None:
                nv = row.iloc[name_col_idx] if name_col_idx < len(row) else None
                if pd.notna(nv):
                    ns = str(nv).strip()
                    if ns and ns not in ("-", "--", "—"):
                        ns_clean = ns.replace(" ", "")
                        # Remark 섹션 감지
                        if ns_clean.lower().startswith("[remark]") or ns_clean.lower() == "remark":
                            return ns
                        # 섹션 헤더: "가공품 소개", "구매품 소개" 등
                        if any(sec in ns_clean for sec in _SECTION_NAMES):
                            return ns
                        # 일반 데이터 행 → 섹션 마커 아님
                        return ""
            # 2) 나머지 열 스캔 (품명 열 제외)
            bracket_val = ""
            section_name_val = ""
            subtotal_val = ""
            for col_idx, v in enumerate(row.tolist()):
                if pd.isna(v):
                    continue
                v_str = str(v).replace(" ", "").replace("\n", "")
                if not v_str:
                    continue
                if col_idx == name_col_idx:
                    continue
                # 소계/합계 텍스트 우선 수집 (구매품 소계, 가공품 소계 등)
                if ("소계" in v_str or "합계" in v_str) and not subtotal_val:
                    subtotal_val = v_str
                    continue
                if _is_section_marker(v_str):
                    bm = _BRACKET_RE.match(v_str)
                    if bm and not bracket_val:
                        bracket_val = v_str
                    elif not section_name_val:
                        section_name_val = v_str
                    continue
                bm = _BRACKET_ONLY_RE.match(v_str)
                if bm:
                    if not bracket_val:
                        bracket_val = f"[{bm.group(1)}]"
                elif _is_section_level_hint(v_str):
                    if not section_name_val:
                        section_name_val = v_str
            # 소계/합계 텍스트가 있으면 최우선 (구매품 소계, 가공품 소계 등)
            if subtotal_val:
                if bracket_val:
                    return f"{bracket_val} {subtotal_val}"
                return subtotal_val
            if bracket_val and section_name_val:
                return f"{bracket_val}{section_name_val}"
            if section_name_val:
                return section_name_val
            if bracket_val:
                return bracket_val
            return ""

        # 1단계: 마커 행 감지
        section_hint_map = {}
        section_marker_rows = set()
        subtotal_rows = []
        for row_idx in range(header_idx + 1, len(df)):
            row = df.iloc[row_idx]
            if is_blank_row(row.tolist()):
                continue
            hint = _marker(row)
            if hint:
                section_hint_map[row_idx] = hint
                section_marker_rows.add(row_idx)
                if "소계" in hint:
                    subtotal_rows.append((row_idx, hint))

        # 2단계: forward propagation
        current_hint = ""
        for row_idx in range(header_idx + 1, len(df)):
            if row_idx in section_hint_map:
                hint = section_hint_map[row_idx]
                hint_clean = hint.replace(" ", "")
                if "합계" in hint and _BRACKET_PREFIX_RE.match(hint_clean):
                    current_hint = ""
                elif "소계" not in hint and "합계" not in hint:
                    current_hint = hint
            elif current_hint:
                section_hint_map[row_idx] = current_hint

        # 3단계: 하단 소계 백필
        for st_row, st_hint in subtotal_rows:
            start = header_idx
            for r in range(st_row - 1, header_idx, -1):
                if _marker(df.iloc[r]):
                    start = r
                    break
            for r in range(start + 1, st_row):
                if r not in section_hint_map:
                    section_hint_map[r] = st_hint

        # 4단계: 소계 SUM 범위 백필 (가장 정확한 섹션 경계)
        # 소계 행의 =SUM(Xa:Xb) 수식 범위는 해당 섹션의 정확한 경계.
        # forward propagation이 앞 섹션 마커를 잘못 전파한 경우를 교정.
        # 예: "구매품 소계" =SUM(I1830:I2149) → 1830~2149행은 구매품 섹션
        if sum_ranges:
            for start, end, subtotal_row in sum_ranges:
                hint = section_hint_map.get(subtotal_row, "")
                if hint:
                    for r in range(start, min(end + 1, len(df))):
                        if r > header_idx:
                            section_hint_map[r] = hint

        return section_hint_map, section_marker_rows

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
