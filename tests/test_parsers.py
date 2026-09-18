"""
tests/test_parsers.py - 파서 단위 테스트
"""
import os
import sys
import tempfile
from pathlib import Path

import pandas as pd

sys.path.insert(0, str(Path(__file__).parent.parent))

from parsers.excel_parser import ExcelParser
from utils.helpers import parse_amount, format_amount, auto_detect_unit


def _make_sample_excel(path: str):
    """샘플 Excel 생성"""
    data = [
        ["설비 견적서", None, None, None, None],
        ["품명", "사양", "수량", "단가", "금액"],
        ["프레임", "SUS304", 2, 1500000, 3000000],
        ["PLC", "FX5U", 1, 2500000, 2500000],
        ["서보모터", "750W", 4, 800000, 3200000],
        ["조립", "인건비", 1, 5000000, 5000000],
        ["마진", None, 1, 0, 2000000],
        ["합계", None, None, None, 15700000],
    ]
    df = pd.DataFrame(data)
    df.to_excel(path, index=False, header=False)


def test_parse_amount():
    assert parse_amount("1,234,567") == 1234567
    assert parse_amount("₩ 100,000") == 100000
    assert parse_amount("(500)") == -500
    assert parse_amount("-1,000") == -1000
    assert parse_amount("1,000.50") == 1000.5
    assert parse_amount(None) == 0.0
    assert parse_amount("") == 0.0


def test_format_amount():
    assert format_amount(100000000, "억원") == "1억"
    assert format_amount(252000000, "억원", 2) == "2.52억"
    assert format_amount(1000000, "백만원") == "1백만원"


def test_auto_detect_unit():
    assert auto_detect_unit(2_000_000_000) == "억원"
    assert auto_detect_unit(50_000_000) == "백만원"
    assert auto_detect_unit(500_000) == "천원"
    assert auto_detect_unit(5000) == "원"


def test_excel_parser():
    tmp_path = tempfile.mktemp(suffix=".xlsx")
    try:
        _make_sample_excel(tmp_path)
        parser = ExcelParser()
        sheets = parser.list_sheets(tmp_path)
        assert len(sheets) >= 1

        qf = parser.parse_sheet(tmp_path, sheets[0], "test.xlsx")
        assert qf.status.value == "완료"
        # 합계 행 제외, 5개 항목 (프레임, PLC, 서보모터, 조립, 마진)
        assert len(qf.items) == 5
        # 원본 총액 감지
        assert qf.original_total == 15700000
        # 추출 합계 (합계 행 제외)
        expected = 3000000 + 2500000 + 3200000 + 5000000 + 2000000
        assert qf.extracted_total == expected
    finally:
        try:
            os.unlink(tmp_path)
        except OSError:
            pass  # Windows 파일 잠금 시 무시


if __name__ == "__main__":
    test_parse_amount()
    test_format_amount()
    test_auto_detect_unit()
    test_excel_parser()
    print("✅ parser tests passed")
