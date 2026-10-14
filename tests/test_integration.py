"""
tests/test_integration.py - 전체 파이프라인 통합 테스트

샘플 Excel 파싱 → 자동 분류 → 집계 → 차트 생성까지 검증.
Streamlit 런타임 없이 실행.
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from quotation_analyzer.parsers.excel_parser import ExcelParser
from quotation_analyzer.classification.auto_classifier import AutoClassifier
from quotation_analyzer.analysis.aggregator import Aggregator
from quotation_analyzer.analysis.validator import Validator
from quotation_analyzer.visualization.cost_chart import CostCompositionChart
from quotation_analyzer.config import SAMPLE_DIR


def main():
    sample_dir = SAMPLE_DIR
    assert sample_dir.exists(), "샘플 데이터가 없습니다. data/generate_sample.py 실행"

    files = {
        "견적가": sample_dir / "견적가.xlsx",
        "구매 목표가": sample_dir / "구매목표가.xlsx",
        "개발 검토가": sample_dir / "개발검토가.xlsx",
    }

    parser = ExcelParser()
    classifier = AutoClassifier()
    agg = Aggregator(supply_option="사급품을 재료비율에 포함")
    validator = Validator()

    scenarios = []
    all_items = []
    all_issues = []

    for scen_name, path in files.items():
        sheets = parser.list_sheets(str(path))
        qf = parser.parse_sheet(str(path), sheets[0], path.name, scenario=scen_name)
        assert qf.status.value == "완료", f"{path.name} 파싱 실패: {qf.error_message}"

        # 자동 분류
        classifier.classify_all(qf.items)
        all_items.extend(qf.items)

        # 집계
        scen = agg.aggregate_scenario(scen_name, qf.items, qf.file_id)
        scenarios.append(scen)

        # 검증
        all_issues.extend(validator.validate_file(qf))
        all_issues.extend(validator.validate_scenario(scen))
        all_issues.extend(validator.validate_items(qf.items, scen_name))

        # 미분류 비율 확인
        uncl = scen.category_totals.get("미분류", 0)
        print(f"  [{scen_name}] 총액={scen.total_amount:,.0f} "
              f"재료비율={scen.material_rate:.1f}% 미분류={uncl:,.0f}")

    # 증감 계산
    deltas = agg.compute_deltas(scenarios)
    assert len(deltas) == 2, "증감 구간이 2개여야 함"

    # 차트 생성
    chart = CostCompositionChart(
        scenarios=scenarios,
        unit="백만원",
        decimals=1,
        highlight_scenario="구매 목표가",
    )
    fig = chart.build()
    assert fig is not None, "차트 생성 실패"
    n_traces = len(fig.data)
    print(f"  차트 trace 수: {n_traces}")

    # 차트 합계 = 집계표 합계 일치 검증 (합산금액 제외 — 이중합산 방지)
    for s in scenarios:
        cat_sum = sum(
            v for k, v in s.category_totals.items() if k != "합산금액"
        )
        assert abs(cat_sum - s.total_amount) < 1, (
            f"[{s.name}] 차트 합계({cat_sum:,.0f}) ≠ 총액({s.total_amount:,.0f})"
        )

    # 미분류 항목 확인
    uncl_items = [i for i in all_items if i.final_category == "미분류"]
    print(f"  전체 항목: {len(all_items)}, 미분류: {len(uncl_items)}")

    print("\n✅ 통합 테스트 통과: 파싱→분류→집계→검증→차트 전체 파이프라인 정상")


if __name__ == "__main__":
    main()
