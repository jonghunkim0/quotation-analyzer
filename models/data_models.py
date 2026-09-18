"""
models/data_models.py - 핵심 데이터 구조 정의
"""
from dataclasses import dataclass, field
from typing import Optional
from enum import Enum


class ReviewStatus(Enum):
    """사용자 검토 상태"""
    PENDING = "대기"
    REVIEWED = "검토됨"
    MODIFIED = "수정됨"


class FileStatus(Enum):
    """파일 분석 상태"""
    PENDING = "대기"
    PROCESSING = "처리중"
    COMPLETED = "완료"
    ERROR = "오류"
    OCR_NEEDED = "OCR 필요"


@dataclass
class QuotationItem:
    """견적서 단일 항목"""
    item_id: str
    # 원본 위치 정보
    source_file: str
    source_sheet: str = ""          # 시트명 또는 PDF 페이지
    source_row: int = 0             # 원본 행 번호
    # 견적 항목 정보
    name: str = ""                  # 품명
    spec: str = ""                  # 사양
    quantity: float = 1.0           # 수량
    unit_price: float = 0.0         # 단가
    amount: float = 0.0             # 금액
    remark: str = ""                # 비고
    category_hint: str = ""         # 원본 구분/분류 열
    vendor: str = ""                # 업체명
    # 자동 분류 결과
    auto_category: str = "미분류"
    confidence: float = 0.0         # 0~100
    keywords: list = field(default_factory=list)   # 핵심 키워드
    reason: str = ""                # 분류 근거
    # 최종 분류 (사용자 수정 가능)
    final_category: str = "미분류"
    # 검토 상태
    review_status: ReviewStatus = ReviewStatus.PENDING
    is_modified: bool = False
    # 부가세 여부
    is_tax: bool = False
    is_total_row: bool = False
    # 비교안
    scenario: str = "견적가"

    @property
    def display_amount(self) -> float:
        """표시용 금액 (부가세/합계 행 제외)"""
        if self.is_tax or self.is_total_row:
            return 0.0
        return self.amount


@dataclass
class QuotationFile:
    """업로드된 견적 파일"""
    file_id: str
    filename: str
    file_type: str                  # 'excel' | 'pdf'
    status: FileStatus = FileStatus.PENDING
    sheets: list = field(default_factory=list)       # Excel 시트 목록
    selected_sheet: str = ""
    is_scanned: bool = False         # 스캔형 PDF 여부
    needs_ocr: bool = False
    error_message: str = ""
    items: list = field(default_factory=list)        # QuotationItem 목록
    original_total: float = 0.0      # 원본 총액
    extracted_total: float = 0.0     # 추출 합계
    tax_amount: float = 0.0          # 부가세 금액
    scenario: str = "견적가"          # 해당 비교안 이름


@dataclass
class Scenario:
    """비교안"""
    name: str
    file_id: str = ""
    items: list = field(default_factory=list)
    # 집계 결과 (계산 시 채워짐)
    total_amount: float = 0.0
    analysis_cost: float = 0.0
    material_total: float = 0.0
    labor_total: float = 0.0
    expense_total: float = 0.0
    margin_total: float = 0.0
    supply_total: float = 0.0
    purchase_total: float = 0.0
    material_rate: float = 0.0
    material_rate_with_supply: float = 0.0
    category_totals: dict = field(default_factory=dict)
    category_ratios: dict = field(default_factory=dict)


@dataclass
class ValidationIssue:
    """검증 이슈"""
    issue_type: str
    severity: str                   # 'warning' | 'error'
    message: str
    scenario: str = ""
    item_id: str = ""
