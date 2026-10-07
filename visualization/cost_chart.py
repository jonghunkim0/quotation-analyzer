"""
visualization/cost_chart.py - 원가구성 비교 대시보드 차트 (Plotly)

첨부 예시 이미지와 유사한 구조:
- 세로 누적 막대 (비교안별)
- 상단 KPI (총액, 분석 원가, 재료비율)
- 재료비율 추세선 (보조 Y축)
- 비교안 간 동일 분류 경계 연결선
- 선택 비교안 강조 테두리
- 세그먼트 금액/구성비 레이블
- 증감 Callout
"""
import plotly.graph_objects as go
from plotly.subplots import make_subplots
from typing import Optional
from models.data_models import Scenario
from config import (
    CATEGORY_COLORS,
    DEFAULT_STACK_ORDER,
    MATERIAL_RATE_LINE_COLOR,
    HIGHLIGHT_BORDER_COLOR,
    INCREASE_COLOR,
    DECREASE_COLOR,
)
from utils.helpers import format_amount, safe_divide

# 그룹 표시명 (데이터 키와 다른 표시용)
GROUP_DISPLAY_NAMES = {"재료비": "재료비(가공품)"}


class CostCompositionChart:
    """원가구성 비교 대시보드 차트 생성기"""

    def __init__(
        self,
        scenarios: list,
        unit: str = "백만원",
        decimals: int = 1,
        stack_order: Optional[list] = None,
        highlight_scenario: str = "구매 목표가",
        show_material_rate: bool = True,
        show_connection_lines: bool = True,
        show_deltas: bool = True,
        show_supply: bool = True,
        show_unclassified: bool = True,
        hide_zero_supply: bool = False,
        dim_unselected: bool = True,
    ):
        self.scenarios = scenarios
        self.unit = unit
        self.decimals = decimals
        self.stack_order = stack_order or list(DEFAULT_STACK_ORDER)
        self.highlight = highlight_scenario
        self.show_material_rate = show_material_rate
        self.show_connection_lines = show_connection_lines
        self.show_deltas = show_deltas
        self.show_supply = show_supply
        self.show_unclassified = show_unclassified
        self.hide_zero_supply = hide_zero_supply
        self.dim_unselected = dim_unselected

    # ─── 표시 단위 변환 ──────────────────────────────────────
    def _unit_divisor(self) -> float:
        return {
            "원": 1,
            "천원": 1_000,
            "백만원": 1_000_000,
            "억원": 100_000_000,
        }.get(self.unit, 1)

    def _fmt(self, amount: float) -> str:
        return format_amount(amount, self.unit, self.decimals)

    def _to_unit(self, amount: float) -> float:
        return amount / self._unit_divisor()

    # ─── 표시할 분류 필터 ────────────────────────────────────
    def _visible_categories(self) -> list:
        cats = []
        for cat in self.stack_order:
            if cat == "미분류" and not self.show_unclassified:
                continue
            if cat == "사급품" and not self.show_supply:
                continue
            if cat == "사급품" and self.hide_zero_supply:
                # 모든 비교안에서 0이면 숨김
                if all(
                    s.category_totals.get("사급품", 0) == 0 for s in self.scenarios
                ):
                    continue
            cats.append(cat)
        return cats

    # ─── 1차: 그룹별 합계 계산 ────────────────────────────────
    def _group_totals(self) -> tuple:
        """1차 차트용 그룹 합계 계산
        Returns: (group_order, group_totals, group_colors)
        """
        from config import COST_GROUPS

        group_order = ["사급품", "구매품", "재료비", "인건비", "경비", "기타"]
        group_colors = {
            "사급품": "#0D9488",
            "구매품": "#4472C4",
            "재료비": "#5B9BD5",
            "인건비": "#C0504D",
            "경비": "#9BBB59",
            "기타": "#8064A2",
        }

        # 1차 그룹 → 포함할 21개 분류 매핑
        group_map = {
            "사급품": ["사급품"],
            "구매품": ["기구 구매품", "제어 구매품", "전장 구매품"],
            "재료비": ["기구 가공품", "전장 가공품"],
            "인건비": [
                "인건비-기구 설계", "인건비-전장 설계", "인건비-제어 설계",
                "인건비-기구 조립", "인건비-전장/제어 조립",
                "인건비-기구 셋업", "인건비-전장/제어 셋업",
                "인건비-기구 양산대응", "인건비-전장/제어 양산대응",
                "인건비-특수제어",
            ],
            "경비": ["경비-포장", "경비-기타", "경비-숙박/교통/항공"],
            "기타": ["마진", "미분류"],
        }

        n_scen = len(self.scenarios)
        group_totals = {g: [0.0] * n_scen for g in group_order}
        for i, s in enumerate(self.scenarios):
            for g_name, cats in group_map.items():
                for cat in cats:
                    group_totals[g_name][i] += self._to_unit(
                        s.category_totals.get(cat, 0.0)
                    )

        return group_order, group_totals, group_colors

    # ─── 2차: 세부 분류 합계 계산 ─────────────────────────────
    def _detail_totals(self) -> tuple:
        """2차 차트용 세부 분류 합계 계산
        Returns: (detail_order, detail_totals, detail_colors)
        """
        detail_order = [
            "기구 구매품", "제어 구매품", "전장 구매품",
            "기구 가공품", "전장 가공품",
            "인건비-기구 설계", "인건비-전장 설계", "인건비-제어 설계",
            "인건비-기구 조립", "인건비-전장/제어 조립",
            "인건비-기구 셋업", "인건비-전장/제어 셋업",
            "인건비-기구 양산대응", "인건비-전장/제어 양산대응",
            "인건비-특수제어",
            "경비-포장", "경비-기타", "경비-숙박/교통/항공",
        ]
        detail_colors = {
            "기구 구매품": "#4472C4",
            "제어 구매품": "#5B9BD5",
            "전장 구매품": "#8FAADC",
            "기구 가공품": "#A5A5A5",
            "전장 가공품": "#C0504D",
            "인건비-기구 설계": "#F79646",
            "인건비-전장 설계": "#FDB26E",
            "인건비-제어 설계": "#FFD966",
            "인건비-기구 조립": "#9BBB59",
            "인건비-전장/제어 조립": "#BDDA7E",
            "인건비-기구 셋업": "#255E91",
            "인건비-전장/제어 셋업": "#4472C4",
            "인건비-기구 양산대응": "#8064A2",
            "인건비-전장/제어 양산대응": "#977DAB",
            "인건비-특수제어": "#4BACC6",
            "경비-포장": "#F2F2F2",
            "경비-기타": "#D9D9D9",
            "경비-숙박/교통/항공": "#BFBFBF",
        }

        n_scen = len(self.scenarios)
        detail_totals = {c: [0.0] * n_scen for c in detail_order}
        for i, s in enumerate(self.scenarios):
            for cat in detail_order:
                detail_totals[cat][i] = self._to_unit(
                    s.category_totals.get(cat, 0.0)
                )

        return detail_order, detail_totals, detail_colors

    # ─── 공통: 누적 막대 + 레이블 생성 ────────────────────────
    def _build_stacked_bar(
        self,
        fig: go.Figure,
        order: list,
        totals: dict,
        colors: dict,
        x_labels: list,
        title: str,
        height: int = 500,
        display_names: Optional[dict] = None,
    ) -> go.Figure:
        """공통 누적 막대 그래프 생성"""
        display_names = display_names or {}
        n_scen = len(x_labels)
        cumulative = [0.0] * n_scen

        for name in order:
            disp = display_names.get(name, name)
            values = totals[name]
            if all(v == 0 for v in values):
                continue

            base = list(cumulative)
            # hover에 실제 금액 표시 (customdata)
            customdata = [[f"{v:.{self.decimals}f} {self.unit}"] for v in values]
            fig.add_trace(
                go.Bar(
                    x=x_labels,
                    y=values,
                    name=disp,
                    orientation="v",
                    base=base,
                    marker_color=colors.get(name, "#999999"),
                    customdata=customdata,
                    hovertemplate=(
                        f"<b>%{{x}}</b><br>"
                        f"분류: {disp}<br>"
                        f"금액: %{{customdata[0]}}<br>"
                        "<extra></extra>"
                    ),
                    legendgroup=name,
                ),
            )

            for i in range(n_scen):
                cumulative[i] = base[i] + values[i]

        # 세그먼트 레이블
        for name in order:
            values = totals[name]
            if all(v == 0 for v in values):
                continue
            # base 재계산
            seg_base = [0.0] * n_scen
            for prev in order:
                if prev == name:
                    break
                for i in range(n_scen):
                    seg_base[i] += totals[prev][i]

            for i in range(n_scen):
                val = values[i]
                if val == 0:
                    continue
                total = cumulative[i]
                ratio = (val / total * 100) if total > 0 else 0
                y_pos = seg_base[i] + val / 2
                label = f"{val:.1f}{self.unit} ({ratio:.1f}%)"
                fig.add_annotation(
                    x=i,
                    y=y_pos,
                    text=label,
                    showarrow=False,
                    font=dict(size=10, color="black"),
                    xanchor="center",
                    yanchor="middle",
                )

        max_y = max(cumulative) if cumulative else 1
        grand_total = sum(cumulative) if cumulative else 0.0
        # cumulative는 이미 _to_unit()으로 단위 변환된 값 → _fmt 사용 불가
        fig.update_layout(
            title=dict(
                text=title,
                x=0.5,
                xanchor="center",
                font=dict(size=16),
                subtitle=dict(
                    text=f"총합계: {grand_total:,.{self.decimals}f}{self.unit}",
                    font=dict(size=11, color="gray"),
                ),
            ),
            xaxis=dict(title=""),
            yaxis=dict(
                title=f"금액 ({self.unit})",
                range=[0, max_y * 1.15],
            ),
            barmode="stack",
            legend=dict(
                orientation="h",
                yanchor="bottom",
                y=-0.2,
                xanchor="center",
                x=0.5,
                font=dict(size=10),
            ),
            height=height,
            margin=dict(l=60, r=30, t=70, b=100),
            hovermode="closest",
        )

        return fig

    def build(self) -> go.Figure:
        """1차 차트: 비용 그룹 비교 (사급품/구매품/재료비/인건비/경비/기타)"""
        fig = go.Figure()
        x_labels = [s.name for s in self.scenarios]
        group_order, group_totals, group_colors = self._group_totals()
        return self._build_stacked_bar(
            fig, group_order, group_totals, group_colors, x_labels,
            title="① 1차: 비용 그룹 비교 (사급품 / 구매품 / 재료비(가공품) / 인건비 / 경비 / 기타)",
            display_names=GROUP_DISPLAY_NAMES,
        )

    def build_detail(self) -> list:
        """2차 차트: 구매품/재료비/인건비/경비 각각의 세부 분류 막대 그래프"""
        from plotly.subplots import make_subplots

        detail_order, detail_totals, detail_colors = self._detail_totals()
        x_labels = [s.name for s in self.scenarios]

        # 4개 그룹으로 분리
        sub_groups = {
            "구매품": ["기구 구매품", "제어 구매품", "전장 구매품"],
            "재료비": ["기구 가공품", "전장 가공품"],
            "인건비": [
                "인건비-기구 설계", "인건비-전장 설계", "인건비-제어 설계",
                "인건비-기구 조립", "인건비-전장/제어 조립",
                "인건비-기구 셋업", "인건비-전장/제어 셋업",
                "인건비-기구 양산대응", "인건비-전장/제어 양산대응",
                "인건비-특수제어",
            ],
            "경비": ["경비-포장", "경비-기타", "경비-숙박/교통/항공"],
        }

        figs = []
        for group_name, cats in sub_groups.items():
            # 이 그룹에 데이터가 있는지 확인
            has_data = any(
                detail_totals[cat][i] != 0
                for cat in cats
                for i in range(len(x_labels))
            )
            if not has_data:
                continue

            disp = GROUP_DISPLAY_NAMES.get(group_name, group_name)
            fig = go.Figure()
            # 이 그룹의 세부 분류만 누적 막대로
            cumulative = [0.0] * len(x_labels)
            for cat in cats:
                values = detail_totals[cat]
                if all(v == 0 for v in values):
                    continue
                base = list(cumulative)
                customdata = [[f"{v:.{self.decimals}f} {self.unit}"] for v in values]
                fig.add_trace(
                    go.Bar(
                        x=x_labels,
                        y=values,
                        name=cat,
                        orientation="v",
                        base=base,
                        marker_color=detail_colors.get(cat, "#999999"),
                        customdata=customdata,
                        hovertemplate=(
                            f"<b>%{{x}}</b><br>"
                            f"분류: {cat}<br>"
                            f"금액: %{{customdata[0]}}<br>"
                            "<extra></extra>"
                        ),
                        legendgroup=cat,
                    ),
                )
                for i in range(len(x_labels)):
                    cumulative[i] = base[i] + values[i]

            # 세그먼트 레이블
            for cat in cats:
                values = detail_totals[cat]
                if all(v == 0 for v in values):
                    continue
                seg_base = [0.0] * len(x_labels)
                for prev in cats:
                    if prev == cat:
                        break
                    for i in range(len(x_labels)):
                        seg_base[i] += detail_totals[prev][i]
                for i in range(len(x_labels)):
                    val = values[i]
                    if val == 0:
                        continue
                    total = cumulative[i]
                    ratio = (val / total * 100) if total > 0 else 0
                    y_pos = seg_base[i] + val / 2
                    label = f"{val:.1f}{self.unit} ({ratio:.1f}%)"
                    fig.add_annotation(
                        x=i, y=y_pos, text=label,
                        showarrow=False,
                        font=dict(size=10, color="black"),
                        xanchor="center", yanchor="middle",
                    )

            max_y = max(cumulative) if cumulative else 1
            grand_total = sum(cumulative) if cumulative else 0.0
            # cumulative는 이미 _to_unit()으로 단위 변환된 값 → _fmt 사용 불가
            fig.update_layout(
                title=dict(
                    text=f"② 2차: {disp} 세부 분류",
                    x=0.5,
                    xanchor="center",
                    font=dict(size=14),
                    subtitle=dict(
                        text=f"총합계: {grand_total:,.{self.decimals}f}{self.unit}",
                        font=dict(size=11, color="gray"),
                    ),
                ),
                xaxis=dict(title=""),
                yaxis=dict(title=f"금액 ({self.unit})", range=[0, max_y * 1.15]),
                barmode="stack",
                legend=dict(
                    orientation="h", yanchor="bottom", y=-0.25,
                    xanchor="center", x=0.5, font=dict(size=9),
                ),
                height=400,
                margin=dict(l=60, r=30, t=50, b=90),
                hovermode="closest",
            )
            figs.append(fig)

        return figs

    # ─── 세그먼트 레이블 ─────────────────────────────────────
    def _add_segment_labels(self, fig, cats, x_labels):
        visible = self._visible_categories()

        # 각 비교안의 총 높이 계산 (레이블 크기 판단용)
        totals = []
        for s in self.scenarios:
            t = 0.0
            for c in visible:
                t += self._to_unit(s.category_totals.get(c, 0.0))
            totals.append(t)
        max_total = max(totals) if totals else 1.0
        if max_total == 0:
            max_total = 1.0

        for cat in cats:
            cat_idx = cats.index(cat)
            for i, s in enumerate(self.scenarios):
                val = s.category_totals.get(cat, 0.0)
                if val == 0:
                    continue
                ratio = s.category_ratios.get(cat, 0.0)

                # 이 분류의 누적 기준선 (이전 분류들의 합)
                base = 0.0
                for c in visible[:cat_idx]:
                    base += self._to_unit(s.category_totals.get(c, 0.0))
                y_pos = base + self._to_unit(val) / 2

                # 세그먼트 높이에 따라 레이블 크기 결정
                seg_height = self._to_unit(val)
                if seg_height > max_total * 0.04:
                    label = self._fmt(val) + "\n" + f"{ratio:.1f}%"
                    font_size = 9
                else:
                    label = self._fmt(val)
                    font_size = 7

                fig.add_annotation(
                    x=i,
                    y=y_pos,
                    text=label,
                    showarrow=False,
                    font=dict(size=font_size, color="white"),
                    xanchor="center",
                    yanchor="middle",
                )

    # ─── 상단 KPI ────────────────────────────────────────────
    def _add_kpi(self, fig, x_labels):
        for i, s in enumerate(self.scenarios):
            total = self._to_unit(s.total_amount)
            analysis = self._to_unit(s.analysis_cost)
            mat_rate = s.material_rate
            kpi_text = (
                f"총액 {self._fmt(s.total_amount)}<br>"
                f"분석원가 {self._fmt(s.analysis_cost)}<br>"
                f"재료비율 {mat_rate:.1f}%"
            )
            is_highlight = (s.name == self.highlight)
            fig.add_annotation(
                x=i,
                y=total * 1.05,
                text=kpi_text,
                showarrow=False,
                font=dict(
                    size=11 if is_highlight else 10,
                    weight="bold" if is_highlight else "normal",
                ),
                xanchor="center",
                yanchor="bottom",
                align="center",
            )

    # ─── 재료비율 추세선 ─────────────────────────────────────
    def _add_material_rate_line(self, fig, x_labels):
        rates = [s.material_rate for s in self.scenarios]
        fig.add_trace(
            go.Scatter(
                x=x_labels,
                y=rates,
                mode="lines+markers+text",
                name="재료비율",
                line=dict(color=MATERIAL_RATE_LINE_COLOR, width=2.5, dash="dot"),
                marker=dict(size=9, color=MATERIAL_RATE_LINE_COLOR),
                text=[f"{r:.1f}%" for r in rates],
                textposition="top center",
                textfont=dict(size=10, color=MATERIAL_RATE_LINE_COLOR),
                hovertemplate=(
                    "<b>%{x}</b><br>재료비율: %{y:.1f}%<extra></extra>"
                ),
            ),
            secondary_y=True,
        )

    # ─── 비교안 간 연결선 ────────────────────────────────────
    def _add_connection_lines(self, fig, cats, x_labels):
        n = len(self.scenarios)
        # 각 분류의 상단 경계를 인접 비교안 간 연결
        for cat in cats:
            tops = []
            for i, s in enumerate(self.scenarios):
                # 이 분류까지의 누적 상단
                cum = 0.0
                for c in self._visible_categories():
                    if c == cat:
                        break
                    cum += self._to_unit(s.category_totals.get(c, 0.0))
                cum += self._to_unit(s.category_totals.get(cat, 0.0))
                tops.append(cum)
            # 인접 연결
            for i in range(n - 1):
                fig.add_shape(
                    type="line",
                    x0=i,
                    y0=tops[i],
                    x1=i + 1,
                    y1=tops[i + 1],
                    line=dict(color="#D1D5DB", width=1, dash="dash"),
                    layer="below",
                    secondary_y=False,
                )

    # ─── 증감 Callout ────────────────────────────────────────
    def _add_delta_callouts(self, fig, x_labels):
        n = len(self.scenarios)
        for i in range(n - 1):
            prev = self.scenarios[i]
            curr = self.scenarios[i + 1]
            # 증감 가장 큰 상위 3개 분류만 표시
            deltas = []
            for cat in self._visible_categories():
                pv = prev.category_totals.get(cat, 0.0)
                cv = curr.category_totals.get(cat, 0.0)
                d = cv - pv
                if d != 0:
                    rate = safe_divide(d, abs(pv)) * 100 if pv != 0 else 0
                    deltas.append((cat, d, rate))
            deltas.sort(key=lambda x: abs(x[1]), reverse=True)
            top3 = deltas[:3]

            if not top3:
                continue

            x_mid = i + 0.5
            y_base = max(
                self._to_unit(prev.total_amount),
                self._to_unit(curr.total_amount),
            ) * 1.12

            lines = []
            for cat, d, rate in top3:
                arrow = "▲" if d > 0 else "▼"
                color = INCREASE_COLOR if d > 0 else DECREASE_COLOR
                lines.append(
                    f"<span style='color:{color}'>{arrow} {cat} "
                    f"{self._fmt(d)} ({rate:+.1f}%)</span>"
                )
            fig.add_annotation(
                x=x_mid,
                y=y_base,
                text="<br>".join(lines),
                showarrow=False,
                font=dict(size=9),
                xanchor="center",
                yanchor="bottom",
                align="center",
                bgcolor="rgba(255,255,255,0.85)",
                bordercolor="#E5E7EB",
                borderwidth=1,
            )

    # ─── 선택 안 흐림 ────────────────────────────────────────
    def _dim_unselected(self, fig):
        # 막대 trace의 opacity 조정 (단순화: 전체 유지, 강조는 테두리로)
        pass

    # ─── 이미지 저장 ─────────────────────────────────────────
    def save_png(self, fig: go.Figure, path: str):
        fig.write_image(path, scale=2)
