"""
analysis/scenario_manager.py - 비교안 관리 로직
"""
from typing import Optional
from models.data_models import QuotationFile, Scenario
from utils.helpers import generate_id
from config import DEFAULT_SCENARIOS


class ScenarioManager:
    """
    비교안(견적가, 구매 목표가, 개발 검토가 등) 관리.
    - 추가, 삭제, 복제, 이름 변경
    - 파일 → 비교안 매핑
    - 항목 복사 (파일 데이터를 다른 비교안으로 복제)
    """

    def __init__(self):
        self.scenarios: list = []  # Scenario 목록
        self._order: list = []     # 비교안 이름 순서

    def init_default(self):
        """기본 비교안 초기화 (실제 Scenario 객체 생성)"""
        self.scenarios = [Scenario(name=n) for n in DEFAULT_SCENARIOS]
        self._order = list(DEFAULT_SCENARIOS)

    def add_scenario(self, name: str, file_id: str = "") -> Scenario:
        """비교안 추가"""
        existing = self.get_scenario(name)
        if existing:
            return existing
        scenario = Scenario(name=name, file_id=file_id)
        self.scenarios.append(scenario)
        self._order.append(name)
        return scenario

    def remove_scenario(self, name: str) -> bool:
        """비교안 삭제"""
        if name not in self._order:
            return False
        self.scenarios = [s for s in self.scenarios if s.name != name]
        self._order.remove(name)
        return True

    def rename_scenario(self, old_name: str, new_name: str) -> bool:
        """비교안 이름 변경"""
        if old_name not in self._order or new_name in self._order:
            return False
        for s in self.scenarios:
            if s.name == old_name:
                s.name = new_name
                for item in s.items:
                    item.scenario = new_name
        self._order[self._order.index(old_name)] = new_name
        return True

    def duplicate_scenario(self, name: str, new_name: str) -> Optional[Scenario]:
        """비교안 복제 (항목 포함)"""
        src = self.get_scenario(name)
        if not src:
            return None
        new_scenario = Scenario(
            name=new_name,
            file_id=src.file_id,
        )
        # 항목 복사
        from models.data_models import QuotationItem
        new_items = []
        for item in src.items:
            new_item = QuotationItem(
                item_id=generate_id("item_"),
                source_file=item.source_file,
                source_sheet=item.source_sheet,
                source_row=item.source_row,
                name=item.name,
                spec=item.spec,
                quantity=item.quantity,
                unit_price=item.unit_price,
                amount=item.amount,
                remark=item.remark,
                category_hint=item.category_hint,
                vendor=item.vendor,
                auto_category=item.auto_category,
                confidence=item.confidence,
                keywords=list(item.keywords),
                reason=item.reason,
                final_category=item.final_category,
                scenario=new_name,
            )
            new_items.append(new_item)
        new_scenario.items = new_items
        self.scenarios.append(new_scenario)
        self._order.append(new_name)
        return new_scenario

    def reorder(self, new_order: list):
        """비교안 순서 변경"""
        valid = [n for n in new_order if n in self._order]
        # 누락된 항목은 뒤에 추가
        for n in self._order:
            if n not in valid:
                valid.append(n)
        self._order = valid

    def get_order(self) -> list:
        """비교안 순서 반환"""
        return list(self._order)

    def get_scenario(self, name: str) -> Optional[Scenario]:
        """이름으로 비교안 조회"""
        for s in self.scenarios:
            if s.name == name:
                return s
        return None

    def assign_file(self, scenario_name: str, qf: QuotationFile):
        """파일의 항목을 비교안에 할당"""
        scenario = self.get_scenario(scenario_name)
        if not scenario:
            self.add_scenario(scenario_name)
            scenario = self.get_scenario(scenario_name)
        scenario.file_id = qf.file_id
        # 항목의 scenario 필드 갱신
        for item in qf.items:
            item.scenario = scenario_name
        scenario.items = list(qf.items)

    def copy_items_to_scenario(
        self, source_scenario: str, target_scenario: str
    ) -> int:
        """
        한 비교안의 항목을 다른 비교안으로 복사.
        Returns: 복사된 항목 수
        """
        src = self.get_scenario(source_scenario)
        tgt = self.get_scenario(target_scenario)
        if not src or not tgt:
            return 0

        from models.data_models import QuotationItem
        count = 0
        for item in src.items:
            new_item = QuotationItem(
                item_id=generate_id("item_"),
                source_file=item.source_file,
                source_sheet=item.source_sheet,
                source_row=item.source_row,
                name=item.name,
                spec=item.spec,
                quantity=item.quantity,
                unit_price=item.unit_price,
                amount=item.amount,
                remark=item.remark,
                category_hint=item.category_hint,
                vendor=item.vendor,
                auto_category=item.auto_category,
                confidence=item.confidence,
                keywords=list(item.keywords),
                reason=item.reason,
                final_category=item.final_category,
                scenario=target_scenario,
            )
            tgt.items.append(new_item)
            count += 1
        return count
