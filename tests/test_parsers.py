"""
tests/test_parsers.py - 파서 단위 테스트
"""
import os
import sys
import tempfile
from pathlib import Path

import pandas as pd

sys.path.insert(0, str(Path(__file__).parent.parent))

from quotation_analyzer.parsers.excel_parser import ExcelParser
from quotation_analyzer.utils.helpers import parse_amount, format_amount, auto_detect_unit


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


def test_formula_row_excluded():
    """다른 행을 참조하는 합산 수식 행(=I6+I10)은 제외,
    같은 행의 =단가*수량 수식 행(=H5*F5)은 실제 항목으로 유지"""
    import openpyxl
    tmp_path = tempfile.mktemp(suffix=".xlsx")
    try:
        wb = openpyxl.Workbook()
        ws = wb.active
        ws.title = "세부"
        ws.append(["구분", "No", "품 명", "규격", "Maker", "수량", "단위", "단가", "금액", "비고"])
        # 2행: 부분 헤더 행 — 금액이 아래 두 소계를 합산하는 수식 (다른 행 참조 → 제외)
        ws.append(["1. 공금부: 전구, 분략막 동등로안절체(전구 2개소)", None, None, None, None, 1.5, None, 3978940, "=I7+I11", None])
        ws.append([None, "1", "SWITCH", "KDXSMD21R", "KG AUTO", 2, "EA", 3990, 7980, None])
        ws.append([None, "2", "PRESSURE SWITCH", "ISE10-M5-A-GR", "SMC", 2, "EA", 71600, 143200, None])
        # 5행: 금액이 같은 행의 단가×수량 수식 (같은 행 참조 → 유지)
        ws.append([None, "3", "SENSOR", "X1", "OMRON", 2, "EA", 50000, "=H5*F5", None])
        ws.append([None, None, None, None, None, None, None, None, None, None])
        ws.append([None, "구매품 소계", None, None, None, None, None, None, 2001540, None])
        ws.append([None, "1)", "PUSH PLATE 01", "AL6061", None, 2, "EA", 179500, 359000, None])
        ws.append([None, "2)", "PUSH PLATE 02", "AL6061", None, 2, "EA", 179500, 359000, None])
        ws.append([None, None, None, None, None, None, None, None, None, None])
        ws.append([None, "가공품 소계", None, None, None, None, None, None, 1777400, None])
        wb.save(tmp_path)

        parser = ExcelParser()
        qf = parser.parse_sheet(tmp_path, "세부", "test.xlsx")
        assert qf.status.value == "완료"
        names = [i.name for i in qf.items]
        # 다른 행 참조 합산 수식 행(부분 헤더)은 합산금액 항목으로 포함 (원가분석 제외)
        sum_items = [i for i in qf.items if i.is_sum_row]
        assert len(sum_items) == 1, f"합산 행이 1개여야 함: {[(i.name, i.sum_formula) for i in qf.items]}"
        assert sum_items[0].final_category == "합산금액"
        assert sum_items[0].sum_formula == "I7+I11", f"합산 수식 오류: {sum_items[0].sum_formula}"
        # 같은 행 =단가*수량 수식 행은 유지
        assert "SENSOR" in names, f"같은 행 수식 항목이 제외됨: {names}"
        # 실제 항목은 포함
        assert "SWITCH" in names
        assert "PUSH PLATE 01" in names
        # 소계 컨텍스트 전파 확인: PUSH PLATE → 기구 가공품
        from quotation_analyzer.classification.auto_classifier import AutoClassifier
        clf = AutoClassifier()
        for item in qf.items:
            if item.name == "PUSH PLATE 01":
                cat, conf, kws, reason = clf.classify(item)
                assert cat == "기구 가공품", f"PUSH PLATE 01 → {cat} (hint={item.category_hint})"
    finally:
        try:
            os.unlink(tmp_path)
        except OSError:
            pass


if __name__ == "__main__":
    test_parse_amount()
    test_format_amount()
    test_auto_detect_unit()
    test_excel_parser()
    test_formula_row_excluded()
    print("✅ parser tests passed")
