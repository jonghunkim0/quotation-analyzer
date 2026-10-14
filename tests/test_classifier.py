"""
tests/test_classifier.py - 자동 분류 로직 테스트
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from quotation_analyzer.models.data_models import QuotationItem
from quotation_analyzer.classification.auto_classifier import AutoClassifier


def _item(name, spec="", remark="", hint=""):
    return QuotationItem(
        item_id="test",
        source_file="test.xlsx",
        name=name,
        spec=spec,
        remark=remark,
        category_hint=hint,
        amount=1000000,
    )


def test_mechanical_material():
    clf = AutoClassifier()
    item = _item("프레임", "SUS304")
    cat, conf, kws, reason = clf.classify(item)
    assert cat == "기구 가공품"
    assert conf >= 70


def test_electrical_material():
    """전장 자체 제작 재료: '전선' → 전장 가공품"""
    clf = AutoClassifier()
    item = _item("전선", "VVF 2.5")
    cat, conf, kws, reason = clf.classify(item)
    assert cat == "전장 가공품"


def test_purchased_standard_parts():
    """표준 구매 부품(모터·실린더·로봇 등) → 구매품"""
    clf = AutoClassifier()
    for name in ["서보모터", "실린더", "로봇", "LM가이드", "볼스크류", "PLC", "HMI", "센서"]:
        item = _item(name)
        cat, conf, kws, reason = clf.classify(item)
        assert cat == "기구 구매품", f"{name} → {cat}"


def test_supply_priority():
    """사급품 우선 규칙: '사급 PLC' → 사급품"""
    clf = AutoClassifier()
    item = _item("사급 PLC", "FX5U")
    cat, conf, kws, reason = clf.classify(item)
    assert cat == "사급품"


def test_purchase_priority():
    """구매품 우선 규칙: '구매품 서보모터' → 구매품"""
    clf = AutoClassifier()
    item = _item("구매품 서보모터", "750W")
    cat, conf, kws, reason = clf.classify(item)
    assert cat == "기구 구매품"


def test_labor():
    clf = AutoClassifier()
    item = _item("조립", "인건비")
    cat, conf, kws, reason = clf.classify(item)
    assert cat == "인건비-전장/제어 조립"


def test_labor_not_stolen_by_part_keyword():
    """인건비 항목의 사양에 부품 키워드가 있어도 구매품으로 오분류되지 않음"""
    clf = AutoClassifier()
    item = _item("제어설계", "PLC/HMI", remark="인건")
    cat, conf, kws, reason = clf.classify(item)
    assert cat == "인건비-제어 설계"


def test_margin():
    clf = AutoClassifier()
    item = _item("마진")
    cat, conf, kws, reason = clf.classify(item)
    assert cat == "마진"


def test_expense():
    clf = AutoClassifier()
    item = _item("운송비")
    cat, conf, kws, reason = clf.classify(item)
    assert cat == "경비-숙박/교통/항공"


def test_unclassified():
    clf = AutoClassifier()
    item = _item("")
    cat, conf, kws, reason = clf.classify(item)
    assert cat == "미분류"
    assert conf < 50


def test_user_rule():
    clf = AutoClassifier(user_rules={"특수부품": "구매품"})
    item = _item("특수부품 A")
    cat, conf, kws, reason = clf.classify(item)
    assert cat == "구매품"
    assert conf >= 90


# ─── 규칙 1: 항목 내 명시적 분류 정보 최우선 ──────────────────
def test_explicit_gongakpum():
    """'가공품' 명시 → 기구 가공품 (최우선)"""
    clf = AutoClassifier()
    item = _item("가공품 베이스", "SUS304")
    cat, conf, kws, reason = clf.classify(item)
    assert cat == "기구 가공품"
    assert conf >= 90


def test_explicit_sageup():
    """'사급' 명시 → 사급품 (최우선)"""
    clf = AutoClassifier()
    item = _item("사급 프레임")
    cat, conf, kws, reason = clf.classify(item)
    assert cat == "사급품"
    assert conf >= 90


# ─── 규칙 2: 섹션 헤더 기반 통일 분류 ─────────────────────────
def test_section_gumapum_intro():
    """구분 열에 '구매품 소개' 섹션 → 구매품으로 통일"""
    clf = AutoClassifier()
    item = _item("서브베이스", "SUS304-T2", hint="구매품 소개")
    cat, conf, kws, reason = clf.classify(item)
    assert cat == "구매품"
    assert conf >= 80


def test_section_gongakpum_intro():
    """구분 열에 '가공품 소개' 섹션 → 기구 가공품로 통일"""
    clf = AutoClassifier()
    item = _item("AZS 프레임", "SUS304", hint="가공품 소개")
    cat, conf, kws, reason = clf.classify(item)
    assert cat == "기구 가공품"
    assert conf >= 80


# ─── 규칙 3: 플레이트/브라켓 약자 → 기구 가공품 ───────────────
def test_plate_bracket_variants():
    """플레이트/브라켓 변형 표기 → 기구 가공품"""
    clf = AutoClassifier()
    for name in ["PLT-BASE", "BLK-SIDE", "플라이트", "블라켓", "블랙켓", "브래킷"]:
        item = _item(name)
        cat, conf, kws, reason = clf.classify(item)
        assert cat == "기구 가공품", f"{name} → {cat}"


def test_plt_no_false_positive():
    """'plt' 약자는 단어 경계 매칭 — 'platform'에는 매칭되지 않음"""
    clf = AutoClassifier()
    item = _item("platform cover")
    cat, conf, kws, reason = clf.classify(item)
    # 'cover'로 기구 가공품가 될 수 있으나 'plt' 오탐은 아님
    assert "plt" not in [k.lower() for k in kws]


# ─── 규칙 3 가드: 품명에 PLATE/BKT 계열이 있으면 구매품 우선 매칭 차단 ──
def test_mech_part_guard_robot_plate():
    """'Z-ROBOT-PLATE-1'의 robot이 구매품으로 오분류하지 않음"""
    clf = AutoClassifier()
    item = _item("Z-ROBOT-PLATE-1")
    cat, conf, kws, reason = clf.classify(item)
    assert cat == "기구 가공품", f"Z-ROBOT-PLATE-1 → {cat}"


def test_mech_part_guard_sensor_bkt():
    """'SENSOR-BKT-1'의 sensor가 구매품으로 오분류하지 않음"""
    clf = AutoClassifier()
    for name in ["SENSOR-BKT-1", "SENSOR_BKT-6", "FIX_BKT", "Y-CABLE-MOVING-BKT-1"]:
        item = _item(name)
        cat, conf, kws, reason = clf.classify(item)
        assert cat == "기구 가공품", f"{name} → {cat}"


def test_mech_part_guard_underscore_boundary():
    """'ROBOT_BASE_PLATE' — _ 경계로 plate 매칭"""
    clf = AutoClassifier()
    item = _item("ROBOT_BASE_PLATE")
    cat, conf, kws, reason = clf.classify(item)
    assert cat == "기구 가공품", f"ROBOT_BASE_PLATE → {cat}"


# ─── 규칙 2: 하단 소계 행 컨텍스트 (파서가 부여한 category_hint) ────────
def test_section_subtotal_gongakpum():
    """'가공품 소계' 컨텍스트 → 기구 가공품 (I19~I65 항목들)"""
    clf = AutoClassifier()
    for name in ["SENSOR_BASE-1", "BLOW-DUCT", "HOOD-SHAFT", "BALL-BOLT-1"]:
        item = _item(name, hint="가공품 소계")
        cat, conf, kws, reason = clf.classify(item)
        assert cat == "기구 가공품", f"{name} → {cat}"


def test_section_subtotal_gumapum():
    """'구매품 소계' 컨텍스트 → 구매품"""
    clf = AutoClassifier()
    item = _item("HI MOUNT", hint="구매품 소계")
    cat, conf, kws, reason = clf.classify(item)
    assert cat == "기구 구매품", f"HI MOUNT → {cat}"


# ─── 셋업엔지니어 / 양산대응 인건비 ────────────────────────────
def test_setup_engineer_categories():
    """'셋업○○엔지니어' → 셋업 인건비(○○)"""
    clf = AutoClassifier()
    cases = [
        ("셋업제어엔지니어(고급)", "셋업 인건비(제어)"),
        ("셋업기구엔지니어(중급)", "셋업 인건비(기구)"),
        ("셋업전장엔지니어(초급)", "셋업 인건비(전장)"),
    ]
    for name, expected in cases:
        item = _item(name)
        cat, conf, kws, reason = clf.classify(item)
        assert cat == expected, f"{name} → {cat}"


def test_mass_production_labor():
    """'양산대응' 품명/섹션 → 양산대응 인건비
    품명에 "기구"가 있으면 기구 계열(품명 계열 고정 원칙)"""
    clf = AutoClassifier()
    cases = [
        ("양산대응엔지니어(고급)", "양산대응", "인건비-전장/제어 양산대응"),
        ("양산대응 기구", "양산대응", "인건비-기구 양산대응"),
        ("양산 대응 인건", "", "인건비-전장/제어 양산대응"),
    ]
    for name, hint, expected in cases:
        item = _item(name, hint=hint)
        cat, conf, kws, reason = clf.classify(item)
        assert cat == expected, f"{name} → {cat} (기대: {expected})"


def test_similarity_propagation():
    """미분류 항목을 이미 분류된 유사 항목과 비교해 전파 (예: "플레트재" ↔ "플레이트재")"""
    clf = AutoClassifier()
    ref = _item("플레이트재 SUS304")   # → 기구 가공품
    typo = _item("플레트재 SUS304")    # 키워드/폴백 미매칭 → 미분류
    items = clf.classify_all([ref, typo])
    assert items[0].final_category == "기구 가공품"
    assert items[1].final_category == "기구 가공품", f"전파 실패: {items[1].final_category}"
    assert items[1].confidence == 70
    assert "유사 항목 전파" in items[1].reason


if __name__ == "__main__":
    test_mechanical_material()
    test_electrical_material()
    test_purchased_standard_parts()
    test_supply_priority()
    test_purchase_priority()
    test_labor()
    test_labor_not_stolen_by_part_keyword()
    test_margin()
    test_expense()
    test_unclassified()
    test_user_rule()
    test_explicit_gongakpum()
    test_explicit_sageup()
    test_section_gumapum_intro()
    test_section_gongakpum_intro()
    test_plate_bracket_variants()
    test_plt_no_false_positive()
    test_mech_part_guard_robot_plate()
    test_mech_part_guard_sensor_bkt()
    test_mech_part_guard_underscore_boundary()
    test_section_subtotal_gongakpum()
    test_section_subtotal_gumapum()
    test_setup_engineer_categories()
    test_mass_production_labor()
    test_similarity_propagation()
    print("✅ classifier tests passed")
