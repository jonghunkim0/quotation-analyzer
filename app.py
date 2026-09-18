"""
app.py - 원가구성 비교 분석 도구 (Streamlit 메인 앱)

실행: streamlit run app.py
"""
import os
import sys
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
from utils.helpers import format_amount, auto_detect_unit

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


# ─── 헬퍼 함수 ───────────────────────────────────────────────
def process_uploaded_file(uploaded_file) -> QuotationFile:
    """업로드된 파일을 파싱"""
    filename = uploaded_file.name
    ext = Path(filename).suffix.lower()

    if ext not in SUPPORTED_EXTENSIONS:
        qf = QuotationFile(
            file_id=f"file_{id(uploaded_file)}",
            filename=filename,
            file_type="unknown",
            status=FileStatus.ERROR,
            error_message=f"지원하지 않는 형식: {ext}",
        )
        return qf

    # 임시 파일로 저장
    import tempfile
    import os
    with tempfile.NamedTemporaryFile(
        delete=False, suffix=ext
    ) as tmp:
        tmp.write(uploaded_file.getvalue())
        tmp_path = tmp.name

    try:
        if ext in (".xlsx", ".xls"):
            parser = ExcelParser()
            sheets = parser.list_sheets(tmp_path)
            # 첫 시트 자동 선택
            selected = sheets[0] if sheets else ""
            qf = parser.parse_sheet(tmp_path, selected, filename)
            qf.sheets = sheets
        elif ext == ".pdf":
            parser = PDFParser()
            qf = parser.parse(tmp_path, filename)
    except Exception as e:
        qf = QuotationFile(
            file_id=f"file_{id(uploaded_file)}",
            filename=filename,
            file_type="excel" if ext in (".xlsx", ".xls") else "pdf",
            status=FileStatus.ERROR,
            error_message=str(e),
        )
    finally:
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
st.title("📊 원가구성 비교 분석 도구")
st.caption(
    "Excel/PDF 견적서 업로드 → 자동 분류 → 원가구성 비교 차트"
)

# ─── 1. 파일 업로드 영역 ─────────────────────────────────────
st.subheader("1. 파일 업로드")

uploaded_files = st.file_uploader(
    "견적 파일을 선택하세요 (Excel: .xlsx, .xls / PDF: .pdf)",
    type=["xlsx", "xls", "pdf"],
    accept_multiple_files=True,
)

if uploaded_files:
    for uf in uploaded_files:
        if uf.name not in [
            f.filename for f in st.session_state.files.values()
        ]:
            with st.spinner(f"'{uf.name}' 분석 중..."):
                qf = process_uploaded_file(uf)
                st.session_state.files[qf.file_id] = qf

    # 새 파일이 추가되면 분류 실행
    run_classification()
    run_aggregation()

# 업로드 파일 목록
if st.session_state.files:
    col1, col2, col3 = st.columns([3, 2, 1])
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

    with col3:
        if st.button("🗑️ 전체 삭제", key="btn_clear_all"):
            st.session_state.files = {}
            st.session_state.scenario_mgr.init_default()
            st.session_state.scenarios = []
            st.session_state.deltas = []
            st.session_state.issues = []
            st.rerun()

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
    fig = chart.build()
    st.plotly_chart(fig, use_container_width=True)

    # 차트 PNG 저장
    if st.button("📷 차트 PNG 저장", key="btn_save_png"):
        try:
            fig.write_image(
                "cost_chart.png", scale=2
            )
            st.success("차트가 cost_chart.png로 저장되었습니다.")
        except Exception as e:
            st.error(f"PNG 저장 실패: {e}")
            st.info(
                "kaleido 패키지가 필요합니다: pip install kaleido"
            )

# ─── 6. 내보내기 ─────────────────────────────────────────────
st.subheader("6. 결과 내보내기")

if st.session_state.scenarios:
    exp_col1, exp_col2, exp_col3 = st.columns(3)

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

    with exp_col1:
        if st.button("📄 견적항목 CSV", key="btn_exp_items"):
            csv_content = exporter.export_items_csv(all_items)
            st.download_button(
                "다운로드",
                data=csv_content,
                file_name="견적항목.csv",
                mime="text/csv",
                key="dl_items",
            )
    with exp_col2:
        if st.button("📊 집계표 CSV", key="btn_exp_summary"):
            csv_content = exporter.export_summary_csv(
                st.session_state.scenarios
            )
            st.download_button(
                "다운로드",
                data=csv_content,
                file_name="집계표.csv",
                mime="text/csv",
                key="dl_summary",
            )
    with exp_col3:
        if st.button("📈 증감분석 CSV", key="btn_exp_delta"):
            csv_content = exporter.export_comparison_csv(
                st.session_state.scenarios, st.session_state.deltas
            )
            st.download_button(
                "다운로드",
                data=csv_content,
                file_name="증감분석.csv",
                mime="text/csv",
                key="dl_delta",
            )

    exp_col4, exp_col5 = st.columns(2)
    with exp_col4:
        if st.button("📑 전체 Excel 내보내기", key="btn_exp_excel"):
            import tempfile
            with tempfile.NamedTemporaryFile(
                suffix=".xlsx", delete=False
            ) as tmp:
                tmp_path = tmp.name
            exporter.export_excel(
                tmp_path,
                all_items,
                st.session_state.scenarios,
                st.session_state.deltas,
                st.session_state.issues,
            )
            with open(tmp_path, "rb") as f:
                data = f.read()
            st.download_button(
                "다운로드",
                data=data,
                file_name="원가분석_결과.xlsx",
                mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                key="dl_excel",
            )
            os.unlink(tmp_path)

    with exp_col5:
        if st.button("⚠️ 검증오류 CSV", key="btn_exp_issues"):
            csv_content = exporter.export_validation_csv(
                st.session_state.issues
            )
            st.download_button(
                "다운로드",
                data=csv_content,
                file_name="검증오류.csv",
                mime="text/csv",
                key="dl_issues",
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

# ─── 푸터 ────────────────────────────────────────────────────
st.divider()
st.caption(
    f"🔒 로컬 처리 | 분석 일시: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')} | "
    f"사급품: {st.session_state.supply_option} | "
    f"단위: {st.session_state.unit}"
)
