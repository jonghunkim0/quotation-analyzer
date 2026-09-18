"""
analysis/aggregator.py - 비용 집계 및 계산 로직
"""
from typing import Optional
from models.data_models import QuotationItem, Scenario
from config import (
    COST_CATEGORIES,
    COST_GROUPS,
    DEFAULT_STACK_ORDER,
)
from utils.helpers import safe_divide


class Aggregator:
    """
    비교안별 비용 집계.
    사급품 포함/제외 옵션을 반영.
    """

    def __init__(self, supply_option: str = "사급품을 재료비율에 포함"):
        """
        supply_option:
          - "사급품을 재료비율에 포함"
          - "사급품을 재료비율에서 제외"
          - "사급품을 총원가에 포함"
          - "사급품을 총원가에서 제외"
          - "사급품을 금액 없이 참고 항목으로만 표시"
        """
        self.supply_option = supply_option

    def aggregate_scenario(
        self,
        name: str,
        items: list,
        file_id: str = "",
    ) -> Scenario:
        """
        비교안의 항목들을 집계하여 Scenario 반환.
        """
        scenario = Scenario(name=name, file_id=file_id, items=items)

        # 분류별 합계
        category_totals = {cat: 0.0 for cat in COST_CATEGORIES}
        for item in items:
            if item.is_tax or item.is_total_row:
                continue
            cat = item.final_category
            if cat not in category_totals:
                cat = "미분류"
            category_totals[cat] += item.amount

        scenario.category_totals = category_totals

        # 그룹 합계
        supply_total = category_totals.get("사급품", 0.0)
        purchase_total = category_totals.get("구매품", 0.0)

        material_cats = COST_GROUPS["재료비"]
        labor_cats = COST_GROUPS["인건비"]

        # 사급품 처리 옵션에 따른 계산
        supply_in_material = self.supply_option in (
            "사급품을 재료비율에 포함",
            "사급품을 총원가에 포함",
        )
        supply_in_total = self.supply_option in (
            "사급품을 재료비율에 포함",
            "사급품을 총원가에 포함",
            "사급품을 재료비율에서 제외",
        )
        # "참고 항목으로만 표시" → 모든 계산에서 제외
        if self.supply_option == "사급품을 금액 없이 참고 항목으로만 표시":
            supply_in_material = False
            supply_in_total = False

        # 재료비 합계 (사급품 포함 여부 반영)
        material_total = sum(
            category_totals[c] for c in material_cats if c != "사급품"
        )
        if supply_in_material:
            material_total += supply_total

        # 인건비 합계
        labor_total = sum(category_totals[c] for c in labor_cats)

        # 경비, 마진
        expense_total = category_totals.get("경비", 0.0)
        margin_total = category_totals.get("마진", 0.0)
        unclassified_total = category_totals.get("미분류", 0.0)

        # 분석 원가 = 재료비 + 인건비 + 경비
        analysis_cost = material_total + labor_total + expense_total

        # 총 견적금액 = 분석 원가 + 마진 (+ 미분류)
        total_amount = analysis_cost + margin_total + unclassified_total

        # 사급품 제외 시 총액에서 차감
        if not supply_in_total and supply_in_material:
            # 재료비율에는 포함되지만 총원가에서 제외
            pass  # total_amount는 항목 합계 기준 유지

        scenario.total_amount = total_amount
        scenario.analysis_cost = analysis_cost
        scenario.material_total = material_total
        scenario.labor_total = labor_total
        scenario.expense_total = expense_total
        scenario.margin_total = margin_total
        scenario.supply_total = supply_total
        scenario.purchase_total = purchase_total

        # 재료비율
        base_total = total_amount if total_amount != 0 else 1.0
        scenario.material_rate = safe_divide(material_total, base_total) * 100

        # 사급품 포함 재료비율 (참고용)
        material_with_supply = material_total + (
            0 if supply_in_material else supply_total
        )
        scenario.material_rate_with_supply = (
            safe_divide(material_with_supply, base_total) * 100
        )

        # 분류별 구성비
        scenario.category_ratios = {
            cat: safe_divide(val, base_total) * 100
            for cat, val in category_totals.items()
        }

        return scenario

    def aggregate_all(
        self,
        scenarios_data: list,
    ) -> list:
        """
        여러 비교안을 일괄 집계.
        scenarios_data: [(name, items, file_id), ...]
        """
        return [
            self.aggregate_scenario(name, items, file_id)
            for name, items, file_id in scenarios_data
        ]

    def compute_deltas(self, scenarios: list) -> list:
        """
        전 비교안 대비 증감액/증감률 계산.
        Returns: [{category, delta_amount, delta_rate}, ...] per adjacent pair
        """
        results = []
        for i in range(1, len(scenarios)):
            prev = scenarios[i - 1]
            curr = scenarios[i]
            pair_deltas = []
            for cat in COST_CATEGORIES:
                prev_val = prev.category_totals.get(cat, 0.0)
                curr_val = curr.category_totals.get(cat, 0.0)
                delta = curr_val - prev_val
                rate = safe_divide(delta, abs(prev_val)) * 100 if prev_val != 0 else 0.0
                pair_deltas.append({
                    "category": cat,
                    "from": prev.name,
                    "to": curr.name,
                    "delta_amount": delta,
                    "delta_rate": rate,
                })
            results.append(pair_deltas)
        return results
