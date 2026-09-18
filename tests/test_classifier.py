"""
tests/test_classifier.py - 자동 분류 로직 테스트
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from models.data_models import QuotationItem
from classification.auto_classifier import AutoClassifier


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
    assert cat == "기구 재료비"
    assert conf >= 70


def test_electrical_material():
    clf = AutoClassifier()
    item = _item("PLC", "FX5U")
    cat, conf, kws, reason = clf.classify(item)
    assert cat == "전장·제어 재료비"


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
    assert cat == "구매품"


def test_labor():
    clf = AutoClassifier()
    item = _item("조립", "인건비")
    cat, conf, kws, reason = clf.classify(item)
    assert cat == "조립 인건비"


def test_margin():
    clf = AutoClassifier()
    item = _item("마진")
    cat, conf, kws, reason = clf.classify(item)
    assert cat == "마진"


def test_expense():
    clf = AutoClassifier()
    item = _item("운송비")
    cat, conf, kws, reason = clf.classify(item)
    assert cat == "경비"


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


if __name__ == "__main__":
    test_mechanical_material()
    test_electrical_material()
    test_supply_priority()
    test_purchase_priority()
    test_labor()
    test_margin()
    test_expense()
    test_unclassified()
    test_user_rule()
    print("✅ classifier tests passed")
