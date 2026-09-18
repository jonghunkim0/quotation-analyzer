"""
classification/auto_classifier.py - 자동 분류 로직
"""
import re
from typing import Optional
from models.data_models import QuotationItem
from utils.helpers import normalize_text
from config import COST_CATEGORIES


# ─── 분류 키워드 규칙 ─────────────────────────────────────────
# 각 분류에 대한 키워드 목록 (우선순위: 사급품/구매품 > 기타)
CLASSIFICATION_RULES = {
    "사급품": [
        "사급품", "사급", "고객사 지급", "고객 지급", "지급자재",
        "고객 제공", "무상 지급", "customer supply", "customer supplied",
        "consigned", "free issue", "고객부품", "고객제공",
    ],
    "구매품": [
        "구매품", "구매 part", "구매파트", "외주 구매", "상용품",
        "표준 구매", "vendor item", "commercial part", "buy part",
        "purchased item", "외부 조달", "구매품",
    ],
    "기구 재료비": [
        "프레임", "플레이트", "브라켓", "가공품", "알루미늄", "프로파일",
        "lm가이드", "lm 가이드", "베어링", "볼스크류", "볼 스크류",
        "실린더", "벨트", "풀리", "볼트", "너트", "기계 제작",
        "스페이서", "샤프트", "축", "기어", "커플링", "스프링",
        "플랜지", "지지대", "베이스", "커버", "하우징", "케이스",
        "스틸", "강판", "알루미늄재", "구리", "브라켓재",
    ],
    "전장·제어 재료비": [
        "plc", "hmi", "센서", "모터", "서보", "인버터", "케이블",
        "차단기", "릴레이", "스위치", "터미널", "커넥터", "판넬",
        "전장품", "제어 부품", "전원공급기", "psu", "컨택터",
        "마그네틱", "피더", "브레이커", "조명", "램프", "버튼",
        "라미네이트", "전선", "코일", "트랜스", "정류기",
    ],
    "기구설계 인건비": [
        "기구설계", "기계설계", "구조설계", "cad", "3d 설계", "2d 도면",
        "상세설계", "도면 작성", "기구 설계", "기계 설계", "설계 인건",
    ],
    "제어설계 인건비": [
        "제어설계", "plc 프로그램", "hmi 프로그램", "소프트웨어 설계",
        "전장설계", "회로설계", "제어 로직", "프로그램 개발",
        "제어 설계", "sw 설계", "프로그래밍",
    ],
    "조립 인건비": [
        "조립", "기계조립", "기구조립", "장비조립", "제작 인건비",
        "조립 공수", "조립 인건", "설치 인건",
    ],
    "셋업 인건비(기구)": [
        "기구 셋업", "기계 셋업", "기구 조정", "얼라인", "정밀 조정",
        "기구 튜닝", "레벨링", "기구 세팅", "정렬",
    ],
    "셋업 인건비(제어)": [
        "프로그램 셋업", "제어 셋업", "시운전", "디버깅", "제어 튜닝",
        "plc 셋업", "hmi 셋업", "제어 세팅", "동작 테스트",
    ],
    "셋업 인건비(전장)": [
        "현장 배선", "전장 셋업", "판넬 설치", "판넬 결선",
        "케이블 포설", "입출력 확인", "전장 공사", "배선", "결선",
    ],
    "경비": [
        "운송비", "출장비", "숙박비", "교통비", "포장비", "안전관리비",
        "일반관리비", "보험료", "설치 경비", "현장 경비", "배송비",
        "운반비", "관리비", "경비",
    ],
    "마진": [
        "마진", "이윤", "profit", "margin", "영업이익", "이익률",
        "이익", "수익",
    ],
}

# 우선순위: 사급품/구매품이 명시되면 해당 분류 우선
PRIORITY_CATEGORIES = ["사급품", "구매품"]


class AutoClassifier:
    """
    자동 분류기.
    품명, 사양, 비고, 구분, 주변 행 정보를 종합해 분류.
    """

    def __init__(self, user_rules: Optional[dict] = None):
        """
        user_rules: {keyword: category} 사용자 정의 규칙
        """
        self.user_rules = user_rules or {}

    def classify(self, item: QuotationItem) -> tuple:
        """
        항목을 분류.
        Returns: (category, confidence, keywords, reason)
        """
        # 분석 대상 텍스트
        texts = [
            item.name,
            item.spec,
            item.remark,
            item.category_hint,
        ]
        combined = " ".join(t for t in texts if t)
        norm_combined = normalize_text(combined)

        if not norm_combined:
            return ("미분류", 0.0, [], "품명, 사양, 비고가 모두 비어 있습니다.")

        # 1) 사용자 규칙 우선 적용
        user_result = self._match_user_rules(norm_combined)
        if user_result:
            return user_result

        # 2) 우선순위 분류 (사급품/구매품)
        for priority_cat in PRIORITY_CATEGORIES:
            keywords = CLASSIFICATION_RULES.get(priority_cat, [])
            matched = [kw for kw in keywords if normalize_text(kw) in norm_combined]
            if matched:
                confidence = min(95.0, 80.0 + len(matched) * 5.0)
                reason = f"'{', '.join(matched)}' 키워드로 {priority_cat}으로 분류"
                return (priority_cat, confidence, matched, reason)

        # 3) 일반 분류 매칭
        best_category = "미분류"
        best_score = 0
        best_keywords = []
        best_reason = ""

        for category in COST_CATEGORIES:
            if category == "미분류":
                continue
            keywords = CLASSIFICATION_RULES.get(category, [])
            matched = [kw for kw in keywords if normalize_text(kw) in norm_combined]
            if matched:
                # 매칭 키워드 수에 따라 점수
                score = len(matched) * 10.0
                # 품명에 직접 매칭되면 보너스
                norm_name = normalize_text(item.name)
                if any(normalize_text(kw) in norm_name for kw in matched):
                    score += 15.0
                # 구분 열에 매칭되면 보너스
                norm_hint = normalize_text(item.category_hint)
                if any(normalize_text(kw) in norm_hint for kw in matched):
                    score += 10.0

                if score > best_score:
                    best_score = score
                    best_category = category
                    best_keywords = matched
                    best_reason = f"'{', '.join(matched)}' 키워드로 {category}으로 분류"

        # 4) 신뢰도 계산
        # 기준:
        #   90%+ : 명확한 분류 키워드 존재 (품명에 직접 매칭)
        #   70~89%: 여러 정보가 분류를 지지
        #   50~69%: 일부 정보만 지지
        #   <50% : 미분류 또는 사용자 확인 필요
        if best_category == "미분류":
            confidence = min(40.0, best_score)
            best_reason = "분류 근거가 부족합니다. 사용자 확인이 필요합니다."
        else:
            norm_name = normalize_text(item.name)
            name_match = any(
                normalize_text(kw) in norm_name for kw in best_keywords
            )
            n_kw = len(best_keywords)

            if name_match and n_kw >= 1:
                # 품명에 명확한 키워드 → 90%+
                confidence = min(95.0, 90.0 + n_kw * 2.0)
            elif n_kw >= 2:
                # 여러 키워드 지지 → 70~89%
                confidence = min(89.0, 75.0 + n_kw * 3.0)
            elif n_kw == 1:
                # 단일 키워드 (품명 아님) → 70~89%
                confidence = 75.0
            else:
                confidence = 55.0

            # 여러 분류에 동시에 해당하면 신뢰도 감소
            multi_match = self._check_multi_match(norm_combined)
            if multi_match:
                confidence = max(50.0, confidence - 15.0)
                best_reason += f" (참고: {', '.join(multi_match)}에도 해당)"

        return (best_category, confidence, best_keywords, best_reason)

    def _match_user_rules(self, norm_text: str) -> Optional[tuple]:
        """사용자 정의 규칙 매칭"""
        for keyword, category in self.user_rules.items():
            if normalize_text(keyword) in norm_text:
                return (category, 95.0, [keyword], f"사용자 규칙 '{keyword}' 적용")
        return None

    def _check_multi_match(self, norm_text: str) -> list:
        """여러 분류에 동시에 해당하는지 확인"""
        matches = []
        for category in COST_CATEGORIES:
            if category == "미분류":
                continue
            keywords = CLASSIFICATION_RULES.get(category, [])
            if any(normalize_text(kw) in norm_text for kw in keywords):
                matches.append(category)
        return matches if len(matches) > 1 else []

    def classify_all(self, items: list) -> list:
        """모든 항목을 일괄 분류"""
        for item in items:
            category, confidence, keywords, reason = self.classify(item)
            item.auto_category = category
            item.confidence = confidence
            item.keywords = keywords
            item.reason = reason
            # 최종 분류는 자동 분류 결과로 초기화
            item.final_category = category
        return items
