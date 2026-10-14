"""
analysis/validator.py - 검증 로직
"""
from typing import Optional
from quotation_analyzer.models.data_models import QuotationItem, QuotationFile, Scenario, ValidationIssue
from quotation_analyzer.config import (
    COST_CATEGORIES,
    DEFAULT_TOLERANCE_ABS,
    DEFAULT_TOLERANCE_PCT,
)
from quotation_analyzer.utils.helpers import safe_divide


class Validator:
    """
    견적 데이터 검증.
    12가지 검증 항목 수행.
    """

    def __init__(
        self,
        tolerance_abs: float = DEFAULT_TOLERANCE_ABS,
        tolerance_pct: float = DEFAULT_TOLERANCE_PCT,
    ):
        self.tolerance_abs = tolerance_abs
        self.tolerance_pct = tolerance_pct

    def _tolerance(self, total: float) -> float:
        """허용 오차: 1원 또는 총액의 0.01% 중 큰 값"""
        return max(self.tolerance_abs, abs(total) * self.tolerance_pct)

    def validate_file(self, qf: QuotationFile) -> list:
        """파일 단위 검증"""
        issues = []

        # 1. 원본 총액 vs 추출 합계
        if qf.original_total > 0:
            diff = abs(qf.original_total - qf.extracted_total)
            tol = self._tolerance(qf.original_total)
            if diff > tol:
                issues.append(ValidationIssue(
                    issue_type="합계 차이",
                    severity="warning",
                    message=(
                        f"원본 총액({qf.original_total:,.0f})과 추출 합계"
                        f"({qf.extracted_total:,.0f})의 차이: {diff:,.0f} "
                        f"(허용 오차: {tol:,.0f})"
                    ),
                ))

        # 7. 음수 금액 확인
        for item in qf.items:
            if item.amount < 0:
                issues.append(ValidationIssue(
                    issue_type="음수 금액",
                    severity="warning",
                    message=f"행 {item.source_row}: '{item.name}' 음수 금액 {item.amount:,.0f}",
                    item_id=item.item_id,
                ))

        # 5. 중복 항목 탐지
        seen = {}
        for item in qf.items:
            key = (item.name, item.amount)
            if key in seen and item.name:
                issues.append(ValidationIssue(
                    issue_type="중복 항목",
                    severity="warning",
                    message=f"'{item.name}' 금액 {item.amount:,.0f} 중복 (행 {seen[key]} / {item.source_row})",
                    item_id=item.item_id,
                ))
            else:
                seen[key] = item.source_row

        return issues

    def validate_scenario(self, scenario: Scenario) -> list:
        """비교안 단위 검증"""
        issues = []

        # 2. 분류별 합계 vs 전체 합계 (합산금액 제외 — 이중합산 방지)
        cat_sum = sum(
            v for k, v in scenario.category_totals.items()
            if k != "합산금액"
        )
        diff = abs(cat_sum - scenario.total_amount)
        tol = self._tolerance(scenario.total_amount)
        if diff > tol:
            issues.append(ValidationIssue(
                issue_type="분류 합계 불일치",
                severity="error",
                message=(
                    f"[{scenario.name}] 분류별 합계({cat_sum:,.0f})와 "
                    f"총액({scenario.total_amount:,.0f}) 불일치: {diff:,.0f}"
                ),
                scenario=scenario.name,
            ))

        # 10. 미분류 금액 확인
        unclassified = scenario.category_totals.get("미분류", 0.0)
        if unclassified > 0 and scenario.total_amount > 0:
            ratio = safe_divide(unclassified, scenario.total_amount) * 100
            if ratio > 5:
                issues.append(ValidationIssue(
                    issue_type="미분류 비율 높음",
                    severity="warning",
                    message=(
                        f"[{scenario.name}] 미분류 {unclassified:,.0f} "
                        f"({ratio:.1f}%) - 분류 검토 필요"
                    ),
                    scenario=scenario.name,
                ))

        return issues

    def validate_items(self, items: list, scenario_name: str = "") -> list:
        """항목 단위 검증"""
        issues = []

        for item in items:
            # 4. 수량 × 단가 vs 기록 금액
            if item.quantity and item.unit_price and item.amount:
                calc = item.quantity * item.unit_price
                diff = abs(calc - item.amount)
                tol = self._tolerance(item.amount)
                if diff > tol:
                    issues.append(ValidationIssue(
                        issue_type="수량×단가 불일치",
                        severity="warning",
                        message=(
                            f"[{scenario_name}] '{item.name}': "
                            f"수량({item.quantity})×단가({item.unit_price:,.0f})="
                            f"{calc:,.0f} ≠ 금액({item.amount:,.0f})"
                        ),
                        scenario=scenario_name,
                        item_id=item.item_id,
                    ))

        return issues

    def validate_all(
        self,
        files: list,
        scenarios: list,
    ) -> list:
        """전체 검증"""
        issues = []
        for qf in files:
            issues.extend(self.validate_file(qf))
        for scenario in scenarios:
            issues.extend(self.validate_scenario(scenario))
            issues.extend(self.validate_items(scenario.items, scenario.name))
        return issues
