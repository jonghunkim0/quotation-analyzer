"""
tests/test_aggregator.py - 집계 및 검증 로직 테스트
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from models.data_models import QuotationItem
from analysis.aggregator import Aggregator
from analysis.validator import Validator


def _item(name, amount, category):
    it = QuotationItem(
        item_id=f"t_{name}",
        source_file="t.xlsx",
        name=name,
        amount=amount,
        final_category=category,
    )
    return it


def test_basic_aggregation():
    items = [
        _item("프레임", 3_000_000, "기구 가공품"),
        _item("PLC", 2_500_000, "전장 가공품"),
        _item("조립", 5_000_000, "조립 인건비"),
        _item("마진", 2_000_000, "마진"),
    ]
    agg = Aggregator()
    s = agg.aggregate_scenario("견적가", items)

    assert s.material_total == 5_500_000
    assert s.labor_total == 5_000_000
    assert s.margin_total == 2_000_000
    assert s.analysis_cost == 10_500_000
    assert s.total_amount == 12_500_000
    # 재료비율 = 5.5 / 12.5
    assert abs(s.material_rate - 44.0) < 0.1


def test_supply_excluded():
    items = [
        _item("프레임", 3_000_000, "기구 가공품"),
        _item("사급품", 1_000_000, "사급품"),
        _item("조립", 5_000_000, "조립 인건비"),
    ]
    # 사급품 재료비율에서 제외
    agg = Aggregator(supply_option="사급품을 재료비율에서 제외")
    s = agg.aggregate_scenario("견적가", items)
    # 재료비 = 기구 가공품만 (사급품 제외)
    assert s.material_total == 3_000_000


def test_supply_included():
    items = [
        _item("프레임", 3_000_000, "기구 가공품"),
        _item("사급품", 1_000_000, "사급품"),
        _item("조립", 5_000_000, "조립 인건비"),
    ]
    agg = Aggregator(supply_option="사급품을 재료비율에 포함")
    s = agg.aggregate_scenario("견적가", items)
    assert s.material_total == 4_000_000


def test_delta():
    items1 = [_item("프레임", 3_000_000, "기구 가공품")]
    items2 = [_item("프레임", 2_000_000, "기구 가공품")]
    agg = Aggregator()
    s1 = agg.aggregate_scenario("견적가", items1)
    s2 = agg.aggregate_scenario("구매 목표가", items2)
    deltas = agg.compute_deltas([s1, s2])
    assert len(deltas) == 1
    mech = [d for d in deltas[0] if d["category"] == "기구 가공품"][0]
    assert mech["delta_amount"] == -1_000_000
    assert abs(mech["delta_rate"] - (-33.33)) < 0.1


def test_validator_total_mismatch():
    items = [_item("프레임", 3_000_000, "기구 가공품")]
    agg = Aggregator()
    s = agg.aggregate_scenario("견적가", items)
    # 총액을 의도적으로 틀리게
    s.total_amount = 9_999_999
    v = Validator()
    issues = v.validate_scenario(s)
    assert any(i.issue_type == "분류 합계 불일치" for i in issues)


if __name__ == "__main__":
    test_basic_aggregation()
    test_supply_excluded()
    test_supply_included()
    test_delta()
    test_validator_total_mismatch()
    print("✅ aggregator tests passed")
