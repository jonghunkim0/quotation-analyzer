"""
app.py - 원가구성 비교 분석 도구 (Streamlit 메인 앱)

실행: streamlit run app.py
"""
import os
import sys
import tempfile
from pathlib import Path

# 프로젝트 루트를 sys.path에 추가
sys.path.insert(0, str(Path(__file__).parent))

import streamlit as st
import pandas as pd
from datetime import datetime

from config import (
    COST_CATEGORIES,
    COST_GROUPS,
    DEFAULT_STACK_ORDER,
    CATEGORY_COLORS,
    DEFAULT_SCENARIOS,
    AMOUNT_UNITS,
    SUPPLY_OPTIONS,
    SUPPORTED_EXTENSIONS,
)
from models.data_models import (
    QuotationItem,
    QuotationFile,
    Scenario,
    ReviewStatus,
    FileStatus,
)
from parsers.excel_parser import ExcelParser
from parsers.pdf_parser import PDFParser
from parsers.ocr_processor import OCRProcessor
from classification.auto_classifier import AutoClassifier
from classification.rule_store import RuleStore
from analysis.aggregator import Aggregator
from analysis.validator import Validator
from analysis.scenario_manager import ScenarioManager
from visualization.cost_chart import CostCompositionChart
from export.exporter import Exporter
from utils.helpers import format_amount, auto_detect_unit, generate_id

# ─── 페이지 설정 ─────────────────────────────────────────────
st.set_page_config(
    page_title="원가구성 비교 분석 도구",
    page_icon="📊",
    layout="wide",
    initial_sidebar_state="expanded",
)

# ─── 세션 상태 초기화 ────────────────────────────────────────
if "files" not in st.session_state:
    st.session_state.files = {}          # {file_id: QuotationFile}
    st.session_state.scenario_mgr = ScenarioManager()
    st.session_state.scenario_mgr.init_default()
    st.session_state.rule_store = RuleStore()
    st.session_state.classifier = AutoClassifier(
        user_rules=st.session_state.rule_store.get_rules()
    )
    st.session_state.aggregator = Aggregator()
    st.session_state.validator = Validator()
    st.session_state.scenarios = []      # 집계된 Scenario 목록
    st.session_state.deltas = []
    st.session_state.issues = []
    st.session_state.highlight = "구매 목표가"
    st.session_state.unit = "백만원"
    st.session_state.decimals = 1
    st.session_state.supply_option = SUPPLY_OPTIONS[0]
    st.session_state.show_material_rate = True
    st.session_state.show_connection_lines = True
    st.session_state.show_deltas = True
    st.session_state.show_supply = True
    st.session_state.show_unclassified = True
    st.session_state.hide_zero_supply = False
    st.session_state.dim_unselected = True
    st.session_state.stack_order = list(DEFAULT_STACK_ORDER)
    st.session_state.filter_mode = "전체"
    st.session_state.selected_category_filter = None
    st.session_state.uploaded_files_raw = {}  # {filename: UploadedFile}
    st.session_state.chat_history = []         # [{role, content}]
    st.session_state.reset_counter = 0         # file_uploader 초기화용


# ─── 헬퍼 함수 ───────────────────────────────────────────────
def process_uploaded_file(uploaded_file, scenario: str = "견적가") -> QuotationFile:
    """
    업로드된 파일을 임시 디스크에 저장한 뒤 파싱.
    (Streamlit UploadedFile은 메모리 객체라 파서가 읽을 수 있는 경로로 저장 필요)
    """
    filename = uploaded_file.name
    ext = Path(filename).suffix.lower()

    if ext not in SUPPORTED_EXTENSIONS:
        return QuotationFile(
            file_id=generate_id("file_"),
            filename=filename,
            file_type="unknown",
            status=FileStatus.ERROR,
            error_message=f"지원하지 않는 형식: {ext}",
        )

    # 임시 파일로 저장 (파서가 file_path 문자열을 요구함)
    suffix = ext
    with tempfile.NamedTemporaryFile(
        suffix=suffix, delete=False
    ) as tmp:
        tmp.write(uploaded_file.getbuffer())
        tmp_path = tmp.name

    try:
        if ext in (".xlsx", ".xls"):
            parser = ExcelParser()
            sheets = parser.list_sheets(tmp_path)
            # 첫 시트 자동 선택
            selected = sheets[0] if sheets else ""
            qf = parser.parse_sheet(tmp_path, selected, filename, scenario)
            qf.sheets = sheets
        elif ext == ".pdf":
            parser = PDFParser()
            qf = parser.parse(tmp_path, filename, scenario)
    except Exception as e:
        qf = QuotationFile(
            file_id=generate_id("file_"),
            filename=filename,
            file_type="excel" if ext in (".xlsx", ".xls") else "pdf",
            status=FileStatus.ERROR,
            error_message=str(e),
        )
    finally:
        # 임시 파일 정리
        try:
            os.unlink(tmp_path)
        except OSError:
            pass

    return qf


def run_classification():
    """모든 파일의 항목을 자동 분류"""
    for qf in st.session_state.files.values():
        if qf.items:
            st.session_state.classifier.classify_all(qf.items)


def run_aggregation():
    """비교안별 집계 + 검증"""
    agg = Aggregator(supply_option=st.session_state.supply_option)
    scenarios = []
    for name in st.session_state.scenario_mgr.get_order():
        scen = st.session_state.scenario_mgr.get_scenario(name)
        if scen and scen.items:
            aggregated = agg.aggregate_scenario(
                name, scen.items, scen.file_id
            )
            scenarios.append(aggregated)
    st.session_state.scenarios = scenarios
    st.session_state.deltas = agg.compute_deltas(scenarios)

    # 검증
    validator = st.session_state.validator
    issues = []
    for qf in st.session_state.files.values():
        issues.extend(validator.validate_file(qf))
    for s in scenarios:
        issues.extend(validator.validate_scenario(s))
        issues.extend(validator.validate_items(s.items, s.name))
    st.session_state.issues = issues


def refresh_all():
    """분류 → 집계 → 검증 전체 재실행"""
    run_classification()
    run_aggregation()


# ─── 사이드바: 설정 ──────────────────────────────────────────
with st.sidebar:
    st.header("⚙️ 설정")

    st.subheader("금액 표시")
    st.session_state.unit = st.selectbox(
        "표시 단위",
        list(AMOUNT_UNITS.keys()),
        index=list(AMOUNT_UNITS.keys()).index(st.session_state.unit),
    )
    st.session_state.decimals = st.number_input(
        "소수점 자릿수", min_value=0, max_value=4,
        value=st.session_state.decimals,
    )

    st.subheader("사급품 처리")
    st.session_state.supply_option = st.selectbox(
        "사급품 처리 옵션",
        SUPPLY_OPTIONS,
        index=SUPPLY_OPTIONS.index(st.session_state.supply_option),
    )

    st.subheader("차트 옵션")
    st.session_state.show_material_rate = st.checkbox(
        "재료비율 추세선", value=st.session_state.show_material_rate
    )
    st.session_state.show_connection_lines = st.checkbox(
        "비교안 연결선", value=st.session_state.show_connection_lines
    )
    st.session_state.show_deltas = st.checkbox(
        "증감 Callout", value=st.session_state.show_deltas
    )
    st.session_state.show_supply = st.checkbox(
        "사급품 표시", value=st.session_state.show_supply
    )
    st.session_state.show_unclassified = st.checkbox(
        "미분류 표시", value=st.session_state.show_unclassified
    )
    st.session_state.hide_zero_supply = st.checkbox(
        "사급품 0일 때 숨김", value=st.session_state.hide_zero_supply
    )
    st.session_state.dim_unselected = st.checkbox(
        "선택 안 외 흐림", value=st.session_state.dim_unselected
    )

    st.subheader("강조 비교안")
    st.session_state.highlight = st.selectbox(
        "강조할 비교안",
        st.session_state.scenario_mgr.get_order(),
        index=(
            st.session_state.scenario_mgr.get_order().index(
                st.session_state.highlight
            )
            if st.session_state.highlight
            in st.session_state.scenario_mgr.get_order()
            else 0
        ),
    )

    st.subheader("누적 순서")
    st.session_state.stack_order = st.multiselect(
        "누적 순서 (위→아래)",
        COST_CATEGORIES,
        default=st.session_state.stack_order,
    )

    st.divider()
    st.caption(
        "🔒 모든 데이터는 로컬에서 처리됩니다. "
        "외부 서비스로 전송되지 않습니다."
    )

# ─── 메인 헤더 ───────────────────────────────────────────────
APP_VERSION = "1.3.6"
APP_UPDATED = "2026. 10. 12."
st.markdown(
    f'<div style="display:flex;align-items:baseline;gap:10px;">'
    f'<h1 style="margin:0;">📊 원가구성 비교 분석 도구</h1>'
    f'<span style="font-size:0.85rem;color:#888;">'
    f'ver {APP_VERSION} · 업데이트 {APP_UPDATED}</span>'
    f'</div>',
    unsafe_allow_html=True,
)
st.caption(
    "Excel/PDF 견적서 **업로드** → 자동 분류 → 원가구성 비교 차트"
)

# ─── 1. 파일 업로드 영역 ─────────────────────────────────────
hdr_left, hdr_right = st.columns([4, 1], gap="small")
with hdr_left:
    st.subheader("1. 파일 업로드")
with hdr_right:
    if st.button("🔄 새로운 분석", key="btn_reset"):
        st.session_state.files = {}
        st.session_state.scenario_mgr.init_default()
        st.session_state.scenarios = []
        st.session_state.deltas = []
        st.session_state.issues = []
        st.session_state.uploaded_files_raw = {}
        st.session_state.chat_history = []
        st.session_state.reset_counter += 1  # file_uploader 초기화
        st.rerun()

uploaded_files = st.file_uploader(
    "견적 파일 선택",
    type=["xlsx", "xls", "pdf"],
    accept_multiple_files=True,
    key=f"file_uploader_{st.session_state.reset_counter}",
)

btn_col, status_col = st.columns([2, 3])
with btn_col:
    analyze_clicked = st.button(
        "▶ 분석 시작",
        use_container_width=True,
        key="btn_analyze",
        disabled=not uploaded_files,
    )
with status_col:
    if not uploaded_files:
        st.info("📁 먼저 파일을 업로드해 주세요.")
    elif analyze_clicked:
        total_files = len(uploaded_files)
        for idx, up in enumerate(uploaded_files):
            existing = [
                f for f in st.session_state.files.values() if f.filename == up.name
            ]
            if existing:
                st.info(f"'{up.name}'은(는) 이미 추가되어 있습니다.")
                continue

            # 진행률 바 (해당 파일 자체의 진행률 0→100%)
            progress_bar = st.progress(
                0.0,
                text=f"분석 중: {up.name} ({idx + 1}/{total_files})",
            )

            # 파일명 기반 비교안 이름 (확장자 제거)
            scen_name = Path(up.name).stem
            st.session_state.scenario_mgr.add_scenario(scen_name)

            qf = process_uploaded_file(up, scenario=scen_name)
            st.session_state.files[qf.file_id] = qf
            st.session_state.scenario_mgr.assign_file(scen_name, qf)
            st.session_state.uploaded_files_raw[up.name] = up

            # 분류 단계
            progress_bar.progress(
                0.5,
                text=f"분류 중: {up.name} ({idx + 1}/{total_files})",
            )
            run_classification()

            # 집계 단계
            progress_bar.progress(
                0.9,
                text=f"집계 중: {up.name} ({idx + 1}/{total_files})",
            )
            run_aggregation()

            # 완료 (해당 파일 바 100%)
            progress_bar.progress(
                1.0,
                text=f"완료: {up.name} ({idx + 1}/{total_files})",
            )

            if qf.status == FileStatus.COMPLETED:
                st.success(f"✅ '{qf.filename}' 분석 완료 ({len(qf.items)}개 항목)")
            elif qf.status == FileStatus.OCR_NEEDED:
                st.warning(f"🔍 '{qf.filename}'은(는) 스캔형 PDF입니다. OCR 처리가 필요합니다.")
            else:
                st.error(f"❌ '{qf.filename}' 분석 실패: {qf.error_message}")

        # 전체 완료 표시
        st.success(f"🎉 전체 분석 완료 ({total_files}개 파일)")
    else:
        # 이미 분석된 파일: 진행바를 100% 완료 상태로 표시
        analyzed_names = {f.filename for f in st.session_state.files.values()}
        total_files = len(uploaded_files)
        for idx, up in enumerate(uploaded_files):
            if up.name in analyzed_names:
                st.progress(
                    1.0,
                    text=f"✅ 완료: {up.name} ({idx + 1}/{total_files})",
                )
        if analyzed_names:
            st.success(f"🎉 전체 분석 완료 ({len(analyzed_names)}개 파일)")
        else:
            st.info("📁 파일을 업로드했습니다. **분석 시작** 버튼을 눌러 주세요.")

# 업로드 파일 목록
if st.session_state.files:
    col1, col2 = st.columns([3, 2])
    with col1:
        st.markdown("**업로드된 파일**")
        for fid, qf in st.session_state.files.items():
            status_icon = {
                FileStatus.COMPLETED: "✅",
                FileStatus.ERROR: "❌",
                FileStatus.OCR_NEEDED: "🔍",
                FileStatus.PROCESSING: "⏳",
                FileStatus.PENDING: "⏸️",
            }.get(qf.status, "❓")
            st.markdown(
                f"{status_icon} **{qf.filename}** "
                f"({len(qf.items)}개 항목)"
            )
            if qf.error_message:
                st.caption(f"   ⚠️ {qf.error_message}")
            if qf.needs_ocr:
                st.caption("   🔍 스캔형 PDF - OCR 처리 필요")
            if qf.sheets and qf.file_type == "excel":
                st.caption(f"   📑 시트: {', '.join(qf.sheets)}")

    with col2:
        st.markdown("**원본 vs 추출 합계**")
        for fid, qf in st.session_state.files.items():
            if qf.original_total > 0:
                diff = qf.original_total - qf.extracted_total
                diff_str = f"차이: {diff:,.0f}"
                if abs(diff) > max(1, qf.original_total * 0.0001):
                    st.warning(f"{qf.filename}: {diff_str}")
                else:
                    st.success(f"{qf.filename}: {diff_str}")

# ─── 2. 비교안 관리 ──────────────────────────────────────────
st.subheader("2. 비교안 관리")

mgr = st.session_state.scenario_mgr
order = mgr.get_order()

col_a, col_b, col_c, col_d = st.columns(4)
with col_a:
    new_name = st.text_input("새 비교안 이름", key="new_scen_name")
    if st.button("➕ 추가", key="btn_add_scen") and new_name.strip():
        mgr.add_scenario(new_name.strip())
        st.rerun()

with col_b:
    if order:
        del_name = st.selectbox("삭제할 비교안", order, key="del_scen")
        if st.button("🗑️ 삭제", key="btn_del_scen") and del_name:
            mgr.remove_scenario(del_name)
            st.rerun()

with col_c:
    if len(order) >= 1:
        dup_src = st.selectbox("복제 원본", order, key="dup_src")
        dup_name = st.text_input("새 이름", key="dup_name")
        if st.button("📋 복제", key="btn_dup_scen") and dup_name.strip():
            mgr.duplicate_scenario(dup_src, dup_name.strip())
            st.rerun()

with col_d:
    if order:
        rename_src = st.selectbox("이름 변경 원본", order, key="ren_src")
        rename_new = st.text_input("새 이름", key="ren_new")
        if st.button("✏️ 변경", key="btn_ren_scen") and rename_new.strip():
            mgr.rename_scenario(rename_src, rename_new.strip())
            st.rerun()

# 파일 → 비교안 매핑
if st.session_state.files:
    st.markdown("**파일 → 비교안 매핑**")
    file_cols = st.columns(min(len(st.session_state.files), 4))
    for i, (fid, qf) in enumerate(st.session_state.files.items()):
        with file_cols[i % len(file_cols)]:
            assigned = st.selectbox(
                f"{qf.filename}",
                order,
                index=order.index(qf.scenario)
                if qf.scenario in order
                else 0,
                key=f"map_{fid}",
            )
            if assigned != qf.scenario:
                qf.scenario = assigned
                mgr.assign_file(assigned, qf)
                run_aggregation()

# ─── 3. 원본 데이터 및 분류 검토 테이블 ─────────────────────
st.subheader("3. 견적 항목 및 분류 검토")

# 모든 항목 수집
all_items = []
for qf in st.session_state.files.values():
    all_items.extend(qf.items)

if all_items:
    # 필터
    filter_col1, filter_col2, filter_col3 = st.columns(3)
    with filter_col1:
        st.session_state.filter_mode = st.selectbox(
            "필터",
            ["전체", "미분류", "낮은 신뢰도 (<70%)", "수정됨", "합계 오류"],
            index=["전체", "미분류", "낮은 신뢰도 (<70%)", "수정됨", "합계 오류"].index(
                st.session_state.filter_mode
            ),
        )
    with filter_col2:
        st.session_state.selected_category_filter = st.selectbox(
            "분류 필터",
            ["전체"] + COST_CATEGORIES,
            index=0,
        )
    with filter_col3:
        scenario_filter = st.selectbox(
            "비교안 필터",
            ["전체"] + order,
            index=0,
        )

    # 필터링
    filtered = all_items
    if st.session_state.filter_mode == "미분류":
        filtered = [i for i in filtered if i.final_category == "미분류"]
    elif st.session_state.filter_mode == "낮은 신뢰도 (<70%)":
        filtered = [i for i in filtered if i.confidence < 70]
    elif st.session_state.filter_mode == "수정됨":
        filtered = [i for i in filtered if i.is_modified]
    elif st.session_state.filter_mode == "합계 오류":
        error_ids = {i.item_id for i in st.session_state.issues if i.item_id}
        filtered = [i for i in filtered if i.item_id in error_ids]

    if st.session_state.selected_category_filter != "전체":
        filtered = [
            i
            for i in filtered
            if i.final_category == st.session_state.selected_category_filter
        ]
    if scenario_filter != "전체":
        filtered = [i for i in filtered if i.scenario == scenario_filter]

    # 테이블 표시
    table_data = []
    for it in filtered:
        table_data.append({
            "비교안": it.scenario,
            "파일": it.source_file[:20],
            "시트/페이지": it.source_sheet,
            "행": it.source_row,
            "품명": it.name[:30],
            "사양": it.spec[:20],
            "수량": it.quantity,
            "단가": f"{it.unit_price:,.0f}" if it.unit_price else "",
            "금액": f"{it.amount:,.0f}",
            "자동분류": it.auto_category,
            "신뢰도": f"{it.confidence:.0f}%",
            "최종분류": it.final_category,
            "수정": "✅" if it.is_modified else "",
        })

    df_table = pd.DataFrame(table_data)
    st.dataframe(
        df_table,
        use_container_width=True,
        height=400,
        hide_index=True,
    )

    # 분류 수정 (상세 편집)
    st.markdown("**분류 수정**")
    edit_col1, edit_col2, edit_col3 = st.columns([2, 2, 1])
    with edit_col1:
        item_options = {
            f"{i.source_file[:15]}|{i.source_row}|{i.name[:20]}": i
            for i in filtered
        }
        selected_key = st.selectbox(
            "수정할 항목",
            list(item_options.keys()),
            index=0,
            key="edit_item",
        )
    with edit_col2:
        if selected_key and selected_key in item_options:
            item = item_options[selected_key]
            new_cat = st.selectbox(
                "최종 분류",
                COST_CATEGORIES,
                index=COST_CATEGORIES.index(item.final_category)
                if item.final_category in COST_CATEGORIES
                else COST_CATEGORIES.index("미분류"),
                key=f"cat_{item.item_id}",
            )
            if new_cat != item.final_category:
                if st.button("💾 분류 저장", key=f"save_{item.item_id}"):
                    item.final_category = new_cat
                    item.is_modified = True
                    item.review_status = ReviewStatus.MODIFIED
                    # 규칙 학습
                    kw = st.session_state.rule_store.learn_from_correction(
                        item.name, item.spec, new_cat
                    )
                    if kw:
                        st.session_state.classifier.user_rules = (
                            st.session_state.rule_store.get_rules()
                        )
                        st.toast(f"규칙 학습: '{kw}' → {new_cat}")
                    run_aggregation()
                    st.rerun()

    st.caption(
        f"총 {len(all_items)}개 항목 중 {len(filtered)}개 표시"
    )

# ─── 4. 비용 집계표 ──────────────────────────────────────────
st.subheader("4. 비용 집계표")

if st.session_state.scenarios:
    summary_rows = []
    for s in st.session_state.scenarios:
        row = {"비교안": s.name}
        for cat in COST_CATEGORIES:
            row[cat] = s.category_totals.get(cat, 0.0)
        row["총 견적금액"] = s.total_amount
        row["분석 원가"] = s.analysis_cost
        row["재료비 합계"] = s.material_total
        row["인건비 합계"] = s.labor_total
        row["경비"] = s.expense_total
        row["마진"] = s.margin_total
        row["사급품"] = s.supply_total
        row["구매품"] = s.purchase_total
        row["재료비율(%)"] = round(s.material_rate, 1)
        row["사급포함 재료비율(%)"] = round(s.material_rate_with_supply, 1)
        summary_rows.append(row)

    df_summary = pd.DataFrame(summary_rows)
    st.dataframe(
        df_summary,
        use_container_width=True,
        height=300,
        hide_index=True,
    )

    # 구성비 표시
    st.markdown("**분류별 구성비 (%)**")
    ratio_rows = []
    for s in st.session_state.scenarios:
        row = {"비교안": s.name}
        for cat in COST_CATEGORIES:
            row[cat] = round(s.category_ratios.get(cat, 0.0), 1)
        ratio_rows.append(row)
    df_ratio = pd.DataFrame(ratio_rows)
    st.dataframe(
        df_ratio,
        use_container_width=True,
        height=250,
        hide_index=True,
    )

    # 검증 이슈
    if st.session_state.issues:
        with st.expander(f"⚠️ 검증 이슈 ({len(st.session_state.issues)}개)"):
            for issue in st.session_state.issues:
                icon = "🔴" if issue.severity == "error" else "🟡"
                st.markdown(
                    f"{icon} **[{issue.issue_type}]** {issue.message}"
                )

# ─── 5. 원가구성 비교 차트 ──────────────────────────────────
st.subheader("5. 원가구성 비교 차트")

if st.session_state.scenarios:
    # 자동 단위 감지
    max_amount = max(
        (s.total_amount for s in st.session_state.scenarios), default=0
    )
    if max_amount > 0:
        auto_unit = auto_detect_unit(max_amount)
        if st.session_state.unit == "백만원" and auto_unit != "백만원":
            st.session_state.unit = auto_unit

    chart = CostCompositionChart(
        scenarios=st.session_state.scenarios,
        unit=st.session_state.unit,
        decimals=st.session_state.decimals,
        stack_order=st.session_state.stack_order,
        highlight_scenario=st.session_state.highlight,
        show_material_rate=st.session_state.show_material_rate,
        show_connection_lines=st.session_state.show_connection_lines,
        show_deltas=st.session_state.show_deltas,
        show_supply=st.session_state.show_supply,
        show_unclassified=st.session_state.show_unclassified,
        hide_zero_supply=st.session_state.hide_zero_supply,
        dim_unselected=st.session_state.dim_unselected,
    )

    # 1차: 비용 그룹 비교
    fig1 = chart.build()
    st.plotly_chart(fig1, use_container_width=True)

    # 2차: 세부 분류 비교 (구매품/재료비/인건비/경비 각각)
    figs2 = chart.build_detail()
    for i, fig in enumerate(figs2):
        st.plotly_chart(fig, use_container_width=True)

    # 차트 PNG 저장
    if st.button("📷 차트 PNG 저장", key="btn_save_png"):
        try:
            fig1.write_image("cost_chart_1.png", scale=2)
            for i, fig in enumerate(figs2):
                fig.write_image(f"cost_chart_2_{i+1}.png", scale=2)
            st.success("차트가 PNG로 저장되었습니다.")
        except Exception as e:
            st.error(f"PNG 저장 실패: {e}")
            st.info(
                "kaleido 패키지가 필요합니다: pip install kaleido"
            )

# ─── 6. 내보내기 ─────────────────────────────────────────────
st.subheader("6. 결과 내보내기")

if st.session_state.scenarios:
    import io
    import pandas as pd

    metadata = {
        "원본 파일": ", ".join(
            f.filename for f in st.session_state.files.values()
        ),
        "사급품 처리": st.session_state.supply_option,
        "표시 단위": st.session_state.unit,
        "사용자 수정 여부": "Y"
        if any(i.is_modified for i in all_items)
        else "N",
    }
    exporter = Exporter(metadata=metadata)

    def _csv_to_xlsx(csv_str: str) -> bytes:
        """CSV 문자열을 Excel 바이너리로 변환 (빈 데이터 처리)"""
        if not csv_str or not csv_str.strip():
            df = pd.DataFrame({"메시지": ["데이터 없음"]})
        else:
            df = pd.read_csv(io.StringIO(csv_str))
        buf = io.BytesIO()
        df.to_excel(buf, index=False, engine="openpyxl")
        return buf.getvalue()

    # 원본 파일에 분류 열 추가하여 내보내기 (공용 함수)
    def _build_original_with_classification() -> bytes:
        """원본 Excel을 그대로 유지하고 끝단에 분류 열을 추가"""
        import openpyxl
        import tempfile
        import os

        # 파일별 항목 매핑: (source_file, source_sheet, source_row) -> item
        item_map = {}
        for it in all_items:
            key = (it.source_file, it.source_sheet, it.source_row)
            item_map[key] = it

        # 원본 업로드 파일 찾기
        first_qf = next(iter(st.session_state.files.values()), None)
        if first_qf is None:
            df = pd.DataFrame({"메시지": ["데이터 없음"]})
            buf = io.BytesIO()
            df.to_excel(buf, index=False, engine="openpyxl")
            return buf.getvalue()

        raw_file = st.session_state.uploaded_files_raw.get(first_qf.filename)
        if raw_file is None:
            df = pd.DataFrame({"메시지": ["원본 파일 데이터를 찾을 수 없습니다."]})
            buf = io.BytesIO()
            df.to_excel(buf, index=False, engine="openpyxl")
            return buf.getvalue()

        # 원본 파일을 임시 파일로 복사
        tmp_path = os.path.join(tempfile.gettempdir(), f"_orig_{first_qf.filename}")
        with open(tmp_path, "wb") as f:
            f.write(raw_file.getvalue())

        try:
            wb = openpyxl.load_workbook(tmp_path)
        except Exception:
            # 읽기 실패 시 분석 결과만 반환
            df = pd.DataFrame([
                {
                    "품명": it.name,
                    "수량": it.quantity,
                    "단가": it.unit_price,
                    "금액": it.amount,
                    "자동분류": it.auto_category,
                    "신뢰도(%)": it.confidence,
                    "최종분류": it.final_category,
                    "분류근거": it.reason,
                }
                for it in all_items
            ])
            buf = io.BytesIO()
            df.to_excel(buf, index=False, engine="openpyxl")
            return buf.getvalue()

        # 모든 시트 처리
        for ws in wb.worksheets:
            # 헤더 행 탐지 (parser와 동일한 로직)
            from parsers.excel_parser import ExcelParser
            parser = ExcelParser()
            df_tmp = pd.read_excel(tmp_path, sheet_name=ws.title, header=None)
            header_idx = parser.detect_header_row(df_tmp)
            if header_idx < 0:
                continue

            # 기존 최대 열 번호
            max_col = ws.max_column
            # 분류 열 시작 위치
            new_col_start = max_col + 1

            # 헤더 행에 분류 열 이름 추가
            new_headers = ["자동분류", "신뢰도(%)", "핵심키워드", "분류근거", "최종분류", "검토상태", "수정여부"]
            for i, h in enumerate(new_headers):
                ws.cell(row=header_idx + 1, column=new_col_start + i, value=h)

            # 데이터 행에 분류 정보 채우기
            for row_idx in range(header_idx + 1, len(df_tmp)):
                source_row = row_idx + 1  # 1-based (parser와 동일)
                key = (first_qf.filename, ws.title, source_row)
                if key in item_map:
                    it = item_map[key]
                    ws.cell(row=row_idx + 1, column=new_col_start + 0, value=it.auto_category)
                    ws.cell(row=row_idx + 1, column=new_col_start + 1, value=it.confidence)
                    ws.cell(row=row_idx + 1, column=new_col_start + 2, value=", ".join(it.keywords))
                    ws.cell(row=row_idx + 1, column=new_col_start + 3, value=it.reason)
                    ws.cell(row=row_idx + 1, column=new_col_start + 4, value=it.final_category)
                    ws.cell(row=row_idx + 1, column=new_col_start + 5, value=it.review_status.value)
                    ws.cell(row=row_idx + 1, column=new_col_start + 6, value="Y" if it.is_modified else "N")

        # BytesIO로 저장
        buf = io.BytesIO()
        wb.save(buf)
        wb.close()

        # 임시 파일 삭제
        try:
            os.unlink(tmp_path)
        except OSError:
            pass

        return buf.getvalue()

    exp_col1, exp_col2, exp_col3 = st.columns(3)

    with exp_col1:
        st.download_button(
            "📄 견적 세부분류",
            data=_build_original_with_classification(),
            file_name="견적세부분류.xlsx",
            mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
            key="dl_items",
        )
    with exp_col2:
        csv_content = exporter.export_summary_csv(
            st.session_state.scenarios
        )
        st.download_button(
            "📊 집계표",
            data=_csv_to_xlsx(csv_content),
            file_name="집계표.xlsx",
            mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
            key="dl_summary",
        )
    with exp_col3:
        csv_content = exporter.export_comparison_csv(
            st.session_state.scenarios, st.session_state.deltas
        )
        st.download_button(
            "📈 증감분석",
            data=_csv_to_xlsx(csv_content),
            file_name="증감분석.xlsx",
            mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
            key="dl_delta",
        )

    exp_col4, exp_col5 = st.columns(2)
    with exp_col4:
        buf = io.BytesIO()
        exporter.export_excel(
            buf,
            all_items,
            st.session_state.scenarios,
            st.session_state.deltas,
            st.session_state.issues,
        )
        st.download_button(
            "📑 전체 Excel",
            data=buf.getvalue(),
            file_name="원가분석_결과.xlsx",
            mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
            key="dl_excel",
        )

    with exp_col5:
        csv_content = exporter.export_validation_csv(
            st.session_state.issues
        )
        st.download_button(
            "⚠️ 검증오류",
            data=_csv_to_xlsx(csv_content),
            file_name="검증오류.xlsx",
            mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
            key="dl_issues",
        )

    # 원가구성 비교 차트 (5번 섹션)를 Excel 네이티브 차트로 내보내기
    exp_col6 = st.columns(1)
    with exp_col6[0]:
        st.download_button(
            "📊 원가구성 비교 차트 (Excel 그래프)",
            data=exporter.export_chart_excel(
                st.session_state.scenarios,
                unit=st.session_state.unit,
                decimals=st.session_state.decimals,
            ),
            file_name="원가구성비교차트.xlsx",
            mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
            key="dl_chart",
        )

# ─── 7. 분류 규칙 관리 ───────────────────────────────────────
with st.expander("📖 분류 규칙 관리"):
    rules = st.session_state.rule_store.get_rules()
    if rules:
        st.markdown("**현재 규칙**")
        rules_df = pd.DataFrame(
            [{"키워드": k, "분류": v} for k, v in rules.items()]
        )
        st.dataframe(rules_df, use_container_width=True, hide_index=True)

        # 규칙 삭제
        del_kw = st.selectbox(
            "삭제할 규칙", list(rules.keys()), key="del_rule"
        )
        if st.button("🗑️ 규칙 삭제", key="btn_del_rule") and del_kw:
            st.session_state.rule_store.delete_rule(del_kw)
            st.session_state.classifier.user_rules = (
                st.session_state.rule_store.get_rules()
            )
            st.rerun()

        # 규칙 내보내기
        if st.button("📤 규칙 내보내기 (JSON)", key="btn_exp_rules"):
            st.download_button(
                "다운로드",
                data=st.session_state.rule_store.export_rules(),
                file_name="classification_rules.json",
                mime="application/json",
                key="dl_rules",
            )
    else:
        st.info("저장된 규칙이 없습니다. 분류를 수정하면 자동으로 학습됩니다.")

    # 수동 규칙 추가
    st.markdown("**규칙 수동 추가**")
    r_col1, r_col2, r_col3 = st.columns([2, 2, 1])
    with r_col1:
        new_kw = st.text_input("키워드", key="rule_kw")
    with r_col2:
        new_cat = st.selectbox("분류", COST_CATEGORIES, key="rule_cat")
    with r_col3:
        if st.button("➕ 추가", key="btn_add_rule") and new_kw.strip():
            st.session_state.rule_store.add_rule(new_kw.strip(), new_cat)
            st.session_state.classifier.user_rules = (
                st.session_state.rule_store.get_rules()
            )
            st.rerun()

    # 적용 이력
    history = st.session_state.rule_store.get_history(10)
    if history:
        st.markdown("**최근 이력**")
        for h in reversed(history):
            st.caption(
                f"{h['timestamp'][:16]} | {h['action']} | "
                f"'{h['keyword']}' → {h['category']}"
            )

# ─── 7. 분석 도우미 (LLM 챗봇) ───────────────────────────────
st.subheader("7. 분석 도우미")

CHAT_API_URL = "https://bai.hpc.lge.com:10602/api/v1/chat/completions"
CHAT_API_KEY = "sk-9370684cc9794f03b2b951b02bab8d98"
CHAT_MODEL = "Qwen/Qwen3.8-27B-FP8"


def _build_chat_context() -> str:
    """현재 분석 데이터를 LLM 컨텍스트로 구성"""
    ctx = "## 비교안 집계\n"
    for s in st.session_state.scenarios:
        cats = ", ".join(
            f"{c} {v:,.0f}" for c, v in s.category_totals.items() if v != 0
        )
        ctx += f"- {s.name}: 총 {s.total_amount:,.0f}원 ({cats})\n"
    ctx += "\n## 견적 항목 목록 (번호 = 표의 행 순서)\n"
    for i, it in enumerate(all_items, 1):
        ctx += (
            f"{i}. [행{it.source_row}] {it.name[:30]} | "
            f"{it.amount:,.0f}원 | {it.final_category}\n"
        )
    return ctx


def _chat_system_prompt() -> str:
    return (
        '너는 "원가구성 비교 분석 도구"의 분석 도우미다. '
        "사용자의 요청에 따라 분석 데이터를 조회하거나 수정한다.\n\n"
        f"사용 가능한 비용 분류: {', '.join(COST_CATEGORIES)}\n\n"
        f"## 현재 분석 데이터\n{_build_chat_context()}\n\n"
        "## 규칙\n"
        "1. 항상 한국어로 간결하게 답한다.\n"
        '2. "N번째 항목"은 위 목록의 번호 N을 의미한다. "N~M번"은 N부터 M까지의 항목을 의미한다.\n'
        "3. 항목의 분류를 수정해 달라는 요청이면, 답의 마지막 줄에 반드시 아래 형식의 ACTION 줄을 포함하라:\n"
        'ACTION: {"action":"reclassify","indices":[50],"category":"기구 구매품"}\n'
        "   - indices는 수정할 항목 번호 배열, category는 위 분류 중 하나\n"
        "4. 조회 요청(총액, 미분류 목록 등)이면 ACTION 없이 텍스트로만 답한다.\n"
        "5. 데이터에 없는 요청이면 그렇게 알려준다."
    )


def _send_chat_llm(messages: list) -> str:
    """LLM API 호출"""
    import urllib.request
    import json as _json

    req = urllib.request.Request(
        CHAT_API_URL,
        data=_json.dumps({
            "model": CHAT_MODEL,
            "messages": messages,
            "max_tokens": 1500,
            "temperature": 0,
        }).encode(),
        headers={
            "Content-Type": "application/json",
            "Authorization": f"Bearer {CHAT_API_KEY}",
        },
        method="POST",
    )
    with urllib.request.urlopen(req, timeout=60) as resp:
        data = _json.loads(resp.read())
    return (
        data.get("choices", [{}])[0]
        .get("message", {})
        .get("content", "")
    )


# 채팅 히스토리 표시
if st.session_state.chat_history:
    for msg in st.session_state.chat_history:
        with st.chat_message(msg["role"]):
            st.markdown(msg["content"])

# 채팅 입력
chat_input = st.chat_input(
    "예: 50번째 항목은 전장 구매품으로 / 미분류 항목 목록 / 전장 구매품 총액",
    disabled=not st.session_state.scenarios,
)

if chat_input and st.session_state.scenarios:
    # 사용자 메시지 표시
    with st.chat_message("user"):
        st.markdown(chat_input)

    # LLM 호출
    with st.chat_message("assistant"):
        with st.spinner("분석 중…"):
            try:
                messages = [
                    {"role": "system", "content": _chat_system_prompt()},
                    *st.session_state.chat_history[-8:],
                    {"role": "user", "content": chat_input},
                ]
                content = _send_chat_llm(messages)
                if not content:
                    content = "⚠️ 응답이 비어 있습니다. 다시 시도해 주세요."

                # ACTION 추출 + 실행
                import re as _re
                m = _re.search(r"ACTION:\s*(\{[\s\S]*\})", content)
                reply = _re.sub(r"ACTION:\s*\{[\s\S]*\}", "", content).strip()
                if m:
                    import json as _json2
                    try:
                        act = _json2.loads(m.group(1))
                        if (
                            act.get("action") == "reclassify"
                            and isinstance(act.get("indices"), list)
                            and act.get("category") in COST_CATEGORIES
                        ):
                            n = 0
                            for idx in act["indices"]:
                                it = all_items[idx - 1] if 1 <= idx <= len(all_items) else None
                                if it:
                                    it.final_category = act["category"]
                                    it.is_modified = True
                                    st.session_state.rule_store.add_rule(
                                        it.name[:20], act["category"]
                                    )
                                    n += 1
                            st.session_state.classifier.user_rules = (
                                st.session_state.rule_store.get_rules()
                            )
                            reply += (
                                f"\n✅ {n}개 항목을 \"{act['category']}\"(으)로 수정했습니다."
                                if n
                                else "\n⚠️ 해당하는 항목을 찾지 못했습니다."
                            )
                    except _json2.JSONDecodeError:
                        pass

                st.markdown(reply)

            except Exception as e:
                st.error(f"⚠️ {e}")
                reply = f"⚠️ {e}"

    # 히스토리 저장
    st.session_state.chat_history.append({"role": "user", "content": chat_input})
    st.session_state.chat_history.append({"role": "assistant", "content": reply})
    if len(st.session_state.chat_history) > 12:
        st.session_state.chat_history = st.session_state.chat_history[-12:]

elif not st.session_state.scenarios:
    st.info("📁 먼저 파일을 업로드하고 **분석 시작**을 눌러주세요.")

# ─── 푸터 ────────────────────────────────────────────────────
st.divider()
st.caption(
    f"🔒 로컬 처리 | 분석 일시: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')} | "
    f"사급품: {st.session_state.supply_option} | "
    f"단위: {st.session_state.unit}"
)
