# 📊 원가구성 비교 분석 도구

제조장비 견적서(Excel/PDF)를 업로드하면 견적 항목을 자동 추출·분류하고,
**견적가 / 구매 목표가 / 개발 검토가** 등 여러 비교안의 원가구성을
누적 막대 + 재료비율 추세선 + 비교안 연결선 + KPI가 결합된 대시보드 차트로 비교하는 사내 웹 도구입니다.

> 🔒 **모든 데이터는 로컬에서 처리**되며 외부 서비스로 전송되지 않습니다.

---

## ✨ 주요 기능

- **파일 업로드**: Excel(.xlsx/.xls), PDF(텍스트형/스캔형) 다중 업로드, 드래그앤드롭
- **자동 추출**: 품명·사양·수량·단가·금액·비고 등 열 이름 자동 인식, 헤더 행 자동 탐지
- **자동 분류**: 13개 비용 분류 + 신뢰도(0~100%) + 분류 근거 표시
  - 사급품/구매품 우선 규칙 (예: '사급 PLC' → 사급품)
- **사용자 수정**: 드롭다운으로 분류 수정, 수정 시 로컬 규칙 자동 학습
- **비교안 관리**: 추가·삭제·복제·이름변경, 파일→비교안 매핑
- **집계·검증**: 분류별 합계/구성비, 원본 총액 vs 추출 합계 차이 검증 등 12종 검증
- **원가구성 비교 차트**: 세로 누적 막대, 상단 KPI, 재료비율 추세선(보조 Y축),
  비교안 간 연결선, 선택 비교안 강조 테두리, 증감 Callout
- **사급품 처리 옵션**: 포함/제외 5가지 모드
- **내보내기**: CSV / Excel(다중 시트) / 차트 PNG
- **분류 규칙 관리**: 추가·수정·삭제·내보내기, 적용 이력

---

## 📁 프로젝트 구조

```
quotation-analyzer/
├── app.py                      # Streamlit 메인 앱
├── config.py                   # 전역 설정·상수 (분류, 색상, 열 매핑)
├── requirements.txt
├── models/
│   └── data_models.py          # QuotationItem / QuotationFile / Scenario
├── utils/
│   └── helpers.py              # 금액 파싱, 포맷, 단위 감지 등
├── parsers/
│   ├── excel_parser.py         # Excel 파서 (헤더 자동 탐지)
│   ├── pdf_parser.py           # PDF 파서 (스캔형 감지)
│   └── ocr_processor.py        # OCR (pytesseract)
├── classification/
│   ├── auto_classifier.py      # 자동 분류 (키워드 규칙 + 사용자 규칙)
│   └── rule_store.py           # 사용자 규칙 로컬 저장 (JSON)
├── analysis/
│   ├── aggregator.py           # 비용 집계 (사급품 옵션 반영)
│   ├── validator.py            # 12종 검증
│   └── scenario_manager.py     # 비교안 관리
├── visualization/
│   └── cost_chart.py           # 원가구성 비교 대시보드 (Plotly)
├── export/
│   └── exporter.py             # CSV / Excel 내보내기
├── data/
│   └── generate_sample.py      # 샘플 견적서 생성기
└── tests/
    ├── test_parsers.py
    ├── test_classifier.py
    └── test_aggregator.py
```

---

## 🚀 설치 및 실행

### 1. 의존성 설치

```powershell
cd quotation-analyzer
pip install -r requirements.txt
```

> 차트 PNG 저장을 사용하려면 `pip install kaleido`
> OCR(스캔형 PDF)을 사용하려면 [Tesseract OCR](https://github.com/UB-Mannheim/tesseract/wiki) 설치 + `pytesseract`

### 2. 샘플 데이터 생성 (선택)

```powershell
python data/generate_sample.py
```

`data/sample/`에 견적가·구매목표가·개발검토가 3개 Excel이 생성됩니다.

### 3. 앱 실행

```powershell
streamlit run app.py
```

브라우저에서 `http://localhost:8501` 접속.

### 4. 테스트 실행

```powershell
python tests/test_parsers.py
python tests/test_classifier.py
python tests/test_aggregator.py
```

---

## 📋 비용 분류 (13개)

| # | 분류 | 그룹 |
|---|------|------|
| 1 | 기구 재료비 | 재료비 |
| 2 | 전장·제어 재료비 | 재료비 |
| 3 | 사급품 | 재료비 |
| 4 | 구매품 | 재료비 |
| 5 | 기구설계 인건비 | 인건비 |
| 6 | 제어설계 인건비 | 인건비 |
| 7 | 조립 인건비 | 인건비 |
| 8 | 셋업 인건비(기구) | 인건비 |
| 9 | 셋업 인건비(제어) | 인건비 |
| 10 | 셋업 인건비(전장) | 인건비 |
| 11 | 경비 | 기타 |
| 12 | 마진 | 기타 |
| 13 | 미분류 | 별도 관리 |

---

## 🧮 핵심 계산식

```
재료비 합계   = 기구 재료비 + 전장·제어 재료비 + 구매품 + (사급품*옵션)
재료비율(%)   = 재료비 합계 ÷ 기준 총액 × 100
인건비 합계   = 6개 인건비 분류 합계
분석 원가     = 재료비 합계 + 인건비 합계 + 경비
총 견적금액   = 분석 원가 + 마진
구성비(%)     = 각 분류 금액 ÷ 기준 총액 × 100
증감액        = 현재 비교안 - 이전 비교안
증감률(%)     = 증감액 ÷ 이전 비교안 × 100
```

---

## 🔒 보안

- 완전 로컬 처리, 외부 API 미사용
- 로그에 견적 내용·업체명·금액 기록 금지
- 파일 확장자/MIME/크기 검증
- 사용자 규칙은 로컬 JSON에만 저장
