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

    def build(self) -> go.Figure:
        """차트 Figure 생성"""
        fig = make_subplots(specs=[[{"secondary_y": self.show_material_rate}]])

        visible_cats = self._visible_categories()
        n_scen = len(self.scenarios)
        x_labels = [s.name for s in self.scenarios]

        # ── 1. 누적 막대 ──────────────────────────────────────
        cumulative = [0.0] * n_scen  # 각 비교안의 누적 상단 (연결선용)
        cat_top_bounds = {}  # {category: [top_bound per scenario]}
        cat_bottom_bounds = {}

        for cat in visible_cats:
            values = []
            for s in self.scenarios:
                val = s.category_totals.get(cat, 0.0)
                values.append(self._to_unit(val))

            # 누적 기준 (이전 분류들의 합)
            base = list(cumulative)
            # 막대 추가
            fig.add_trace(
                go.Bar(
                    x=x_labels,
                    y=values,
                    name=cat,
                    orientation="v",
                    base=base,
                    marker_color=CATEGORY_COLORS.get(cat, "#999999"),
                    hovertemplate=(
                        f"<b>%{{x}}</b><br>"
                        f"분류: {cat}<br>"
                        f"금액: %{{y:.{self.decimals}f}} {self.unit}<br>"
                        "<extra></extra>"
                    ),
                    legendgroup=cat,
                ),
                secondary_y=False,
            )

            # 누적 경계 기록
            tops = []
            bottoms = []
            for i in range(n_scen):
                bottoms.append(base[i])
                tops.append(base[i] + values[i])
            cat_top_bounds[cat] = tops
            cat_bottom_bounds[cat] = bottoms
            for i in range(n_scen):
                cumulative[i] = base[i] + values[i]

        # ── 2. 선택 비교안 강조 테두리 ────────────────────────
        if self.highlight in x_labels:
            idx = x_labels.index(self.highlight)
            max_val = cumulative[idx]
            fig.add_shape(
                type="rect",
                x0=idx - 0.4,
                x1=idx + 0.4,
                y0=0,
                y1=max_val * 1.02,
                line=dict(color=HIGHLIGHT_BORDER_COLOR, width=3),
                fillcolor="rgba(220,38,38,0.04)",
                layer="above",
                secondary_y=False,
            )

        # ── 3. 세그먼트 레이블 (금액 + 구성비) ────────────────
        self._add_segment_labels(fig, visible_cats, x_labels)

        # ── 4. 상단 KPI ───────────────────────────────────────
        self._add_kpi(fig, x_labels)

        # ── 5. 재료비율 추세선 (보조 Y축) ─────────────────────
        if self.show_material_rate:
            self._add_material_rate_line(fig, x_labels)

        # ── 6. 비교안 간 연결선 ───────────────────────────────
        if self.show_connection_lines:
            self._add_connection_lines(fig, visible_cats, x_labels)

        # ── 7. 증감 Callout ───────────────────────────────────
        if self.show_deltas:
            self._add_delta_callouts(fig, x_labels)

        # ── 8. 축 설정 ────────────────────────────────────────
        max_y = max(cumulative) if cumulative else 1
        fig.update_layout(
            title=dict(
                text="원가구성 비교 대시보드",
                x=0.5,
                font=dict(size=20),
            ),
            xaxis=dict(title="비교안"),
            yaxis=dict(
                title=f"금액 ({self.unit})",
                range=[0, max_y * 1.35],  # KPI 공간 확보
            ),
            legend=dict(
                orientation="h",
                yanchor="bottom",
                y=1.02,
                xanchor="right",
                x=1,
            ),
            height=700,
            margin=dict(l=60, r=60, t=120, b=60),
            hovermode="closest",
        )

        if self.show_material_rate:
            fig.update_layout(
                yaxis2=dict(
                    title="재료비율 (%)",
                    overlaying="y",
                    side="right",
                    range=[0, 100],
                    showgrid=False,
                )
            )

        # 선택하지 않은 비교안 흐림 처리 (막대 투명도)
        if self.dim_unselected and self.highlight in x_labels:
            self._dim_unselected(fig)

        return fig

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
