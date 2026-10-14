"""
run_analyzer_headless.py - quotation-analyzer headless 자동실행 스크립트

Streamlit UI 없이:
  1. Raw 견적 파일(Excel/PDF) 파싱
  2. 자동 분류 (auto_category)
  3. 최종분류 = 자동분류 (수동 검토 없음)
  4. 내보내기 CSV (최종분류 포함) 생성

사용법:
  python run_analyzer_headless.py <input_file> [output_csv]
"""
import sys
import os
from pathlib import Path

# analyzer 프로젝트 루트를 sys.path에 추가
ANALYZER_ROOT = Path(__file__).parent
sys.path.insert(0, str(ANALYZER_ROOT))

from quotation_analyzer.parsers.excel_parser import ExcelParser
from quotation_analyzer.parsers.pdf_parser import PDFParser
from quotation_analyzer.classification.auto_classifier import AutoClassifier
from quotation_analyzer.export.exporter import Exporter
from quotation_analyzer.models.data_models import QuotationFile


def run(input_file: str, output_csv: str) -> QuotationFile:
    input_path = Path(input_file)
    if not input_path.exists():
        raise FileNotFoundError(f"파일을 찾을 수 없습니다: {input_file}")

    filename = input_path.name
    ext = input_path.suffix.lower()

    # 1) 파싱
    if ext in (".xlsx", ".xls"):
        parser = ExcelParser()
        sheets = parser.list_sheets(str(input_path))
        selected = sheets[0] if sheets else ""
        qf = parser.parse_sheet(str(input_path), selected, filename, "견적가")
        qf.sheets = sheets
    elif ext == ".pdf":
        parser = PDFParser()
        qf = parser.parse(str(input_path), filename, "견적가")
    else:
        raise ValueError(f"지원하지 않는 형식: {ext}")

    if qf.status.value == "오류":
        print(f"[오류] 파싱 실패: {qf.error_message}")
        return qf

    print(f"[파싱] {filename} | 시트={qf.selected_sheet} | 항목 수={len(qf.items)}")

    # 2) 자동 분류
    classifier = AutoClassifier()
    classifier.classify_all(qf.items)

    # 3) 최종분류 = 자동분류 (수동 검토 없음)
    for it in qf.items:
        it.final_category = it.auto_category

    # 4) 내보내기 CSV
    exporter = Exporter(metadata={
        "원본 파일": filename,
        "시트": qf.selected_sheet,
        "항목 수": len(qf.items),
    })
    csv_content = exporter.export_items_csv(qf.items)
    out_path = Path(output_csv)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(csv_content, encoding="utf-8-sig")
    print(f"[내보내기] {out_path} ({len(qf.items)}개 항목)")

    # 분류 요약
    from collections import Counter
    cat_count = Counter(it.final_category for it in qf.items)
    print("\n[최종분류 요약]")
    for cat, cnt in cat_count.most_common():
        print(f"  {cat}: {cnt}")

    return qf


if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("사용법: python run_analyzer_headless.py <input_file> [output_csv]")
        sys.exit(1)
    inp = sys.argv[1]
    out = sys.argv[2] if len(sys.argv) > 2 else str(
        ANALYZER_ROOT / "data" / "output" / "analyzer_export.csv"
    )
    run(inp, out)
