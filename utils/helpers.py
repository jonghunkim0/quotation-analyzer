"""
utils/helpers.py - 공용 유틸리티 함수
"""
import re
import uuid
from typing import Optional, Union


def generate_id(prefix: str = "") -> str:
    """유일한 ID 생성"""
    short = uuid.uuid4().hex[:8]
    return f"{prefix}{short}" if prefix else short


def parse_amount(value) -> float:
    """
    금액 문자열을 float로 변환.
    쉼표, 통화기호, 공백, 괄호를 처리.
    음수: (123) 또는 -123 형식 지원.
    """
    if value is None:
        return 0.0
    if isinstance(value, (int, float)):
        return float(value)

    s = str(value).strip()
    if not s or s in {"-", "--", "N/A", "n/a", "없음", "-"}:
        return 0.0

    # 괄호로 표시된 음수: (1,234)
    negative = False
    if s.startswith("(") and s.endswith(")"):
        negative = True
        s = s[1:-1]
    elif s.startswith("(-") and s.endswith(")"):
        negative = True
        s = s[2:-1]

    # 통화기호, 쉼표, 공백 제거
    s = re.sub(r"[₩$€¥,，\s]", "", s)

    # 마이너스 표기
    if s.startswith("-"):
        negative = True
        s = s[1:]

    # 숫자만 추출 (소수점 포함)
    match = re.search(r"[\d.]+", s)
    if not match:
        return 0.0

    try:
        result = float(match.group())
    except ValueError:
        return 0.0

    return -result if negative else result


def format_amount(amount: float, unit: str = "원", decimals: int = 0) -> str:
    """
    금액을 지정된 단위로 포맷.
    unit: '원', '천원', '백만원', '억원'
    """
    unit_map = {
        "원": (1, "원"),
        "천원": (1_000, "천원"),
        "백만원": (1_000_000, "백만원"),
        "억원": (100_000_000, "억"),
    }
    divisor, suffix = unit_map.get(unit, (1, "원"))
    value = amount / divisor
    if decimals == 0:
        return f"{value:,.0f}{suffix}"
    return f"{value:,.{decimals}f}{suffix}"


def auto_detect_unit(max_amount: float) -> str:
    """데이터 규모에 따라 표시 단위 자동 결정"""
    if max_amount >= 1_000_000_000:
        return "억원"
    elif max_amount >= 10_000_000:
        return "백만원"
    elif max_amount >= 100_000:
        return "천원"
    return "원"


def normalize_text(text: str) -> str:
    """텍스트 정규화: 소문자, 공백 제거"""
    if not text:
        return ""
    return re.sub(r"\s+", "", str(text).lower())


def safe_divide(numerator: float, denominator: float, default: float = 0.0) -> float:
    """안전한 나눗셈"""
    if denominator == 0:
        return default
    return numerator / denominator


def match_column(header: str, aliases: list) -> bool:
    """열 이름이 별칭 목록과 일치하는지 확인"""
    norm = normalize_text(header)
    for alias in aliases:
        if normalize_text(alias) in norm or norm in normalize_text(alias):
            return True
    return False


def is_total_row(text: str) -> bool:
    """합계/소계 행인지 확인"""
    from config import TOTAL_ROW_KEYWORDS
    norm = normalize_text(text)
    for kw in TOTAL_ROW_KEYWORDS:
        if normalize_text(kw) in norm:
            return True
    return False


def is_blank_row(values: list) -> bool:
    """모든 값이 빈 행인지 확인"""
    for v in values:
        if v is not None and str(v).strip() != "":
            return False
    return True
