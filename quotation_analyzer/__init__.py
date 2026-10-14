"""
quotation_analyzer - 견적 원가 분석 패키지

pip install:
  pip install git+https://github.com/yourname/quotation-analyzer.git
"""

__version__ = "1.3.6"

from quotation_analyzer.config import COST_CATEGORIES, COST_GROUPS
from quotation_analyzer.models.data_models import (
    QuotationItem, QuotationFile, Scenario, ValidationIssue,
    ReviewStatus, FileStatus,
)
from quotation_analyzer.parsers.excel_parser import ExcelParser
from quotation_analyzer.classification.auto_classifier import AutoClassifier
from quotation_analyzer.export.exporter import Exporter
from quotation_analyzer.analysis.aggregator import Aggregator
from quotation_analyzer.analysis.validator import Validator
from quotation_analyzer.analysis.scenario_manager import ScenarioManager

# PDF 지원 (선택적 — PyMuPDF/pdfplumber 설치 시에만)
try:
    from quotation_analyzer.parsers.pdf_parser import PDFParser
    _HAS_PDF = True
except ImportError:
    PDFParser = None
    _HAS_PDF = False

__all__ = [
    "COST_CATEGORIES", "COST_GROUPS",
    "QuotationItem", "QuotationFile", "Scenario", "ValidationIssue",
    "ReviewStatus", "FileStatus",
    "ExcelParser", "PDFParser",
    "AutoClassifier",
    "Exporter",
    "Aggregator", "Validator", "ScenarioManager",
]
