"""
classification/auto_classifier.py - 자동 분류 로직
"""
import re
from typing import Optional
from quotation_analyzer.models.data_models import QuotationItem
from quotation_analyzer.utils.helpers import normalize_text
from quotation_analyzer.config import COST_CATEGORIES, COST_GROUPS

# 인건비 그룹 카테고리 (인건비 섹션에서 매칭 대상)
LABOR_GROUP_CATS = set(COST_GROUPS.get("인건비", []))

# 카테고리 → 비용 그룹 매핑 (비용 성격 섹션 게이트용)
_CAT_GROUP = {}
for _g, _cats in COST_GROUPS.items():
    for _c in _cats:
        _CAT_GROUP[_c] = _g


def _cost_type(hint: str):
    """섹션 힌트에서 비용 성격(인건비/경비/재료비) 판별"""
    if not hint:
        return None
    if "경비" in hint:
        return "경비"
    if "인건" in hint:
        return "인건비"
    if any(k in hint for k in ("자재", "재료", "자체비", "구매품", "가공품", "사급품")):
        return "재료비"
    return None


def _family_type(hint: str):
    """섹션 힌트에서 계열(기구/전장·제어) 판별"""
    if not hint:
        return None
    if "기구" in hint or "기계" in hint:
        return "기구"
    if "전장" in hint or "제어" in hint or "전기" in hint:
        return "전장/제어"
    return None


# ─── 분류 키워드 규칙 (16개 분류) ─────────────────────────────
CLASSIFICATION_RULES = {
    "사급품": [
        "사급품", "사급", "고객사 지급", "고객 지급", "지급자재",
        "고객 제공", "무상 지급", "customer supply", "customer supplied",
        "consigned", "free issue", "고객부품", "고객제공",
    ],
    "기구 구매품": [
        "구매품", "구매 part", "구매파트", "외주 구매", "상용품",
        "표준 구매", "vendor item", "commercial part", "buy part",
        "purchased item", "외부 조달",
        # 기계 표준 구매 부품
        "모터", "서보", "실린더", "로봇", "lm가이드", "lm 가이드",
        "볼스크류", "볼 스크류", "베어링", "기어", "커플링",
        "벨트", "풀리", "스프링",
        "볼트", "너트", "샤프트", "축", "플랜지", "스페이서",
    ],
    "기구 가공품": [
        "프레임", "플레이트", "플라이트", "플레이트재", "브라켓", "브래킷",
        "블라켓", "블랙켓", "가공품", "알루미늄", "프로파일",
        "기계 제작", "스틸", "강판", "알루미늄재", "구리", "브라켓재",
        "지지대", "베이스", "커버", "하우징", "케이스",
        # 약자
        "plt", "blk", "bkt", "plate", "bracket",
    ],
    "제어 구매품": [
        "plc", "hmi", "센서", "인버터", "차단기", "릴레이", "스위치",
        "터미널", "커넥터", "전원공급기", "psu", "컨택터",
        "마그네틱", "피더", "브레이커", "조명", "램프", "버튼",
        "코일", "트랜스", "제어 부품",
    ],
    "전장 가공품": [
        "제어 가공", "컨트롤 박스", "제어 박스",
        "전장 가공", "전장부 가공", "판넬 가공",
        "케이블", "전선", "전장품", "라미네이트", "정류기",
        "판넬",
    ],
    "전장 구매품": [
        "전장 구매", "전장품 구매", "케이블 구매",
    ],
    "인건비-기구 설계": [
        "기구설계", "기계설계", "구조설계", "cad", "3d 설계", "2d 도면",
        "상세설계", "도면 작성", "기구 설계", "기계 설계", "설계 인건",
    ],
    "인건비-전장 설계": [
        "전장설계", "회로설계",
    ],
    "인건비-제어 설계": [
        "제어설계", "제어 설계",
        "plc 프로그램", "hmi 프로그램", "소프트웨어 설계",
        "제어 로직", "프로그램 개발", "sw 설계", "프로그래밍",
        "plc", "hmi",
    ],
    "인건비-기구 조립": [
        "기구조립", "기계조립", "기구 조립",
    ],
    "인건비-전장/제어 조립": [
        "조립", "장비조립", "전장 조립", "제어 조립",
        "제작 인건비", "조립 공수", "조립 인건", "설치 인건",
    ],
    "인건비-기구 셋업": [
        "기구 셋업", "기계 셋업", "기구 조정", "얼라인", "정밀 조정",
        "기구 튜닝", "레벨링", "기구 세팅", "정렬", "셋업기구엔지니어",
    ],
    "인건비-전장/제어 셋업": [
        "프로그램 셋업", "제어 셋업", "시운전", "디버깅", "제어 튜닝",
        "plc 셋업", "hmi 셋업", "제어 세팅", "동작 테스트", "셋업제어엔지니어",
        "현장 배선", "전장 셋업", "판넬 설치", "판넬 결선",
        "케이블 포설", "입출력 확인", "전장 공사", "배선", "결선", "셋업전장엔지니어",
    ],
    "인건비-기구 양산대응": [
        "양산 기구", "양산대응 기구", "양산 인건 기구",
    ],
    "인건비-전장/제어 양산대응": [
        "양산", "양산대응", "양산 대응", "양산인건", "양산 인건",
        "양산체계", "양산대기", "양산사원", "양산지원",
        "양산 전장", "양산 제어",
    ],
    "인건비-특수제어": [
        "pmac", "umac", "모션", "특수 제어", "특수제어",
        "제어 인건", "인건비-특수제어", "제어",
    ],
    "경비-포장": [
        "포장", "포장비", "패키징", "packaging",
    ],
    "경비-기타": [
        "기타", "기타항목", "기타 비용", "물류", "물류비", "물류 비용",
    ],
    "경비-숙박/교통/항공": [
        "운송비", "출장비", "숙박비", "교통비", "안전관리비",
        "일반관리비", "보험료", "설치 경비", "현장 경비", "배송비",
        "운반비", "관리비", "이동", "국내이동", "항공",
        "출입국", "교훈", "교육", "체류비", "교통", "숙박",
    ],
    "마진": [
        "마진", "이윤", "profit", "margin", "영업이익", "이익률",
        "이익", "수익",
    ],
}

# 우선순위: 사급품이 명시되면 최우선
PRIORITY_CATEGORIES = ["사급품"]

# 규칙 1: 항목 내용에 명시된 분류 정보 → 최우선
EXPLICIT_CLASSIFICATION = {
    "사급품": ["사급품", "사급"],
    "기구 구매품": ["구매품"],
    "기구 가공품": ["가공품"],
}

# 규칙 2: 섹션 헤더 → 섹션 내 항목 통일 분류
SECTION_CLASSIFICATION = {
    "기구 구매품": ["구매품"],
    "기구 가공품": ["가공품"],
    "제어 구매품": ["제어 구매", "제어구매품", "제어 구매품"],
    "전장 구매품": ["전장 구매", "전장구매품", "전장 구매품"],
    "전장 가공품": ["전장/제어", "전장제어", "전장·제어", "전장 제어", "전장 재료", "전장재료"],
}

# 규칙 2-1: 섹션 힌트에 전장/제어 계열이 있으면 기구 구매품 우선 매칭 건너뜀
# (원본 파일의 구분 열에 "전장/제어"로 명시된 섹션 내 항목은 전장/제어 계열로 분류)
ELEC_SECTION_KWS = ["전장", "제어", "전기", "electrical", "control", "wiring", "cable"]

# 규칙 2 (2축 결정): 전장/제어 섹션에서 기구 계열로 매칭된 분류 → 전장/제어 대응 분류 재조정
# 계열(전장/제어) × 성격(재료비/구매품/인건비) 조합에 따라 최종 분류 방향 결정
ELEC_FAMILY_REMAP = {
    "기구 구매품": "전장 구매품",
    "기구 가공품": "전장 가공품",
    "인건비-기구 설계": "인건비-전장 설계",
    "인건비-기구 조립": "인건비-전장/제어 조립",
    "인건비-기구 셋업": "인건비-전장/제어 셋업",
    "인건비-기구 양산대응": "인건비-전장/제어 양산대응",
}

# 규칙 3: 품명에 플레이트/브라켓 계열이 있으면 구매품 우선 매칭을 건너뜀
# (예: "Z-ROBOT-PLATE-1"의 robot, "SENSOR-BKT-1"의 sensor가 구매품으로 오분류하는 것 방지)
MECH_PART_GUARD_KWS = [
    "플레이트", "플라이트", "플레이트재", "브라켓", "브래킷", "블라켓", "블랙켓",
    "plt", "blk", "bkt", "plate", "bracket",
]


def _match_kw(kw: str, norm_text: str) -> bool:
    """키워드 매칭. 짧은 영문 약자(plt/blk/bkt 등)는 단어 경계로 매칭해 오탐 방지.
    품명 표기 관례상 _ 와 - 도 단어 경계로 취급 (예: ROBOT_BASE_PLATE → plate 매칭)."""
    nkw = normalize_text(kw)
    if not nkw:
        return False
    if nkw.isascii() and len(nkw) <= 5:
        return re.search(
            rf"(?<![a-z0-9]){re.escape(nkw)}(?![a-z0-9])", norm_text
        ) is not None
    return nkw in norm_text


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
        # 분석 대상 텍스트 — 원본 행에 기록된 모든 내용 참고 (skip 없음)
        # raw_row_text: 행 전체 셀 텍스트 (매핑되지 않은 열 포함)
        # name/spec/remark/category_hint: 핵심 필드 (보너스 점수용)
        texts = [
            item.name,
            item.spec,
            item.remark,
            item.category_hint,
            item.raw_row_text,  # 원본 행 전체 — 모든 셀 내용 포함
        ]
        combined = " ".join(t for t in texts if t)
        norm_combined = normalize_text(combined)

        if not norm_combined:
            return ("미분류", 0.0, [], "품명, 사양, 비고가 모두 비어 있습니다.")

        # 1) 사용자 규칙 우선 적용
        user_result = self._match_user_rules(norm_combined)
        if user_result:
            return user_result

        # 1-1) 규칙 1: 항목 내용에 명시된 분류 정보(사급/구매품/가공품) → 최우선
        #      단, "구매품"이 명시되어도 섹션이 전장/제어이면 구매품(전장/제어)으로 분류
        norm_hint = normalize_text(item.category_hint)
        is_elec_section = any(_match_kw(kw, norm_hint) for kw in ELEC_SECTION_KWS) if norm_hint else False

        # 비용 성격(인건비/경비/재료비) 섹션 감지
        # 하위 섹션("인건비 > 경비"의 "경비")이 있으면 하위 우선, 없으면 상위 기준
        if norm_hint and ">" in norm_hint:
            _hint_parts = [p.strip() for p in norm_hint.split(">") if p.strip()]
            _sub_hint = _hint_parts[-1] if _hint_parts else ""
            _top_hint = _hint_parts[0] if _hint_parts else ""
        else:
            _sub_hint = norm_hint
            _top_hint = norm_hint

        section_type = _cost_type(_sub_hint) or _cost_type(_top_hint)
        # 계열(기구/전장·제어) 감지: A열(상위) 우선, 없으면 B열(하위) 기준
        section_family = _family_type(_top_hint) or _family_type(_sub_hint)
        # 인건비 섹션 감지 (하위 섹션이 인건비 계열일 때만)
        is_labor_section = (section_type == "인건비")

        # 1-1b) 품명 계열 고정: 품명에 "기구"/"전장"/"제어"가 명시되면 계열 고정
        #       규격/비고의 "전장공임(부)" 같은 섹션 레벨 라벨이 품명의 계열을
        #       덮어쓰지 못하게 함 (병합 셀 전파로 모든 인건비 행에 전파됨)
        norm_name_for_family = normalize_text(item.name or "")
        name_is_mech = "기구" in norm_name_for_family or "기계" in norm_name_for_family
        name_is_elec = ("전장" in norm_name_for_family or "제어" in norm_name_for_family) and not name_is_mech
        if name_is_mech:
            is_elec_section = False  # 품명에 "기구" 명시 → 전장/제어 리맵 차단

        # 1-1a) "사급"이 같은 행 어디에든 명시되면 무조건 사급품 (최고 우선순위)
        #      품명/사양/비고/구분 — 모든 필드에서 확인
        if any(_match_kw(kw, norm_combined) for kw in ["사급", "사급품", "고객부품", "고객제공"]):
            return (
                "사급품",
                98.0,
                ["사급"],
                f"항목에 '사급' 명시 → 사급품으로 분류 (품명: {item.name})",
            )

        for category, kws in EXPLICIT_CLASSIFICATION.items():
            matched = [kw for kw in kws if _match_kw(kw, norm_combined)]
            if matched:
                # 전장/제어 섹션에서 기구 계열 매칭 → 전장/제어 계열로 리맵
                if is_elec_section and category in ELEC_FAMILY_REMAP:
                    category = ELEC_FAMILY_REMAP[category]
                return (
                    category,
                    95.0,
                    matched,
                    f"항목 내용에 '{', '.join(matched)}' 명시 → {category}으로 분류",
                )

        # 1-2) 규칙 2: 섹션 헤더("구매품 소개", "가공품 소개" 등) → 섹션 내 항목 통일 분류
        if norm_hint:
            for category, kws in SECTION_CLASSIFICATION.items():
                if any(_match_kw(kw, norm_hint) for kw in kws):
                    # 전장/제어 섹션에서 기구 계열 매칭 → 전장/제어 계열로 리맵
                    if is_elec_section and category in ELEC_FAMILY_REMAP:
                        category = ELEC_FAMILY_REMAP[category]
                    return (
                        category,
                        85.0,
                        [item.category_hint],
                        f"섹션 '{item.category_hint}' 기준 → {category}으로 통일 분류",
                    )

        # 2) 우선순위 분류 (사급품/구매품)
        #    단, 품명/비고에 인건비 성격이 있으면 사양의 부품 키워드가
        #    오분류하지 않도록 구매품 우선 매칭만 건너뜀 (사급품은 명시적 신호)
        labor_name = normalize_text(f"{item.name or ''} {item.remark or ''} {item.spec or ''}")
        is_labor_item = re.search(
            r"설계|조립|셋업|세팅|인건|시운전|정렬|얼라인|튜닝|레벨링|결선|배선|포설|설치|도면|프로그래밍|개발|테스트|관리비|운송|출장|숙박|배송|포장|보험|경력",
            labor_name,
        ) is not None
        # 품명에 플레이트/브라켓 계열이 있으면 구매품 우선 매칭 건너뜀 (규칙 3)
        norm_name0 = normalize_text(item.name)
        is_mech_part = any(_match_kw(kw, norm_name0) for kw in MECH_PART_GUARD_KWS)
        # 규칙 2-1: 섹션 힌트에 전장/제어 계열이 있으면 기구 구매품 우선 매칭 건너뜀
        for priority_cat in PRIORITY_CATEGORIES:
            if priority_cat == "기구 구매품" and (is_labor_item or is_mech_part or is_elec_section):
                continue
            keywords = CLASSIFICATION_RULES.get(priority_cat, [])
            matched = [kw for kw in keywords if _match_kw(kw, norm_combined)]
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
            # 규칙 2-1: 전장/제어 섹션 내에서는 기구 구매품 점수 대폭 감점
            if category == "기구 구매품" and is_elec_section:
                continue
            # 품명 계열 고정: 품명에 "기구" 있으면 전장/제어 계열 카테고리 건너뜀
            if name_is_mech and ("전장" in category or "제어" in category):
                continue
            # 품명에 "전장/제어" 있으면 기구 계열 카테고리 건너뜀
            if name_is_elec and category.startswith("기구"):
                continue
            keywords = CLASSIFICATION_RULES.get(category, [])
            matched = [kw for kw in keywords if _match_kw(kw, norm_combined)]
            if matched:
                # 매칭 키워드 수에 따라 점수
                score = len(matched) * 10.0
                # 품명에 직접 매칭되면 보너스
                norm_name = normalize_text(item.name)
                if any(_match_kw(kw, norm_name) for kw in matched):
                    score += 15.0
                # 구분 열에 매칭되면 보너스
                if any(_match_kw(kw, norm_hint) for kw in matched):
                    score += 10.0
                # 비용 성격 강제 게이트: B열(성격)이 있으면 해당 성격 그룹만 매칭
                # → 인건비 섹션(B열=인건비)이면 경비 키워드(출입국/교훈 등) 무시
                if section_type and _CAT_GROUP.get(category) not in (section_type, "기타"):
                    continue

                if score > best_score:
                    best_score = score
                    best_category = category
                    best_keywords = matched
                    best_reason = f"'{', '.join(matched)}' 키워드로 {category}으로 분류"

        # 3-0) 규칙 2 (2축 결정): 계열(기구/전장·제어) × 성격(재료비/구매품/인건비)
        #      섹션이 전장/제어인데 기구 계열로 매칭된 경우 → 전장/제어 대응 분류로 재조정
        #      (예: "솔레노이드"가 기구 구매품로 매칭돼도, 전장/제어 섹션이면 전장 구매품)
        if is_elec_section and best_category in ELEC_FAMILY_REMAP:
            remapped = ELEC_FAMILY_REMAP[best_category]
            best_reason = (
                f"계열(전장/제어)×성격 조합 → '{best_category}'을(를) {remapped}으로 재조정 "
                f"(섹션 '{item.category_hint}')"
            )
            best_category = remapped
            best_score = max(best_score, 70.0)

        # 3-1) 섹션 기반 폴백: "양산대응" 섹션 내 항목 → 인건비-전장/제어 양산대응
        if best_category == "미분류" and "양산대응" in norm_hint:
            return (
                "인건비-전장/제어 양산대응",
                45.0,
                [],
                f"키워드 매칭 실패 → 섹션 '{item.category_hint}' 기준 분류",
            )

        # 3-2) 섹션 기반 폴백: "전장/제어" 섹션 내 항목 → 전장 가공품
        if best_category == "미분류" and is_elec_section:
            return (
                "전장 가공품",
                50.0,
                [],
                f"키워드 매칭 실패 → 섹션 '{item.category_hint}'(전장/제어) 기준 분류",
            )

        # 3-3) 섹션 기반 폴백: "인건비" 섹션 내 항목 → 계열(기구/전장·제어) 기준 조립
        #      A열 계열이 기구면 인건비-기구 조립, 전장/제어면 인건비-전장/제어 조립
        if best_category == "미분류" and section_type == "인건비":
            if section_family == "기구":
                return (
                    "인건비-기구 조립",
                    45.0,
                    [],
                    f"키워드 매칭 실패 → 섹션 '{item.category_hint}'(인건비·기구) 기준 분류",
                )
            return (
                "인건비-전장/제어 조립",
                45.0,
                [],
                f"키워드 매칭 실패 → 섹션 '{item.category_hint}'(인건비) 기준 분류",
            )

        # 3-4) 섹션 기반 폴백: "자재비/자체비" 섹션 내 항목 → 계열(기구/전장·제어) 기준 가공품
        #      "자재리스트 참조" 등 자재비 섹션 항목이 키워드에 안 걸려 미분류되는 것 방지
        if best_category == "미분류" and section_type == "재료비":
            if section_family == "전장/제어":
                return (
                    "전장 가공품",
                    45.0,
                    [],
                    f"키워드 매칭 실패 → 섹션 '{item.category_hint}'(자재비·전장/제어) 기준 분류",
                )
            return (
                "기구 가공품",
                45.0,
                [],
                f"키워드 매칭 실패 → 섹션 '{item.category_hint}'(자재비) 기준 분류",
            )

        # 3-5) 섹션 기반 폴백: "경비" 섹션 내 항목 → 경비-기타
        #      물류비 등 구체적 경비 키워드에 안 걸린 경비 항목이 미분류되는 것 방지
        if best_category == "미분류" and section_type == "경비":
            return (
                "경비-기타",
                45.0,
                [],
                f"키워드 매칭 실패 → 섹션 '{item.category_hint}'(경비) 기준 분류",
            )

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
            name_match = any(_match_kw(kw, norm_name) for kw in best_keywords)
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
            if any(_match_kw(kw, norm_text) for kw in keywords):
                matches.append(category)
        return matches if len(matches) > 1 else []

    def classify_all(self, items: list) -> list:
        """모든 항목을 일괄 분류"""
        for item in items:
            if item.is_sum_row:
                continue  # 합산 행은 이미 합산금액으로 분류됨
            category, confidence, keywords, reason = self.classify(item)
            item.auto_category = category
            item.confidence = confidence
            item.keywords = keywords
            item.reason = reason
            # 최종 분류는 자동 분류 결과로 초기화
            item.final_category = category
        # 유사 항목 전파: 미분류 항목을 이미 분류된 항목과 유사도 비교해 전파
        self._propagate_similar(items)
        return items

    @staticmethod
    def _bigrams(s: str) -> set:
        return {s[i:i + 2] for i in range(len(s) - 1)}

    @classmethod
    def _dice(cls, a: str, b: str) -> float:
        A, B = cls._bigrams(a), cls._bigrams(b)
        if not A or not B:
            return 0.0
        inter = len(A & B)
        return (2 * inter) / (len(A) + len(B))

    def _propagate_similar(self, items: list) -> int:
        """미분류 항목을 같은 목록에서 이미 분류된 항목과 문자 2-그램 Dice 유사도로 전파.
        협력사/담당자마다 표현 방식이 달라 키워드로 못 잡은 항목(예: "양산대기 기구" ↔ "양산대응 기구") 대응.
        섹션(hint)이 같은 매칭은 보너스. 임계값 0.6, 신뢰도 70.
        ※ 섹션 힌트가 있는 항목은 전파 대상에서 제외 (섹션 기반 분류가 우선)"""
        count = 0
        classified = [
            i for i in items
            if i.final_category and i.final_category != "미분류" and not i.is_sum_row
        ]
        for it in items:
            if it.is_sum_row:
                continue  # 합산 행은 전파 대상 아님
            if it.final_category != "미분류":
                continue
            # 섹션 힌트가 있으면 유사 항목 전파 대신 섹션 기반 분류를 신뢰
            if it.category_hint:
                continue
            text = normalize_text(f"{it.name} {it.spec or ''}")
            best, best_score = None, 0.0
            for ref in classified:
                ref_text = normalize_text(f"{ref.name} {ref.spec or ''}")
                score = self._dice(text, ref_text)
                if it.category_hint and it.category_hint == ref.category_hint:
                    score += 0.15  # 섹션 동일 보너스
                if score > best_score:
                    best_score, best = score, ref
            if best and best_score >= 0.6:
                it.auto_category = best.final_category
                it.final_category = best.final_category
                it.confidence = 70.0
                it.reason = f"유사 항목 전파: '{best.name}'"
                count += 1
        return count
