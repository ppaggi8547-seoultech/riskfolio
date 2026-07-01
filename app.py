"""다자산 포트폴리오 VaR 리스크 대시보드.

이 앱은 사용자가 입력한 한국주식, 미국주식, 원화 현금을 기반으로 생성된 CSV/PNG/TXT
산출물을 읽어 표시한다. 리스크 계산은 각 step 파일과 run_all.py가 수행하며, 앱은 명시적
버튼 클릭 시에만 run_all.main(interactive=False)을 호출한다.
"""

from __future__ import annotations

import json
import re
from datetime import date, datetime
from html import escape
from pathlib import Path
from typing import Any

import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
import streamlit as st

from config import (
    ASSET_MASTER_FILE,
    ASSET_RETURN_FILE,
    ASSET_RISK_SUMMARY_FILE,
    ASSET_STRESS_TEST_FILE,
    ASSET_VALUE_FILE,
    CHART_DIR,
    CORRELATION_FILE,
    DRAWDOWN_FILE,
    KR_PRICE_FILE,
    PORTFOLIO_CONFIG_FILE,
    PORTFOLIO_RETURNS_FILE,
    PORTFOLIO_VALUE_FILE,
    POSITION_SUMMARY_FILE,
    REPORT_FILE,
    RISK_SUMMARY_FILE,
    STRESS_TEST_FILE,
    US_PRICE_FILE,
    USD_KRW_FILE,
    VAR_BACKTEST_FILE,
    VAR_BACKTEST_SUMMARY_FILE,
)
from portfolio_input import save_portfolio_config

try:
    from run_all import main as run_all_main
except ImportError:
    run_all_main = None


KR_EDITOR_COLUMNS = ["종목코드", "수량", "매수가격_원"]
US_EDITOR_COLUMNS = ["티커", "수량", "매수가격_달러", "매수일자"]
NO_ANALYSIS_MESSAGE = "아직 분석 결과가 없습니다. Portfolio Input 탭에서 포트폴리오를 입력한 뒤 전체 분석 실행을 눌러주세요."


def configure_page() -> None:
    """대시보드 페이지 설정."""
    st.set_page_config(
        page_title="Riskfolio",
        page_icon="📊",
        layout="wide",
        initial_sidebar_state="expanded",
    )


def apply_custom_css() -> None:
    """배포용 화이트 테마와 카드형 대시보드 스타일을 적용한다."""
    # Note: st.data_editor uses an internal canvas/grid renderer, so some cell background styles may be controlled by Streamlit internals.
    st.markdown(
        """
        <style>
        :root {
            --rf-page-bg: #ffffff;
            --rf-panel-bg: #ffffff;
            --rf-table-bg: #f3f4f6;
            --rf-table-header-bg: #e5e7eb;
            --rf-table-hover-bg: #e0e7ff;
            --rf-text-main: #111827;
            --rf-text-muted: #4b5563;
            --rf-border: rgba(0, 0, 0, 0.32);
            --rf-border-soft: rgba(0, 0, 0, 0.18);
        }

        html {
            color-scheme: light;
        }

        .stApp,
        [data-testid="stAppViewContainer"] {
            background: var(--rf-page-bg) !important;
            color: var(--rf-text-main) !important;
        }

    

        .block-container {
            max-width: 1520px;
            padding-top: 1.6rem;
            padding-bottom: 2.5rem;
            background: var(--rf-page-bg) !important;
            color: var(--rf-text-main) !important;
        }

        html,
        body,
        p,
        span,
        div,
        label {
            color: inherit;
        }

        h1 {
            color: #111827 !important;
            font-size: clamp(2rem, 4vw, 3.4rem) !important;
            line-height: 1.18 !important;
            letter-spacing: -0.03em;
        }

        h2,
        h3,
        h4,
        h5,
        h6,
        [data-testid="stMarkdownContainer"],
        [data-testid="stCaptionContainer"] {
            color: #111827 !important;
        }

        .stApp p,
        .stApp span,
        .stApp label,
        [data-testid="stWidgetLabel"] {
            color: #111827 !important;
        }

        .dashboard-subtitle {
            color: #475569 !important;
            font-size: clamp(0.95rem, 1.5vw, 1.05rem);
            line-height: 1.65;
            max-width: 1050px;
            margin-bottom: 1.15rem;
            white-space: normal;
            overflow-wrap: anywhere;
        }

        .stTabs [data-baseweb="tab-list"] {
            gap: 0.35rem;
            margin-top: 0.45rem;
            margin-bottom: 0.45rem;
            border-bottom: 1px solid rgba(0, 0, 0, 0.18);
        }

        .stTabs [data-baseweb="tab"] {
            padding: 0.55rem 0.75rem;
            color: #334155 !important;
        }

        .stTabs [data-baseweb="tab"] p {
            color: #334155 !important;
        }

        .stTabs [aria-selected="true"] {
            color: #dc2626 !important;
            font-weight: 700 !important;
        }

        .stTabs [aria-selected="true"] p {
            color: #dc2626 !important;
            font-weight: 700 !important;
        }

        .stTabs [data-baseweb="tab-highlight"] {
            background-color: #dc2626 !important;
        }

        .section-title {
            border: 1px solid var(--rf-border) !important;
            border-left: 4px solid #dc2626 !important;
            border-radius: 10px;
            background: var(--rf-panel-bg) !important;
            padding: 0.55rem 0.9rem;
            margin: 0.9rem 0 1rem 0;
            font-size: 1.25rem;
            font-weight: 800;
            color: var(--rf-text-main) !important;
            box-shadow: none !important;
        }

        .section-title,
        .section-title h1,
        .section-title h2,
        .section-title h3,
        .section-title-text {
            color: var(--rf-text-main) !important;
        }

        .notice-box {
            background: var(--rf-panel-bg) !important;
            border: 1px solid var(--rf-border) !important;
            border-radius: 10px;
            padding: 0.9rem 1rem;
            color: var(--rf-text-main) !important;
            line-height: 1.6;
            margin-bottom: 1rem;
            box-shadow: none !important;
        }

        .stApp .notice-box * {
            color: var(--rf-text-main) !important;
        }

        .metric-grid {
            display: grid;
            grid-template-columns: repeat(4, minmax(0, 1fr));
            gap: 1rem;
            align-items: stretch;
            margin-top: 1rem;
            margin-bottom: 1.55rem;
        }

        .metric-card {
            background: var(--rf-panel-bg) !important;
            border: 1px solid var(--rf-border) !important;
            border-radius: 14px;
            padding: 1.1rem 1.2rem;
            min-height: 158px;
            height: 100%;
            box-sizing: border-box;
            display: flex;
            flex-direction: column;
            justify-content: space-between;
            box-shadow: none !important;
            min-width: 0;
            overflow: hidden;
        }

        .metric-card-top,
        .metric-card-bottom {
            min-width: 0;
            width: 100%;
        }

        .metric-card-bottom {
            margin-top: 0.75rem;
        }

        .metric-value-row {
            display: flex;
            align-items: baseline;
            gap: 0.12rem;
            flex-wrap: nowrap;
            width: 100%;
            min-width: 0;
            overflow: hidden;
            margin-top: 0.45rem;
        }

        .metric-label {
            font-size: 0.9rem;
            font-weight: 750;
            color: var(--rf-text-muted) !important;
            line-height: 1.25;
            word-break: keep-all;
            overflow-wrap: anywhere;
        }

        .metric-value-main {
            font-size: clamp(1.45rem, 2.05vw, 2.25rem);
            font-weight: 850;
            color: var(--rf-text-main) !important;
            line-height: 1.02;
            letter-spacing: -0.035em;
            white-space: nowrap;
            word-break: keep-all;
            overflow: hidden;
            text-overflow: clip;
            min-width: 0;
        }

        .metric-value-main.value-long {
            font-size: clamp(1.28rem, 1.72vw, 1.9rem);
            letter-spacing: -0.045em;
        }
        .metric-value-main.value-xlong {
            font-size: clamp(1.12rem, 1.45vw, 1.62rem);
            letter-spacing: -0.055em;
        }
        .metric-value-main.value-xxlong {
            font-size: clamp(0.98rem, 1.2vw, 1.38rem);
            letter-spacing: -0.065em;
        }

        .metric-value-unit {
            font-size: clamp(0.86rem, 0.95vw, 1.12rem);
            font-weight: 800;
            color: var(--rf-text-main) !important;
            line-height: 1;
            white-space: nowrap;
            flex-shrink: 0;
            letter-spacing: -0.02em;
        }

        .metric-card.profit-positive .metric-value-main,
        .metric-card.profit-positive .metric-value-unit {
            color: #dc2626 !important;
        }

        .metric-card.profit-negative .metric-value-main,
        .metric-card.profit-negative .metric-value-unit {
            color: #2563eb !important;
        }

        .metric-sub {
            margin-top: 0.6rem;
            font-size: 0.85rem;
            color: var(--rf-text-muted) !important;
            line-height: 1.3;
            word-break: keep-all;
            overflow-wrap: anywhere;
        }

        [data-testid="stDataFrame"],
        [data-testid="stDataFrame"] * {
            color: var(--rf-text-main) !important;
            -webkit-text-fill-color: var(--rf-text-main) !important;
        }

        [data-testid="stDataFrame"] {
            background: var(--rf-table-bg) !important;
            border: 1px solid var(--rf-border) !important;
            border-radius: 10px !important;
            box-shadow: none !important;
            overflow: hidden !important;
        }

        [data-testid="stDataFrame"] div {
            border-color: var(--rf-border-soft) !important;
        }

        table,
        thead,
        tbody,
        tr,
        th,
        td {
            color: var(--rf-text-main) !important;
            -webkit-text-fill-color: var(--rf-text-main) !important;
        }

        table {
            background: var(--rf-table-bg) !important;
            border-color: var(--rf-border) !important;
        }

        thead tr th {
            background: var(--rf-table-header-bg) !important;
            border-color: var(--rf-border) !important;
            font-weight: 700 !important;
        }

        tbody tr td {
            background: var(--rf-table-bg) !important;
            border-color: var(--rf-border-soft) !important;
        }

        tbody tr:hover td {
            background: var(--rf-table-hover-bg) !important;
        }

        [data-testid="stDataEditor"],
        [data-testid="stDataEditor"] * {
            color: var(--rf-text-main) !important;
            -webkit-text-fill-color: var(--rf-text-main) !important;
        }

        [data-testid="stDataEditor"] {
            background: var(--rf-table-bg) !important;
            border: 1px solid var(--rf-border) !important;
            border-radius: 10px !important;
            box-shadow: none !important;
            overflow: hidden !important;
        }

        [data-testid="stDataEditor"] * {
            border-color: var(--rf-border-soft) !important;
        }


        [data-testid="stDataEditor"] [role="columnheader"],
        [data-testid="stDataEditor"] .dvn-header,
        [data-testid="stDataEditor"] .dvn-cell-header,
        [data-testid="stDataFrame"] [role="columnheader"],
        [data-testid="stDataFrame"] .dvn-header,
        [data-testid="stDataFrame"] .dvn-cell-header {
            background: var(--rf-table-header-bg) !important;
            color: var(--rf-text-main) !important;
            -webkit-text-fill-color: var(--rf-text-main) !important;
            border-color: var(--rf-border) !important;
            font-weight: 700 !important;
        }

        [data-testid="stDataEditor"] [role="gridcell"],
        [data-testid="stDataEditor"] .dvn-cell,
        [data-testid="stDataEditor"] .dvn-cell-text,
        [data-testid="stDataFrame"] [role="gridcell"],
        [data-testid="stDataFrame"] .dvn-cell,
        [data-testid="stDataFrame"] .dvn-cell-text {
            background: var(--rf-table-bg) !important;
            color: var(--rf-text-main) !important;
            -webkit-text-fill-color: var(--rf-text-main) !important;
            border-color: var(--rf-border-soft) !important;
        }

        [data-testid="stDataEditor"] [role="gridcell"]:hover,
        [data-testid="stDataEditor"] .dvn-cell:hover,
        [data-testid="stDataFrame"] [role="gridcell"]:hover,
        [data-testid="stDataFrame"] .dvn-cell:hover {
            background: var(--rf-table-hover-bg) !important;
        }

        [data-testid="stDataEditor"] input,
        [data-testid="stDataEditor"] textarea,
        [data-testid="stDataFrame"] input,
        [data-testid="stDataFrame"] textarea {
            background: var(--rf-table-bg) !important;
            color: var(--rf-text-main) !important;
            -webkit-text-fill-color: var(--rf-text-main) !important;
            border-color: var(--rf-border) !important;
            caret-color: var(--rf-text-main) !important;
        }

        [data-testid="stDataEditor"] input::placeholder,
        [data-testid="stDataEditor"] textarea::placeholder,
        [data-testid="stDataFrame"] input::placeholder,
        [data-testid="stDataFrame"] textarea::placeholder {
            color: #6b7280 !important;
            -webkit-text-fill-color: #6b7280 !important;
            opacity: 1 !important;
        }

        [data-testid="stDataEditor"] canvas,
        [data-testid="stDataFrame"] canvas {
            background: var(--rf-table-bg) !important;
        }

        .glideDataEditor,
        .glideDataEditor *,
        .stDataFrameGlideDataEditor,
        .stDataFrameGlideDataEditor *,
        .dvn-scroller,
        .dvn-scroller *,
        .dvn-stack,
        .dvn-stack *,
        .dvn-underlay,
        .dvn-underlay *,
        .dvn-cell,
        .dvn-cell *,
        .dvn-cell-text,
        .dvn-cell-text *,
        .dvn-header,
        .dvn-header *,
        .dvn-cell-header,
        .dvn-cell-header * {
            color: var(--rf-text-main) !important;
            -webkit-text-fill-color: var(--rf-text-main) !important;
        }

        [data-testid="stSidebar"] {
            background: #ffffff !important;
            border-right: 1px solid rgba(0, 0, 0, 0.35);
        }

        [data-testid="stSidebar"] * {
            color: #111827;
        }

        .stButton > button,
        .stFormSubmitButton > button,
        .stDownloadButton > button {
            border: 1px solid rgba(0, 0, 0, 0.38) !important;
            background: #ffffff !important;
            color: #111827 !important;
            border-radius: 10px !important;
            box-shadow: none !important;
        }

        .stButton > button:hover,
        .stFormSubmitButton > button:hover,
        .stDownloadButton > button:hover {
            border-color: #dc2626 !important;
            color: #dc2626 !important;
            box-shadow: none !important;
        }

        button[kind="primary"],
        [data-testid="stBaseButton-primary"] {
            background: #dc2626 !important;
            color: #ffffff !important;
            border-color: #dc2626 !important;
            box-shadow: none !important;
        }

        button[kind="primary"] *,
        .stApp [data-testid="stBaseButton-primary"] * {
            color: #ffffff !important;
        }

        button[kind="primary"]:hover,
        [data-testid="stBaseButton-primary"]:hover {
            background: #b91c1c !important;
            color: #ffffff !important;
            box-shadow: none !important;
        }

        input,
        textarea,
        [data-baseweb="input"],
        [data-baseweb="base-input"] {
            background: var(--rf-table-bg) !important;
            color: var(--rf-text-main) !important;
            -webkit-text-fill-color: var(--rf-text-main) !important;
            border-color: var(--rf-border) !important;
            caret-color: var(--rf-text-main) !important;
            box-shadow: none !important;
        }

        [data-baseweb="input"] input,
        [data-baseweb="base-input"] input {
            background: var(--rf-table-bg) !important;
            color: var(--rf-text-main) !important;
            -webkit-text-fill-color: var(--rf-text-main) !important;
            caret-color: var(--rf-text-main) !important;
        }

        [data-baseweb="base-input"] {
            background: var(--rf-table-bg) !important;
        }

        input::placeholder,
        textarea::placeholder {
            color: #6b7280 !important;
            -webkit-text-fill-color: #6b7280 !important;
            opacity: 1 !important;
        }

        [data-testid="stNumberInput"] button {
            background: #e5e7eb !important;
            color: #111827 !important;
            border-color: rgba(0, 0, 0, 0.18) !important;
            box-shadow: none !important;
        }

        [data-testid="stPlotlyChart"] {
            background: #ffffff !important;
        }

        .footer-note {
            color: #6b7280 !important;
            border-top: 1px solid rgba(0, 0, 0, 0.22);
            padding-top: 1.5rem;
            margin-top: 2rem;
        }

        .stApp .footer-note * {
            color: #6b7280 !important;
        }

        .metric-card,
        .notice-box,
        .section-title,
        [data-testid="stDataFrame"],
        [data-testid="stDataEditor"],
        .stButton > button,
        .stFormSubmitButton > button,
        .stDownloadButton > button {
            box-shadow: none !important;
        }

        @media (max-width: 1300px) {
            .metric-grid {
                grid-template-columns: repeat(3, minmax(0, 1fr));
            }
        }

        @media (max-width: 760px) {
            .metric-grid {
                grid-template-columns: 1fr;
            }

            .metric-card {
                min-height: 128px;
            }

            .metric-value-main,
            .metric-value-main.value-long,
            .metric-value-main.value-xlong,
            .metric-value-main.value-xxlong {
                font-size: clamp(1.45rem, 7vw, 2.05rem);
            }
        }
        </style>
        """,
        unsafe_allow_html=True,
    )


def apply_plotly_readable_theme(fig):
    """화이트 배경에서 Plotly 차트 텍스트가 잘 보이도록 공통 테마를 적용한다."""
    fig.update_layout(
        template="plotly_white",
        plot_bgcolor="#ffffff",
        paper_bgcolor="#ffffff",
        font=dict(color="#111827", size=13),
        title=dict(
            font=dict(color="#111827", size=18),
            x=0.02,
            xanchor="left",
        ),
        legend=dict(
            font=dict(color="#111827", size=12),
            bgcolor="rgba(255,255,255,0)",
            bordercolor="rgba(0,0,0,0)",
        ),
        margin=dict(l=60, r=30, t=70, b=60),
    )

    fig.update_xaxes(
        title_font=dict(color="#111827", size=13),
        tickfont=dict(color="#374151", size=11),
        gridcolor="rgba(0, 0, 0, 0.18)",
        zerolinecolor="rgba(0, 0, 0, 0.42)",
        linecolor="rgba(0, 0, 0, 0.45)",
        showline=True,
    )

    fig.update_yaxes(
        title_font=dict(color="#111827", size=13),
        tickfont=dict(color="#374151", size=11),
        gridcolor="rgba(0, 0, 0, 0.22)",
        zerolinecolor="rgba(0, 0, 0, 0.42)",
        linecolor="rgba(0, 0, 0, 0.45)",
        showline=True,
    )

    fig.update_traces(
        textfont=dict(color="#111827"),
        hoverlabel=dict(
            bgcolor="#ffffff",
            font_size=12,
            font_color="#111827",
            bordercolor="rgba(0,0,0,0.35)",
        ),
    )

    if getattr(fig.layout, "annotations", None):
        for annotation in fig.layout.annotations:
            annotation.font = dict(color="#111827", size=14)

    return fig


def format_won(value: Any) -> str:
    """원화 금액 포맷."""
    if value is None or pd.isna(value):
        return "N/A"
    try:
        return f"{float(value):,.0f}원"
    except (TypeError, ValueError):
        return "N/A"


def format_percent(value: Any, digits: int = 2) -> str:
    """비율 포맷."""
    if value is None or pd.isna(value):
        return "N/A"
    try:
        return f"{float(value):.{digits}%}"
    except (TypeError, ValueError):
        return "N/A"


def format_number(value: Any, digits: int = 0) -> str:
    """숫자 포맷."""
    if value is None or pd.isna(value):
        return "N/A"
    try:
        return f"{float(value):,.{digits}f}"
    except (TypeError, ValueError):
        return "N/A"


def format_float(value: Any, digits: int = 4) -> str:
    """소수 포맷."""
    if value is None or pd.isna(value):
        return "N/A"
    try:
        return f"{float(value):,.{digits}f}"
    except (TypeError, ValueError):
        return "N/A"


def format_usd(value: Any) -> str:
    """달러 금액 포맷."""
    if value is None or pd.isna(value):
        return "N/A"
    try:
        return f"${float(value):,.2f}"
    except (TypeError, ValueError):
        return "N/A"


def format_signed_won(value: Any) -> str:
    """손익용 원화 금액 포맷."""
    if value is None or pd.isna(value):
        return "N/A"
    try:
        number = float(value)
    except (TypeError, ValueError):
        return "N/A"
    if abs(number) < 0.5:
        return "0원"
    sign = "+" if number > 0 else "-"
    return f"{sign}{abs(number):,.0f}원"


def format_signed_percent(value: Any) -> str:
    """손익률용 비율 포맷."""
    if value is None or pd.isna(value):
        return "N/A"
    try:
        number = float(value)
    except (TypeError, ValueError):
        return "N/A"
    if abs(number) < 0.00005:
        return "0.00%"
    sign = "+" if number > 0 else "-"
    return f"{sign}{abs(number):.2%}"


def format_price_by_currency(value: Any, currency: Any, empty_text: str = "N/A") -> str:
    """통화에 맞게 가격을 표시한다."""
    if value is None or pd.isna(value):
        return empty_text
    currency_text = str(currency or "").upper()
    if currency_text == "USD":
        return format_usd(value)
    return format_won(value)


def format_purchase_price(row: pd.Series) -> str:
    """매수가격 표시 형식."""
    if str(row.get("시장", "")) == "CASH":
        return "-"
    return format_price_by_currency(row.get("매수가격"), row.get("매수가격_통화"), empty_text="N/A")


def format_current_price(row: pd.Series) -> str:
    """현재가격 표시 형식."""
    return format_price_by_currency(row.get("현재가격"), row.get("현재가격_통화"), empty_text="N/A")


def format_market_ticker(row: pd.Series) -> str:
    """시장과 티커를 합쳐 표시한다."""
    market = str(row.get("시장", "")).strip()
    ticker = str(row.get("티커", "")).strip()
    if market == "CASH" or ticker == "CASH":
        return "CASH"
    return f"{market}.{ticker}" if market else ticker


def profit_loss_color(value: Any) -> str:
    """손익 값에 맞는 Streamlit Styler 색상."""
    if value is None or pd.isna(value):
        return "color: #64748b;"
    try:
        number = float(value)
    except (TypeError, ValueError):
        return "color: #64748b;"
    if number > 0:
        return "color: #dc2626; font-weight: 700;"
    if number < 0:
        return "color: #2563eb; font-weight: 700;"
    return "color: #64748b;"


@st.cache_data(show_spinner=False)
def read_csv_cached(path_string: str, modified_at: int, date_index: bool, index_col_zero: bool) -> pd.DataFrame:
    """수정시각 기반 캐시로 CSV를 읽는다."""
    del modified_at
    path = Path(path_string)
    if index_col_zero:
        return pd.read_csv(path, encoding="utf-8-sig", index_col=0)
    if date_index:
        frame = pd.read_csv(path, encoding="utf-8-sig", index_col="날짜", parse_dates=["날짜"])
        frame.index = pd.to_datetime(frame.index)
        frame = frame[~frame.index.duplicated(keep="last")].sort_index()
        frame.index.name = "날짜"
        return frame
    return pd.read_csv(path, encoding="utf-8-sig")


@st.cache_data(show_spinner=False)
def read_text_cached(path_string: str, modified_at: int) -> str:
    """텍스트 파일 캐시 로더."""
    del modified_at
    return Path(path_string).read_text(encoding="utf-8")


@st.cache_data(show_spinner=False)
def read_json_cached(path_string: str, modified_at: int) -> dict[str, Any]:
    """JSON 파일 캐시 로더."""
    del modified_at
    return json.loads(Path(path_string).read_text(encoding="utf-8"))


def load_csv_file(file_path: Path, date_index: bool = False, index_col_zero: bool = False) -> pd.DataFrame | None:
    """CSV 파일을 안전하게 읽는다."""
    if not file_path.exists():
        return None
    try:
        return read_csv_cached(str(file_path), file_path.stat().st_mtime_ns, date_index, index_col_zero)
    except Exception:
        return None


def load_text_file(file_path: Path) -> str | None:
    """텍스트 파일을 안전하게 읽는다."""
    if not file_path.exists():
        return None
    try:
        return read_text_cached(str(file_path), file_path.stat().st_mtime_ns)
    except OSError:
        return None


def load_json_file(file_path: Path) -> dict[str, Any] | None:
    """JSON 파일을 안전하게 읽는다."""
    if not file_path.exists():
        return None
    try:
        return read_json_cached(str(file_path), file_path.stat().st_mtime_ns)
    except Exception:
        return None


def show_missing_file_warning(file_path: Path, label: str | None = None) -> None:
    """누락 파일 경고."""
    st.info(f"{NO_ANALYSIS_MESSAGE}\n\n누락 파일: `{label or file_path.name}`")


def get_metric(summary: pd.DataFrame | None, metric_name: str, column: str = "수익률") -> float | None:
    """risk_summary에서 특정 지표를 가져온다."""
    if summary is None or not {"지표", column}.issubset(summary.columns):
        return None
    matched = summary.loc[summary["지표"] == metric_name, column]
    if matched.empty or pd.isna(matched.iloc[0]):
        return None
    try:
        return float(matched.iloc[0])
    except (TypeError, ValueError):
        return None


def normalize_correlation_matrix(correlation: pd.DataFrame | None) -> pd.DataFrame:
    """CSV 재로딩 중 깨진 상관관계 행렬의 index와 columns를 안전하게 정규화한다."""
    if correlation is None or correlation.empty:
        return pd.DataFrame()

    matrix = correlation.copy()
    possible_index_cols = ["index", "Unnamed: 0", "티커", "자산", "Ticker"]
    for column in possible_index_cols:
        if column in matrix.columns:
            matrix = matrix.set_index(column)
            break

    matrix.index = matrix.index.astype(str)
    matrix.columns = matrix.columns.astype(str)

    common_assets = [asset for asset in matrix.columns if asset in matrix.index]
    if len(common_assets) < 2 and matrix.shape[0] == matrix.shape[1]:
        matrix.index = matrix.columns.astype(str)
        common_assets = list(matrix.columns)

    common_assets = [asset for asset in matrix.columns if asset in matrix.index]
    if len(common_assets) < 2:
        return pd.DataFrame()

    matrix = matrix.loc[common_assets, common_assets]
    return matrix.apply(pd.to_numeric, errors="coerce")


def build_display_name_map(
    position_summary: pd.DataFrame | None,
    asset_master: pd.DataFrame | None,
) -> dict[str, str]:
    """position_summary와 asset_master에서 티커 → 표시명 매핑을 만든다."""
    name_map: dict[str, str] = {}
    for frame in (asset_master, position_summary):
        if frame is None or frame.empty or "티커" not in frame.columns:
            continue
        for _, row in frame.iterrows():
            ticker = str(row.get("티커", "")).strip()
            if not ticker or ticker.lower() == "nan":
                continue
            for column in ("표시명", "자산", "회사명", "자산명"):
                value = row.get(column)
                if value is None or pd.isna(value):
                    continue
                display_text = str(value).strip()
                if display_text and display_text.lower() != "nan":
                    name_map[ticker] = display_text
                    break
            else:
                name_map[ticker] = ticker
    name_map.setdefault("CASH", "현금")
    return name_map


def build_company_name_map(
    position_summary: pd.DataFrame | None,
    asset_master: pd.DataFrame | None,
) -> dict[str, str]:
    """티커 → 회사명 매핑을 만든다."""
    company_map: dict[str, str] = {}
    for frame in (asset_master, position_summary):
        if frame is None or frame.empty or "티커" not in frame.columns:
            continue
        for _, row in frame.iterrows():
            ticker = str(row.get("티커", "")).strip()
            if not ticker or ticker.lower() == "nan":
                continue
            for column in ("회사명", "자산명"):
                value = row.get(column)
                if value is None or pd.isna(value):
                    continue
                company_text = str(value).strip()
                if company_text and company_text.lower() != "nan":
                    company_map[ticker] = company_text
                    break
            else:
                company_map[ticker] = ticker
    company_map.setdefault("CASH", "현금")
    return company_map


def display_name(ticker: Any, name_map: dict[str, str]) -> str:
    """표시명 매핑이 있으면 표시명을, 없으면 티커를 반환한다."""
    ticker_text = str(ticker).strip()
    return name_map.get(ticker_text, ticker_text)


def add_display_asset_column(frame: pd.DataFrame, name_map: dict[str, str], column_name: str = "자산") -> pd.DataFrame:
    """티커 컬럼이 있는 표에 표시명 기반 자산 컬럼을 추가한다."""
    displayed = frame.copy()
    if "티커" in displayed.columns:
        displayed.insert(0, column_name, displayed["티커"].map(lambda ticker: display_name(ticker, name_map)))
    return displayed


def rename_axis_with_display_names(matrix: pd.DataFrame, name_map: dict[str, str]) -> pd.DataFrame:
    """상관관계 매트릭스의 축 이름을 표시명으로 바꾼다."""
    if matrix is None or matrix.empty:
        return pd.DataFrame()
    renamed = matrix.copy()
    renamed.index = [display_name(index, name_map) for index in renamed.index]
    renamed.columns = [display_name(column, name_map) for column in renamed.columns]
    return renamed


def build_config_table(
    config: dict[str, Any] | None,
    market: str,
    name_map: dict[str, str],
    company_map: dict[str, str],
) -> pd.DataFrame:
    """저장된 portfolio_config를 화면용 입력 현황 표로 변환한다."""
    if not config:
        return pd.DataFrame()
    key = "korean_stocks" if market == "KR" else "us_stocks"
    ticker_label = "종목코드" if market == "KR" else "티커"
    rows = []
    for item in config.get(key, []):
        ticker = str(item.get("ticker", "")).strip()
        purchase_price = item.get("purchase_price")
        purchase_currency = item.get("purchase_currency") or ("KRW" if market == "KR" else "USD")
        rows.append(
            {
                "시장": market,
                ticker_label: ticker,
                "회사명": company_map.get(ticker, ticker),
                "표시명": display_name(ticker, name_map),
                "수량": item.get("quantity", 0),
                "매수가격": format_price_by_currency(purchase_price, purchase_currency, empty_text="N/A"),
                "매수일자": item.get("purchase_date") or "-",
            }
        )
    return pd.DataFrame(rows)


def empty_kr_editor_frame() -> pd.DataFrame:
    """한국주식 입력용 빈 DataFrame."""
    return pd.DataFrame(columns=KR_EDITOR_COLUMNS)


def empty_us_editor_frame() -> pd.DataFrame:
    """미국주식 입력용 빈 DataFrame."""
    return pd.DataFrame(columns=US_EDITOR_COLUMNS)


def example_kr_editor_frame() -> pd.DataFrame:
    """예시 한국주식 입력값."""
    return pd.DataFrame(
        [
            {"종목코드": "005930", "수량": 10.0, "매수가격_원": 70_000.0},
            {"종목코드": "000660", "수량": 5.0, "매수가격_원": 180_000.0},
        ],
        columns=KR_EDITOR_COLUMNS,
    )


def example_us_editor_frame() -> pd.DataFrame:
    """예시 미국주식 입력값."""
    return pd.DataFrame(
        [
            {
                "티커": "GOOGL",
                "수량": 3.0,
                "매수가격_달러": 260.5,
                "매수일자": date(2024, 3, 15),
            },
        ],
        columns=US_EDITOR_COLUMNS,
    )


def is_blank_value(value: Any) -> bool:
    """입력 표의 빈 값을 판별한다."""
    if value is None:
        return True
    if isinstance(value, str) and not value.strip():
        return True
    try:
        return bool(pd.isna(value))
    except TypeError:
        return False


def load_existing_portfolio_config_safe() -> dict[str, Any]:
    """portfolio_config.json이 없어도 빈 기본값을 반환한다."""
    empty_config = {"korean_stocks": [], "us_stocks": [], "cash_krw": 0.0}
    if not PORTFOLIO_CONFIG_FILE.exists():
        return empty_config
    try:
        config = json.loads(PORTFOLIO_CONFIG_FILE.read_text(encoding="utf-8"))
    except Exception:
        return empty_config
    if not isinstance(config, dict):
        return empty_config
    return {
        "korean_stocks": config.get("korean_stocks", []) or [],
        "us_stocks": config.get("us_stocks", []) or [],
        "cash_krw": float(config.get("cash_krw", 0.0) or 0.0),
    }


def parse_editor_date(value: Any) -> str | None:
    """data_editor 날짜 값을 YYYY-MM-DD 문자열로 변환한다."""
    if is_blank_value(value):
        return None
    if isinstance(value, datetime):
        parsed = value.date()
    elif isinstance(value, date):
        parsed = value
    else:
        try:
            parsed = pd.to_datetime(value, errors="raise").date()
        except Exception as exc:
            raise ValueError("매수일자는 YYYY-MM-DD 형식이어야 합니다. 예: 2024-03-15") from exc
    if parsed > date.today():
        raise ValueError("미래 날짜는 매수일자로 입력할 수 없습니다.")
    return parsed.isoformat()


def normalize_kr_ticker_for_input(value: Any) -> str:
    """한국주식 입력 종목코드를 6자리로 정규화한다."""
    if is_blank_value(value):
        return ""
    text = str(value).strip()
    if text.endswith(".0"):
        text = text[:-2]
    if not text.isdigit():
        raise ValueError(f"한국주식 종목코드는 숫자여야 합니다: {text}")
    if len(text) > 6:
        raise ValueError(f"한국주식 종목코드는 6자리를 넘을 수 없습니다: {text}")
    return text.zfill(6)


def normalize_us_ticker_for_input(value: Any) -> str:
    """미국주식 입력 티커를 대문자로 정규화한다."""
    if is_blank_value(value):
        return ""
    ticker = str(value).strip().upper()
    if not re.fullmatch(r"[A-Z][A-Z0-9.\-]*", ticker):
        raise ValueError(f"미국주식 티커 형식이 올바르지 않습니다: {ticker}")
    return ticker


def parse_positive_number(value: Any, label: str, allow_blank: bool = False) -> float | None:
    """양수 입력값을 검증한다."""
    if is_blank_value(value):
        if allow_blank:
            return None
        raise ValueError(f"{label}은 0보다 큰 숫자여야 합니다.")
    try:
        number = float(value)
    except (TypeError, ValueError) as exc:
        raise ValueError(f"{label}은 0보다 큰 숫자여야 합니다.") from exc
    if number <= 0:
        raise ValueError(f"{label}은 0보다 커야 합니다.")
    return number


def portfolio_config_to_editor_frames(config: dict[str, Any]) -> tuple[pd.DataFrame, pd.DataFrame, float]:
    """기존 portfolio_config를 data_editor 초기값으로 변환한다."""
    kr_rows = []
    for item in config.get("korean_stocks", []) or []:
        kr_rows.append(
            {
                "종목코드": str(item.get("ticker", "")).strip(),
                "수량": item.get("quantity"),
                "매수가격_원": item.get("purchase_price"),
            }
        )

    us_rows = []
    for item in config.get("us_stocks", []) or []:
        purchase_date = item.get("purchase_date")
        try:
            editor_purchase_date = pd.to_datetime(purchase_date).date() if purchase_date else None
        except Exception:
            editor_purchase_date = None
        us_rows.append(
            {
                "티커": str(item.get("ticker", "")).strip().upper(),
                "수량": item.get("quantity"),
                "매수가격_달러": item.get("purchase_price"),
                "매수일자": editor_purchase_date,
            }
        )

    kr_df = pd.DataFrame(kr_rows, columns=KR_EDITOR_COLUMNS) if kr_rows else empty_kr_editor_frame()
    us_df = pd.DataFrame(us_rows, columns=US_EDITOR_COLUMNS) if us_rows else empty_us_editor_frame()
    cash_krw = float(config.get("cash_krw", 0.0) or 0.0)
    return kr_df, us_df, cash_krw


def build_portfolio_config_from_editor(
    kr_df: pd.DataFrame,
    us_df: pd.DataFrame,
    cash_krw: float,
) -> dict[str, Any]:
    """data_editor 입력값을 portfolio_config.json 구조로 변환하고 검증한다."""
    korean_stocks: list[dict[str, Any]] = []
    us_stocks: list[dict[str, Any]] = []

    for row_number, row in kr_df.fillna("").iterrows():
        ticker = normalize_kr_ticker_for_input(row.get("종목코드"))
        if not ticker:
            continue
        quantity = parse_positive_number(row.get("수량"), f"한국주식 {ticker} 수량")
        purchase_price = parse_positive_number(row.get("매수가격_원"), f"한국주식 {ticker} 매수가격", allow_blank=True)
        korean_stocks.append(
            {
                "market": "KR",
                "ticker": ticker,
                "quantity": quantity,
                "purchase_price": purchase_price,
                "purchase_currency": "KRW",
            }
        )

    for _, row in us_df.fillna("").iterrows():
        ticker = normalize_us_ticker_for_input(row.get("티커"))
        if not ticker:
            continue
        quantity = parse_positive_number(row.get("수량"), f"미국주식 {ticker} 수량")
        purchase_price = parse_positive_number(row.get("매수가격_달러"), f"미국주식 {ticker} 매수가격", allow_blank=True)
        purchase_date = parse_editor_date(row.get("매수일자"))
        if purchase_price is not None and purchase_date is None:
            raise ValueError(
                "미국주식은 매수가격을 입력할 경우 매수일자도 함께 입력해야 합니다. "
                "예: GOOGL,29,260.5,2024-03-15"
            )
        us_stocks.append(
            {
                "market": "US",
                "ticker": ticker,
                "quantity": quantity,
                "purchase_price": purchase_price,
                "purchase_currency": "USD",
                "purchase_date": purchase_date,
            }
        )

    try:
        cash_value = float(cash_krw or 0.0)
    except (TypeError, ValueError) as exc:
        raise ValueError("원화 현금은 0 이상 숫자여야 합니다.") from exc
    if cash_value < 0:
        raise ValueError("원화 현금은 0 이상이어야 합니다.")

    if not korean_stocks and not us_stocks and cash_value == 0:
        raise ValueError("최소 하나 이상의 주식 또는 현금 금액을 입력해야 합니다.")

    return {
        "korean_stocks": korean_stocks,
        "us_stocks": us_stocks,
        "cash_krw": cash_value,
    }


def save_portfolio_config_from_app(config: dict[str, Any]) -> dict[str, Any]:
    """앱에서 생성한 포트폴리오 설정을 저장한다."""
    return save_portfolio_config(config)


def has_any_portfolio_position(config: dict[str, Any] | None) -> bool:
    """저장된 포트폴리오가 비어 있지 않은지 확인한다."""
    if not config:
        return False
    return bool(config.get("korean_stocks") or config.get("us_stocks") or float(config.get("cash_krw", 0.0) or 0.0) > 0)


def initialize_portfolio_input_state(config: dict[str, Any]) -> None:
    """Portfolio Input 탭의 session_state를 초기화한다."""
    if "input_version" not in st.session_state:
        st.session_state["input_version"] = 0
    if st.session_state.get("portfolio_input_initialized"):
        return
    kr_df, us_df, cash_krw = portfolio_config_to_editor_frames(config)
    st.session_state["kr_editor_df"] = kr_df
    st.session_state["us_editor_df"] = us_df
    st.session_state["cash_krw_value"] = cash_krw
    st.session_state["portfolio_input_initialized"] = True


def split_metric_value(value: str) -> tuple[str, str]:
    """metric 카드 값을 숫자/본문과 단위로 분리한다.

    예:
    - "241,128,748원" -> ("241,128,748", "원")
    - "33.88%" -> ("33.88", "%")
    - "727일" -> ("727", "일")
    """
    text = str(value).strip()
    if not text:
        return "", ""
    matched = re.match(r"^(.+?)(원|%|일|회)$", text)
    if matched:
        return matched.group(1).strip(), matched.group(2)
    return text, ""


def metric_value_size_class(main_value: str) -> str:
    """값 길이에 따라 metric 숫자 폰트 크기 클래스를 고른다."""
    text = str(main_value).strip()
    if len(text) >= 16:
        return "value-xxlong"
    if len(text) >= 13:
        return "value-xlong"
    if len(text) >= 10:
        return "value-long"
    return ""


def render_metric_card(label: str, value: str, sub_text: str = "") -> str:
    """안전한 HTML 카드 문자열을 반환한다."""
    safe_label = escape(str(label))
    main_value, unit = split_metric_value(str(value))
    safe_main_value = escape(main_value)
    safe_unit = escape(unit)
    safe_sub = escape(str(sub_text))
    size_class = metric_value_size_class(main_value)
    value_class = f"metric-value-main {size_class}".strip()

    profit_class = ""
    profit_sensitive_labels = {"총 평가손익", "총자산 수익률", "총 수익률"}

    if str(label) in profit_sensitive_labels:
        value_text = str(value).strip()
        if value_text.startswith("+"):
            profit_class = "profit-positive"
        elif value_text.startswith("-"):
            profit_class = "profit-negative"

    card_class = f"metric-card {profit_class}".strip()
    unit_html = f'<span class="metric-value-unit">{safe_unit}</span>' if safe_unit else ""

    return (
        f'<div class="{card_class}">'
        '<div class="metric-card-top">'
        f'<div class="metric-label">{safe_label}</div>'
        '<div class="metric-value-row">'
        f'<span class="{value_class}">{safe_main_value}</span>'
        f"{unit_html}"
        "</div>"
        "</div>"
        f'<div class="metric-card-bottom"><div class="metric-sub">{safe_sub or "&nbsp;"}</div></div>'
        "</div>"
    )


def render_metric_grid(cards: list[dict[str, str]]) -> None:
    """카드 목록을 CSS grid로 렌더링한다."""
    html = "\n".join(render_metric_card(card["label"], card["value"], card.get("sub", "")) for card in cards)
    st.markdown(f'<div class="metric-grid">\n{html}\n</div>', unsafe_allow_html=True)


def display_date_index_table(frame: pd.DataFrame) -> pd.DataFrame:
    """날짜 인덱스 DataFrame을 화면 표시용으로 변환한다."""
    displayed = frame.reset_index()
    if "날짜" in displayed.columns:
        displayed["날짜"] = pd.to_datetime(displayed["날짜"]).dt.strftime("%Y-%m-%d")
    return displayed


def format_position_summary(position: pd.DataFrame, name_map: dict[str, str]) -> pd.io.formats.style.Styler:
    """Position Summary 탭 표시 형식과 손익 색상을 적용한다."""
    raw = position.copy().reset_index(drop=True)
    displayed = pd.DataFrame(index=raw.index)
    displayed["자산명"] = raw.apply(
        lambda row: row.get("자산명") or row.get("회사명") or display_name(row.get("티커"), name_map),
        axis=1,
    )
    displayed["티커"] = raw.apply(format_market_ticker, axis=1)
    displayed["수량"] = raw["수량"].map(lambda value: format_number(value, 4).rstrip("0").rstrip(".")) if "수량" in raw.columns else "N/A"
    displayed["매수일자"] = raw.get("매수일자", pd.Series("-", index=raw.index)).fillna("-").replace("", "-")
    displayed["매수가격"] = raw.apply(format_purchase_price, axis=1)
    displayed["현재가격"] = raw.apply(format_current_price, axis=1)
    cash_mask = (
        raw.get("시장", pd.Series("", index=raw.index)).astype(str).eq("CASH")
        | raw.get("티커", pd.Series("", index=raw.index)).astype(str).eq("CASH")
        | displayed["자산명"].astype(str).eq("현금")
        )

    displayed.loc[cash_mask, ["티커", "수량", "매수가격", "현재가격"]] = "-"
    displayed["현재평가금액_원화"] = raw.get("현재평가금액_원화", pd.Series(index=raw.index, dtype=float)).map(format_won)
    displayed["총 수익"] = raw.get("총수익_원화", pd.Series(index=raw.index, dtype=float)).map(format_signed_won)
    displayed["수익률"] = raw.get("수익률", pd.Series(index=raw.index, dtype=float)).map(format_signed_percent)
    displayed["포트폴리오비중"] = raw.get("포트폴리오비중", pd.Series(index=raw.index, dtype=float)).map(format_percent)

    def style_profit_loss(_: pd.DataFrame) -> pd.DataFrame:
        styles = pd.DataFrame("", index=displayed.index, columns=displayed.columns)
        if "총수익_원화" in raw.columns:
            styles["총 수익"] = raw["총수익_원화"].map(profit_loss_color)
        if "수익률" in raw.columns:
            styles["수익률"] = raw["수익률"].map(profit_loss_color)
        return styles

    return displayed.style.apply(style_profit_loss, axis=None)


def format_risk_summary(summary: pd.DataFrame) -> pd.DataFrame:
    """risk_summary 표시 형식."""
    displayed = summary.copy()
    if "수익률" in displayed.columns:
        displayed["수익률"] = displayed["수익률"].map(format_percent)
    for column in ("금액", "현재평가금액_기준_금액"):
        if column in displayed.columns:
            displayed[column] = displayed[column].map(format_won)
    return displayed


def format_asset_risk(asset_risk: pd.DataFrame, name_map: dict[str, str] | None = None) -> pd.DataFrame:
    """asset_risk_summary 표시 형식."""
    displayed = add_display_asset_column(asset_risk, name_map or {}) if name_map is not None else asset_risk.copy()
    preferred_prefix = ["자산", "자산명", "시장", "티커", "수량", "비중", "현재평가금액"]
    remaining_columns = [column for column in displayed.columns if column not in preferred_prefix]
    displayed = displayed[[column for column in preferred_prefix if column in displayed.columns] + remaining_columns]
    money_columns = [column for column in displayed.columns if "금액" in column or column == "현재평가금액"]
    percent_keywords = ("비중", "수익률", "변동성", "MDD", "VaR", "ES")
    for column in displayed.columns:
        if column in money_columns:
            displayed[column] = displayed[column].map(format_won)
        elif any(keyword in column for keyword in percent_keywords) and column not in {"티커", "시장", "자산명"}:
            displayed[column] = displayed[column].map(format_percent)
    return displayed


def load_dashboard_data() -> dict[str, Any]:
    """대시보드에 필요한 모든 산출물을 안전하게 로드한다."""
    return {
        "config": load_existing_portfolio_config_safe(),
        "asset_master": load_csv_file(ASSET_MASTER_FILE),
        "kr_prices": load_csv_file(KR_PRICE_FILE, date_index=True),
        "us_prices": load_csv_file(US_PRICE_FILE, date_index=True),
        "usdkrw": load_csv_file(USD_KRW_FILE, date_index=True),
        "asset_values": load_csv_file(ASSET_VALUE_FILE, date_index=True),
        "asset_returns": load_csv_file(ASSET_RETURN_FILE, date_index=True),
        "portfolio_values": load_csv_file(PORTFOLIO_VALUE_FILE, date_index=True),
        "portfolio_returns": load_csv_file(PORTFOLIO_RETURNS_FILE, date_index=True),
        "position_summary": load_csv_file(POSITION_SUMMARY_FILE),
        "risk_summary": load_csv_file(RISK_SUMMARY_FILE),
        "asset_risk_summary": load_csv_file(ASSET_RISK_SUMMARY_FILE),
        "correlation": normalize_correlation_matrix(load_csv_file(CORRELATION_FILE, index_col_zero=True)),
        "stress_test": load_csv_file(STRESS_TEST_FILE),
        "asset_stress_test": load_csv_file(ASSET_STRESS_TEST_FILE),
        "drawdown": load_csv_file(DRAWDOWN_FILE, date_index=True),
        "var_backtest": load_csv_file(VAR_BACKTEST_FILE),
        "var_backtest_summary": load_csv_file(VAR_BACKTEST_SUMMARY_FILE),
        "report": load_text_file(REPORT_FILE),
    }


def check_file_status() -> pd.DataFrame:
    """주요 산출물 존재 여부를 반환한다."""
    files = {
        "포트폴리오 입력": PORTFOLIO_CONFIG_FILE,
        "자산명 매핑": ASSET_MASTER_FILE,
        "한국주식 가격": KR_PRICE_FILE,
        "미국주식 가격": US_PRICE_FILE,
        "USD/KRW 환율": USD_KRW_FILE,
        "자산 평가금액": ASSET_VALUE_FILE,
        "자산 수익률": ASSET_RETURN_FILE,
        "포트폴리오 가치": PORTFOLIO_VALUE_FILE,
        "포트폴리오 수익률": PORTFOLIO_RETURNS_FILE,
        "포지션 요약": POSITION_SUMMARY_FILE,
        "리스크 요약": RISK_SUMMARY_FILE,
        "자산별 리스크": ASSET_RISK_SUMMARY_FILE,
        "상관관계": CORRELATION_FILE,
        "스트레스 테스트": STRESS_TEST_FILE,
        "백테스팅 결과": VAR_BACKTEST_FILE,
        "리포트": REPORT_FILE,
    }
    return pd.DataFrame([{"산출물": name, "경로": str(path), "존재": path.exists()} for name, path in files.items()])


def render_section_title(title: str) -> None:
    """공통 섹션 제목을 렌더링한다."""
    st.markdown(f'<div class="section-title">{escape(title)}</div>', unsafe_allow_html=True)


def render_tab_explanation(text: str) -> None:
    """각 탭 상단의 짧은 설명 박스를 렌더링한다."""
    safe_text = escape(text).replace("\n", "<br>")
    st.markdown(
        f"""
        <div class="notice-box">
            {safe_text}
        </div>
        """,
        unsafe_allow_html=True,
    )


def config_to_text(config: dict[str, Any] | None, market: str) -> str:
    """현재 JSON 설정을 멀티라인 입력값으로 변환한다."""
    if not config:
        return ""
    key = "korean_stocks" if market == "KR" else "us_stocks"
    lines = []
    for item in config.get(key, []):
        ticker = item["ticker"]
        quantity = float(item["quantity"])
        quantity_text = f"{quantity:g}"
        purchase_price = item.get("purchase_price")
        if purchase_price is None or pd.isna(purchase_price):
            lines.append(f"{ticker},{quantity_text}")
            continue
        purchase_price_text = f"{float(purchase_price):g}"
        if market == "KR":
            lines.append(f"{ticker},{quantity_text},{purchase_price_text}")
        else:
            purchase_date = item.get("purchase_date")
            if purchase_date:
                lines.append(f"{ticker},{quantity_text},{purchase_price_text},{purchase_date}")
            else:
                lines.append(f"{ticker},{quantity_text}")
    return "\n".join(lines)


def run_analysis_from_app() -> None:
    """Streamlit에서 비대화형 전체 분석을 실행한다."""
    if run_all_main is None:
        st.error("run_all.py의 main()을 가져올 수 없습니다.")
        return
    try:
        with st.spinner("분석을 실행 중입니다..."):
            run_all_main(interactive=False)
    except Exception as exc:
        st.error(f"전체 분석 실행에 실패했습니다: {type(exc).__name__}: {exc}")
        return
    st.cache_data.clear()
    st.session_state["analysis_success_message"] = "분석이 완료되었습니다. 다른 탭에서 결과를 확인하세요."
    st.rerun()


def render_portfolio_input_tab(data: dict[str, Any]) -> None:
    """포트폴리오 입력 탭."""
    render_section_title("Portfolio Input")
    render_tab_explanation(
        "분석할 포트폴리오를 입력할 수 있어요. 한국주식은 종목코드,수량,매수가격을 입력하고, "
        "미국주식은 티커,수량,매수가격,매수일자를 입력하면 돼요. 미국주식 평가손익은 매수일자 USD/KRW 환율과 "
        "최신 USD/KRW 환율을 모두 반영해서 분석할게요."
    )

    config = data["config"]
    initialize_portfolio_input_state(config)

    if success_message := st.session_state.pop("analysis_success_message", None):
        st.success(success_message)

    name_map = build_display_name_map(data.get("position_summary"), data.get("asset_master"))
    company_map = build_company_name_map(data.get("position_summary"), data.get("asset_master"))

    col_example, col_reset = st.columns(2)
    with col_example:
        if st.button("예시 포트폴리오 불러오기", use_container_width=True):
            st.session_state["kr_editor_df"] = example_kr_editor_frame()
            st.session_state["us_editor_df"] = example_us_editor_frame()
            st.session_state["cash_krw_value"] = 3_000_000.0
            st.session_state["input_version"] += 1
            st.rerun()
    with col_reset:
        if st.button("입력 초기화", use_container_width=True):
            st.session_state["kr_editor_df"] = empty_kr_editor_frame()
            st.session_state["us_editor_df"] = empty_us_editor_frame()
            st.session_state["cash_krw_value"] = 0.0
            st.session_state["input_version"] += 1
            st.rerun()

    editor_version = st.session_state.get("input_version", 0)

    with st.form("portfolio_input_form", clear_on_submit=False):
        st.markdown("#### 한국주식 입력")
        st.caption("한국주식은 6자리 종목코드, 보유 수량, 원화 매수가격을 입력하면 돼요.")
        kr_df = st.data_editor(
            st.session_state["kr_editor_df"],
            num_rows="dynamic",
            use_container_width=True,
            column_config={
                "종목코드": st.column_config.TextColumn(
                    "종목코드",
                    help="한국주식 6자리 종목코드. 예: 005930",
                ),
                "수량": st.column_config.NumberColumn(
                    "수량",
                    min_value=0.0,
                    step=1.0,
                ),
                "매수가격_원": st.column_config.NumberColumn(
                    "매수가격(원)",
                    min_value=0.0,
                    step=100.0,
                ),
            },
            key=f"kr_stock_editor_{editor_version}",
        )

        st.markdown("#### 미국주식 입력")
        st.caption(
            "미국주식은 티커, 보유 수량, 달러 매수가격, 매수일자를 입력하면 돼요. "
            "매수일자는 매수 당시 USD/KRW 환율을 조회하는 데 사용돼요."
        )
        us_df = st.data_editor(
            st.session_state["us_editor_df"],
            num_rows="dynamic",
            use_container_width=True,
            column_config={
                "티커": st.column_config.TextColumn(
                    "티커",
                    help="미국주식 티커. 예: GOOGL, NVDA, AAPL",
                ),
                "수량": st.column_config.NumberColumn(
                    "수량",
                    min_value=0.0,
                    step=1.0,
                ),
                "매수가격_달러": st.column_config.NumberColumn(
                    "매수가격($)",
                    min_value=0.0,
                    step=0.01,
                ),
                "매수일자": st.column_config.DateColumn(
                    "매수일자",
                    help="미국주식 매수일자. 예: 2024-03-15",
                    max_value=date.today(),
                ),
            },
            key=f"us_stock_editor_{editor_version}",
        )

        st.markdown("#### 원화 현금")
        st.caption(
            "숫자만 입력해주세요."
        )
        cash_krw = st.number_input(
            "원화 현금",
            min_value=0.0,
            value=float(st.session_state.get("cash_krw_value", 0.0)),
            step=100_000.0,
            format="%.0f",
            key=f"cash_krw_input_{editor_version}",
        )

        col_save, col_run = st.columns(2)
        with col_save:
            save_clicked = st.form_submit_button(
                "포트폴리오 저장",
                type="primary",
                use_container_width=True,
            )
        with col_run:
            run_clicked = st.form_submit_button("전체 분석 실행", use_container_width=True)

    if save_clicked or run_clicked:
        st.session_state["kr_editor_df"] = kr_df
        st.session_state["us_editor_df"] = us_df
        st.session_state["cash_krw_value"] = cash_krw

        try:
            config_to_save = build_portfolio_config_from_editor(kr_df, us_df, cash_krw)
            saved_config = save_portfolio_config_from_app(config_to_save)
        except ValueError as exc:
            st.error(str(exc))
        else:
            st.session_state["last_saved_config"] = saved_config
            st.cache_data.clear()
            if run_clicked:
                run_analysis_from_app()
            else:
                st.success(f"저장 완료: {PORTFOLIO_CONFIG_FILE}")

    preview_config = st.session_state.get("last_saved_config") or load_existing_portfolio_config_safe()
    if has_any_portfolio_position(preview_config):
        st.markdown("#### 현재 저장된 포트폴리오 미리보기")
        kr_table = build_config_table(preview_config, "KR", name_map, company_map)
        us_table = build_config_table(preview_config, "US", name_map, company_map)
        if not kr_table.empty:
            st.caption("한국주식 입력 현황")
            st.dataframe(kr_table, use_container_width=True, hide_index=True)
        if not us_table.empty:
            st.caption("미국주식 입력 현황")
            st.dataframe(us_table, use_container_width=True, hide_index=True)
        st.info(f"보유 원화 현금: {format_won(preview_config.get('cash_krw', 0))}")
        with st.expander("저장된 원본 JSON 보기", expanded=False):
            st.json(preview_config)
    else:
        st.info(
            "저장된 포트폴리오가 아직 없어요. 표에 자산을 입력하거나 예시 포트폴리오를 불러온 뒤 "
            "포트폴리오 저장 또는 전체 분석 실행을 눌러주세요."
        )


def render_overview_tab(data: dict[str, Any]) -> None:
    """Overview 탭."""
    render_tab_explanation(
        "이 대시보드에서는 현재 입력된 보유 종목과 수량을 기준으로 과거 가격 및 환율 데이터를 적용해 손실위험을 추정할 수 있어요.\n "
        "따라서 결과는 실제 과거 운용성과가 아니라, 현재 포트폴리오가 과거 시장환경에 노출되었을 경우의 리스크 시뮬레이션이에요."
    )
    position = data["position_summary"]
    summary = data["risk_summary"]
    if position is None or summary is None:
        show_missing_file_warning(RISK_SUMMARY_FILE, "risk_summary.csv")
        return

    total_value = float(position["현재평가금액_원화"].sum())
    cash_value = float(position.loc[position["시장"] == "CASH", "현재평가금액_원화"].sum())
    investment_value = None
    total_profit = None
    total_profit_rate = None
    if {"매수금액_원화", "총수익_원화"}.issubset(position.columns):
        purchase_amounts = pd.to_numeric(position["매수금액_원화"], errors="coerce")
        profits = pd.to_numeric(position["총수익_원화"], errors="coerce")
        if purchase_amounts.notna().all() and profits.notna().all() and purchase_amounts.sum() > 0:
            investment_value = float(purchase_amounts.sum())
            total_profit = float(profits.sum())
            total_profit_rate = total_profit / investment_value
        else:
            profit_sub_text = "매수가격이 누락된 자산이 있어요."
    cards = [
        {"label": "총 자산", "value": format_won(total_value), "sub": "원화 기준"},
        {"label": "총 평가손익", "value": format_signed_won(total_profit)},
        {"label": "총자산 수익률", "value": format_signed_percent(total_profit_rate)},
        {"label": "현금 비중","value": format_percent(cash_value / total_value if total_value else 0),"sub": f"현금 {format_won(cash_value)}",},
        {"label": "연환산 변동성", "value": format_percent(get_metric(summary, "연환산 변동성")), "sub": "252거래일(1년) 기준"},
        {"label": "MDD", "value": format_percent(get_metric(summary, "MDD")), "sub": "고점 대비 최대 하락률"},
        {"label": "95% Historical VaR", "value": format_won(get_metric(summary, "95% Historical VaR", "금액")), "sub": format_percent(get_metric(summary, "95% Historical VaR"))},
        {"label": "95% Historical ES", "value": format_won(get_metric(summary, "95% Historical ES", "금액")), "sub": format_percent(get_metric(summary, "95% Historical ES"))},
    ]
    render_metric_grid(cards)

    st.markdown(
        """
        <div class="notice-box">
        미국주식은 일별 USD/KRW 환율을 적용해 원화 평가금액으로 변환해요.
        따라서 미국주식 수익률과 VaR에는 주가 변동과 환율 변동이 모두 자동으로 반영돼요.
        </div>
        """,
        unsafe_allow_html=True,
    )


def render_position_summary_tab(data: dict[str, Any]) -> None:
    """Position Summary 탭."""
    position = data["position_summary"]
    if position is None:
        show_missing_file_warning(POSITION_SUMMARY_FILE, "position_summary.csv")
        return
    name_map = build_display_name_map(position, data.get("asset_master"))
    displayed_position = add_display_asset_column(position, name_map)
    st.dataframe(format_position_summary(position, name_map), use_container_width=True, hide_index=True)
    chart = px.pie(displayed_position, names="자산", values="현재평가금액_원화", title="자산별 현재 평가금액 비중")
    chart.update_layout(
        template="plotly_white",
        margin=dict(l=25, r=25, t=55, b=25),
        plot_bgcolor="#ffffff",
        paper_bgcolor="#ffffff",
        font=dict(color="#111827"),
    )
    chart = apply_plotly_readable_theme(chart)
    st.plotly_chart(chart, use_container_width=True)


def render_risk_summary_tab(data: dict[str, Any]) -> None:
    """Risk Summary 탭."""
    summary = data["risk_summary"]
    if summary is None:
        show_missing_file_warning(RISK_SUMMARY_FILE, "risk_summary.csv")
        return

    displayed = format_risk_summary(summary)

    st.dataframe(
        displayed,
        use_container_width=True,
        height=620,
    )


def render_asset_risk_tab(data: dict[str, Any]) -> None:
    """Asset Risk 탭."""
    render_tab_explanation(
        "개별 자산별 리스크를 비교하는 화면이에요. "
        "어떤 종목이 변동성, VaR, MDD 측면에서 더 큰 위험을 가지는지 확인할 수 있어요."
    )
    asset_risk = data["asset_risk_summary"]
    if asset_risk is None:
        show_missing_file_warning(ASSET_RISK_SUMMARY_FILE, "asset_risk_summary.csv")
        return
    name_map = build_display_name_map(data.get("position_summary"), data.get("asset_master"))
    chart_data = add_display_asset_column(asset_risk, name_map)
    st.dataframe(format_asset_risk(asset_risk, name_map), use_container_width=True, hide_index=True)

    chart_cols = st.columns(3)
    with chart_cols[0]:
        if "95% Historical VaR 금액" in asset_risk.columns:
            fig = px.bar(chart_data, x="자산", y="95% Historical VaR 금액", title="자산별 95% Historical VaR 금액")
            fig.update_layout(
                template="plotly_white",
                plot_bgcolor="#ffffff",
                paper_bgcolor="#ffffff",
                font=dict(color="#111827"),
            )
            fig = apply_plotly_readable_theme(fig)
            st.plotly_chart(fig, use_container_width=True)
    with chart_cols[1]:
        if "연환산 변동성" in asset_risk.columns:
            fig = px.bar(chart_data, x="자산", y="연환산 변동성", title="자산별 연환산 변동성")
            fig.update_layout(
                template="plotly_white",
                yaxis_tickformat=".1%",
                plot_bgcolor="#ffffff",
                paper_bgcolor="#ffffff",
                font=dict(color="#111827"),
            )
            fig = apply_plotly_readable_theme(fig)
            st.plotly_chart(fig, use_container_width=True)
    with chart_cols[2]:
        if "MDD" in asset_risk.columns:
            fig = px.bar(chart_data, x="자산", y="MDD", title="자산별 MDD")
            fig.update_layout(
                template="plotly_white",
                yaxis_tickformat=".1%",
                plot_bgcolor="#ffffff",
                paper_bgcolor="#ffffff",
                font=dict(color="#111827"),
            )
            fig = apply_plotly_readable_theme(fig)
            st.plotly_chart(fig, use_container_width=True)


def render_portfolio_trend_tab(data: dict[str, Any]) -> None:
    """Portfolio Trend 탭."""
    portfolio_values = data["portfolio_values"]
    portfolio_returns = data["portfolio_returns"]
    drawdown = data["drawdown"]
    if portfolio_values is None or portfolio_returns is None:
        show_missing_file_warning(PORTFOLIO_RETURNS_FILE, "portfolio_returns.csv")
        return

    fig_value = px.line(portfolio_values, x=portfolio_values.index, y="TOTAL_VALUE_KRW", title="전체 포트폴리오 가치 추이")
    fig_value.update_layout(
        template="plotly_white",
        xaxis_title="날짜",
        yaxis_title="원",
        plot_bgcolor="#ffffff",
        paper_bgcolor="#ffffff",
        font=dict(color="#111827"),
    )
    fig_value = apply_plotly_readable_theme(fig_value)
    st.plotly_chart(fig_value, use_container_width=True)

    col_left, col_right = st.columns(2)
    with col_left:
        fig_cum = px.line(portfolio_returns, x=portfolio_returns.index, y="누적수익률", title="누적수익률 추이")
        fig_cum.update_layout(
            template="plotly_white",
            yaxis_tickformat=".1%",
            plot_bgcolor="#ffffff",
            paper_bgcolor="#ffffff",
            font=dict(color="#111827"),
        )
        fig_cum = apply_plotly_readable_theme(fig_cum)
        st.plotly_chart(fig_cum, use_container_width=True)
    with col_right:
        fig_daily = px.line(portfolio_returns, x=portfolio_returns.index, y="포트폴리오_수익률", title="일별 수익률 추이")
        fig_daily.update_layout(
            template="plotly_white",
            yaxis_tickformat=".1%",
            plot_bgcolor="#ffffff",
            paper_bgcolor="#ffffff",
            font=dict(color="#111827"),
        )
        fig_daily = apply_plotly_readable_theme(fig_daily)
        st.plotly_chart(fig_daily, use_container_width=True)

    if drawdown is not None:
        fig_dd = px.area(drawdown, x=drawdown.index, y="Drawdown", title="Drawdown 추이")
        fig_dd.update_layout(
            template="plotly_white",
            yaxis_tickformat=".1%",
            plot_bgcolor="#ffffff",
            paper_bgcolor="#ffffff",
            font=dict(color="#111827"),
        )
        fig_dd = apply_plotly_readable_theme(fig_dd)
        st.plotly_chart(fig_dd, use_container_width=True)


def build_var_comparison(summary: pd.DataFrame, confidence: str) -> pd.DataFrame:
    """전체 포트폴리오 VaR/ES 비교표."""
    rows = []
    for methodology in ("Historical", "Parametric", "Monte Carlo"):
        for risk_type in ("VaR", "ES"):
            metric = f"{confidence} {methodology} {risk_type}"
            rows.append(
                {
                    "방법론": methodology,
                    "지표": risk_type,
                    "손실률": format_percent(get_metric(summary, metric)),
                    "손실금액": format_won(get_metric(summary, metric, "금액")),
                }
            )
    return pd.DataFrame(rows)


def render_var_analysis_tab(data: dict[str, Any]) -> None:
    """VaR Analysis 탭."""
    render_tab_explanation(
        "Historical, Parametric, Monte Carlo 방식으로 계산한 VaR와 ES를 비교하는 화면이에요. "
        "서로 다른 가정의 리스크 추정치가 얼마나 다른지 확인할 수 있어요."
    )
    summary = data["risk_summary"]
    asset_risk = data["asset_risk_summary"]
    if summary is None:
        show_missing_file_warning(RISK_SUMMARY_FILE, "risk_summary.csv")
        return

    col95, col99 = st.columns(2)
    with col95:
        st.markdown('<div class="section-title">95% 신뢰수준</div>', unsafe_allow_html=True)
        st.dataframe(build_var_comparison(summary, "95%"), use_container_width=True, hide_index=True)
    with col99:
        st.markdown('<div class="section-title">99% 신뢰수준</div>', unsafe_allow_html=True)
        st.dataframe(build_var_comparison(summary, "99%"), use_container_width=True, hide_index=True)

    chart_rows = []
    for confidence in ("95%", "99%"):
        for methodology in ("Historical", "Parametric", "Monte Carlo"):
            metric = f"{confidence} {methodology} VaR"
            value = get_metric(summary, metric)
            if value is not None:
                chart_rows.append({"신뢰수준": confidence, "방법론": methodology, "VaR 손실률": value})
    if chart_rows:
        fig = px.bar(pd.DataFrame(chart_rows), x="방법론", y="VaR 손실률", color="신뢰수준", barmode="group", title="전체 포트폴리오 VaR 비교")
        fig.update_layout(
            template="plotly_white",
            yaxis_tickformat=".1%",
            plot_bgcolor="#ffffff",
            paper_bgcolor="#ffffff",
            font=dict(color="#111827"),
        )
        fig = apply_plotly_readable_theme(fig)
        st.plotly_chart(fig, use_container_width=True)

    if asset_risk is not None:
        st.markdown('<div class="section-title">개별 자산 VaR</div>', unsafe_allow_html=True)
        name_map = build_display_name_map(data.get("position_summary"), data.get("asset_master"))
        columns = [column for column in ["시장", "티커", "비중", "현재평가금액", "95% Historical VaR", "95% Historical VaR 금액", "99% Historical VaR", "99% Historical VaR 금액"] if column in asset_risk.columns]
        st.dataframe(format_asset_risk(asset_risk[columns], name_map), use_container_width=True, hide_index=True)


def parse_bool_series(series: pd.Series) -> pd.Series:
    """문자열 또는 bool breach 컬럼을 bool로 변환한다."""
    if pd.api.types.is_bool_dtype(series):
        return series.fillna(False)
    return series.astype(str).str.lower().isin({"true", "1", "yes", "y"})


def build_backtest_chart(backtest: pd.DataFrame, confidence: str = "95%") -> go.Figure | None:
    """Rolling Historical VaR 백테스팅 차트."""
    suffix = confidence.replace("%", "")
    var_column = f"Historical_VaR_{suffix}"
    breach_column = f"Historical_Breach_{suffix}"
    required = {"날짜", "실제수익률", var_column, breach_column}
    if not required.issubset(backtest.columns):
        return None
    frame = backtest.copy()
    frame["날짜"] = pd.to_datetime(frame["날짜"], errors="coerce")
    frame["실제수익률"] = pd.to_numeric(frame["실제수익률"], errors="coerce")
    frame[var_column] = pd.to_numeric(frame[var_column], errors="coerce")
    frame["Breach"] = parse_bool_series(frame[breach_column])
    frame = frame.dropna(subset=["날짜", "실제수익률", var_column])
    if frame.empty:
        return None

    fig = go.Figure()
    fig.add_trace(go.Scatter(x=frame["날짜"], y=frame["실제수익률"] * 100, mode="lines", name="실제수익률"))
    fig.add_trace(go.Scatter(x=frame["날짜"], y=-frame[var_column] * 100, mode="lines", name=f"-Historical VaR {confidence}", line=dict(dash="dash")))
    breach_frame = frame[frame["Breach"]]
    if not breach_frame.empty:
        fig.add_trace(go.Scatter(x=breach_frame["날짜"], y=breach_frame["실제수익률"] * 100, mode="markers", name="Breach", marker=dict(color="#dc2626", size=8)))
    fig.update_layout(
        template="plotly_white",
        title=f"Historical VaR {confidence} Backtesting",
        xaxis_title="날짜",
        yaxis_title="수익률 (%)",
        plot_bgcolor="#ffffff",
        paper_bgcolor="#ffffff",
        font=dict(color="#111827"),
    )
    return fig


def render_backtesting_tab(data: dict[str, Any]) -> None:
    """Backtesting 탭."""
    render_tab_explanation(
        "Rolling VaR 백테스팅 결과를 보여주는 화면이에요. "
        "과거 데이터로 추정한 VaR가 실제 다음 날 손실을 얼마나 잘 설명했는지 검증해요."
    )
    summary = data["var_backtest_summary"]
    backtest = data["var_backtest"]
    if summary is None and backtest is None:
        show_missing_file_warning(VAR_BACKTEST_FILE, "var_backtest.csv")
        return
    if summary is not None:
        displayed = summary.copy()
        for column in ("예상초과확률", "실제초과비율"):
            if column in displayed.columns:
                displayed[column] = displayed[column].map(format_percent)
        for column in ("Kupiec_LR", "Kupiec_p_value"):
            if column in displayed.columns:
                displayed[column] = displayed[column].map(lambda value: format_float(value, 4))
        st.dataframe(displayed, use_container_width=True, hide_index=True)
    if backtest is not None:
        fig = build_backtest_chart(backtest, "95%")
        if fig is not None:
            fig = apply_plotly_readable_theme(fig)
            st.plotly_chart(fig, use_container_width=True)
        with st.expander("99% Historical VaR Backtesting"):
            fig99 = build_backtest_chart(backtest, "99%")
            if fig99 is not None:
                fig99 = apply_plotly_readable_theme(fig99)
                st.plotly_chart(fig99, use_container_width=True)


def render_correlation_tab(data: dict[str, Any]) -> None:
    """Correlation 탭."""
    render_tab_explanation(
        "자산 간 수익률 상관관계를 보여주는 화면이에요. "
        "상관관계가 높은 자산은 위기 시 함께 움직일 가능성이 크기 때문에 분산효과가 약할 수 있어요."
    )
    correlation = normalize_correlation_matrix(data["correlation"])
    if correlation.empty:
        st.info("현금을 제외한 위험자산이 2개 미만이거나 상관관계 데이터가 없어요.")
        return
    name_map = build_display_name_map(data.get("position_summary"), data.get("asset_master"))
    display_correlation = rename_axis_with_display_names(correlation, name_map)
    st.dataframe(display_correlation, use_container_width=True)
    fig = px.imshow(
    display_correlation,
    zmin=-1,
    zmax=1,
    color_continuous_scale="RdBu_r",
    title="자산별 수익률 상관관계",
    )

    fig.update_traces(
    texttemplate="%{z:.2f}",
    text=display_correlation.round(2),
    )

    fig.update_layout(
        template="plotly_white",
        plot_bgcolor="#ffffff",
        paper_bgcolor="#ffffff",
        font=dict(color="#111827"),
    )
    fig = apply_plotly_readable_theme(fig)
    st.plotly_chart(fig, use_container_width=True)


def render_stress_test_tab(data: dict[str, Any]) -> None:
    """Stress Test 탭."""
    render_tab_explanation(
        "주식 자산이 -5%, -10%, -20%, -30% 하락하는 시나리오에서 "
        "포트폴리오 손실이 얼마나 발생하는지 확인할 수 있어요."
    )
    stress = data["stress_test"]
    asset_stress = data["asset_stress_test"]
    if stress is None:
        show_missing_file_warning(STRESS_TEST_FILE, "stress_test.csv")
        return
    displayed = stress.copy()
    for column in ("위험자산충격률", "예상손실률"):
        if column in displayed.columns:
            displayed[column] = displayed[column].map(format_percent)
    for column in ("총포트폴리오가치", "예상손실금액", "스트레스후포트폴리오가치"):
        if column in displayed.columns:
            displayed[column] = displayed[column].map(format_won)
    st.dataframe(displayed, use_container_width=True, hide_index=True)

    col_loss, col_after = st.columns(2)
    with col_loss:
        fig = px.bar(stress, x="시나리오", y="예상손실금액", title="시나리오별 예상손실금액")
        fig.update_layout(
            template="plotly_white",
            plot_bgcolor="#ffffff",
            paper_bgcolor="#ffffff",
            font=dict(color="#111827"),
        )
        fig = apply_plotly_readable_theme(fig)
        st.plotly_chart(fig, use_container_width=True)
    with col_after:
        fig = px.bar(stress, x="시나리오", y="스트레스후포트폴리오가치", title="스트레스 후 포트폴리오 가치")
        fig.update_layout(
            template="plotly_white",
            plot_bgcolor="#ffffff",
            paper_bgcolor="#ffffff",
            font=dict(color="#111827"),
        )
        fig = apply_plotly_readable_theme(fig)
        st.plotly_chart(fig, use_container_width=True)

    if asset_stress is not None:
        st.markdown('<div class="section-title">개별 자산 스트레스 테스트</div>', unsafe_allow_html=True)
        name_map = build_display_name_map(data.get("position_summary"), data.get("asset_master"))
        asset_stress_for_chart = add_display_asset_column(asset_stress, name_map)
        displayed_asset = asset_stress_for_chart.copy()
        preferred_columns = ["자산", "자산명", "시장", "티커", "시나리오", "현재평가금액", "충격률", "예상손실금액", "스트레스후평가금액"]
        displayed_asset = displayed_asset[[column for column in preferred_columns if column in displayed_asset.columns]]
        for column in ("충격률",):
            if column in displayed_asset.columns:
                displayed_asset[column] = displayed_asset[column].map(format_percent)
        for column in ("현재평가금액", "예상손실금액", "스트레스후평가금액"):
            if column in displayed_asset.columns:
                displayed_asset[column] = displayed_asset[column].map(format_won)
        st.dataframe(displayed_asset, use_container_width=True, hide_index=True)
        if {"자산", "시나리오", "예상손실금액"}.issubset(asset_stress_for_chart.columns):
            fig = px.bar(
                asset_stress_for_chart,
                x="자산",
                y="예상손실금액",
                color="시나리오",
                barmode="group",
                title="자산별 스트레스 테스트 예상손실금액",
            )
            fig.update_layout(
                template="plotly_white",
                plot_bgcolor="#ffffff",
                paper_bgcolor="#ffffff",
                font=dict(color="#111827"),
            )
            fig = apply_plotly_readable_theme(fig)
            st.plotly_chart(fig, use_container_width=True)


def render_charts_tab() -> None:
    """Charts 탭."""
    render_tab_explanation(
        "분석 결과를 이미지 차트로 모아서 보여드려요. "
        "리포트나 발표 자료에 사용할 수 있는 주요 시각화 결과를 확인할 수 있어요."
    )
    chart_specs = [
        ("포트폴리오 가치", CHART_DIR / "portfolio_value.png"),
        ("누적수익률", CHART_DIR / "cumulative_return.png"),
        ("수익률 분포", CHART_DIR / "return_distribution.png"),
        ("Drawdown", CHART_DIR / "drawdown.png"),
        ("자산별 비중 · 표시명 기준", CHART_DIR / "asset_weights.png"),
        ("상관관계 히트맵 · 표시명 기준", CHART_DIR / "correlation_heatmap.png"),
        ("VaR 백테스팅", CHART_DIR / "var_backtest_breaches.png"),
    ]
    if not any(chart_path.exists() for _, chart_path in chart_specs):
        st.info(NO_ANALYSIS_MESSAGE)
        return
    for title, chart_path in chart_specs:
        st.markdown(f'<div class="section-title">{escape(title)}</div>', unsafe_allow_html=True)
        if chart_path.exists():
            st.image(str(chart_path), use_container_width=True)
        else:
            st.warning(f"`{chart_path.name}` 파일이 없습니다. 먼저 `python run_all.py`를 실행하세요.")


def render_raw_data_tab(data: dict[str, Any]) -> None:
    """Raw Data 탭."""
    render_tab_explanation(
        "분석에 사용된 입력값, 가격 데이터, 수익률, 리스크 결과 CSV를 확인하는 화면이에요. "
        "계산 결과를 검증하거나 다운로드할 때 사용하면 돼요."
    )
    raw_files = [
        ("portfolio_config.json", PORTFOLIO_CONFIG_FILE, "json"),
        ("asset_master.csv - 자산명 매핑", ASSET_MASTER_FILE, "csv"),
        ("kr_prices.csv", KR_PRICE_FILE, "date_csv"),
        ("us_prices.csv", US_PRICE_FILE, "date_csv"),
        ("usdkrw.csv", USD_KRW_FILE, "date_csv"),
        ("asset_values_krw.csv", ASSET_VALUE_FILE, "date_csv"),
        ("asset_returns_krw.csv", ASSET_RETURN_FILE, "date_csv"),
        ("portfolio_values.csv", PORTFOLIO_VALUE_FILE, "date_csv"),
        ("portfolio_returns.csv", PORTFOLIO_RETURNS_FILE, "date_csv"),
        ("position_summary.csv", POSITION_SUMMARY_FILE, "csv"),
        ("risk_summary.csv", RISK_SUMMARY_FILE, "csv"),
        ("asset_risk_summary.csv", ASSET_RISK_SUMMARY_FILE, "csv"),
        ("correlation_matrix.csv", CORRELATION_FILE, "index_csv"),
        ("stress_test.csv", STRESS_TEST_FILE, "csv"),
        ("asset_stress_test.csv", ASSET_STRESS_TEST_FILE, "csv"),
        ("var_backtest.csv", VAR_BACKTEST_FILE, "csv"),
        ("var_backtest_summary.csv", VAR_BACKTEST_SUMMARY_FILE, "csv"),
    ]
    rendered_any = False
    for title, file_path, kind in raw_files:
        if not file_path.exists():
            continue
        rendered_any = True
        with st.expander(title, expanded=False):
            if kind == "json":
                st.json(load_json_file(file_path))
            elif kind == "date_csv":
                frame = load_csv_file(file_path, date_index=True)
                if frame is not None:
                    st.dataframe(display_date_index_table(frame), use_container_width=True, hide_index=True)
            elif kind == "index_csv":
                frame = load_csv_file(file_path, index_col_zero=True)
                if frame is not None:
                    st.dataframe(frame, use_container_width=True)
            else:
                frame = load_csv_file(file_path)
                if frame is not None:
                    st.dataframe(frame, use_container_width=True, hide_index=True)
    if not rendered_any:
        st.info(NO_ANALYSIS_MESSAGE)


def render_glossary_intro() -> None:
    """용어 해설 상단 안내문."""
    render_section_title("용어 해설")
    render_tab_explanation(
        "대시보드에 사용된 리스크관리 용어를 설명해드릴게요. "
        "VaR, ES, MDD, Drawdown, 백테스팅, 상관관계, 스트레스 테스트의 의미와 해석 방법을 확인할 수 있어요.\n"
        "이 지표들은 모두 “포트폴리오가 얼마나 손실날 수 있는가”를 서로 다른 관점에서 측정하는 도구에요. 각 지표는 장점과 한계가 있으므로 하나의 숫자만 보지 말고 함께 해석해야 해요."
    )
    st.markdown(
        """
(중요) 이 사이트는 현재 입력된 보유 종목과 수량을 기준으로 과거 가격 및 환율 데이터를 적용해 손실위험을
추정해요. 따라서 결과는 실제 과거 운용성과가 아니라, 현재 포트폴리오가 과거 시장환경에 노출되었을
경우의 리스크 시뮬레이션이에요.
        """
    )


def render_glossary_summary_table() -> None:
    """핵심 용어 빠른 요약표."""
    summary_rows = [
        {
            "용어": "Historical VaR",
            "한 줄 정의": "과거 실제 수익률 분포를 기준으로 특정 신뢰수준의 하루 손실위험을 추정하는 지표에요.",
            "대시보드 위치": "Overview, VaR Analysis, Asset Risk",
        },
        {
            "용어": "Historical ES",
            "한 줄 정의": "Historical VaR를 초과한 최악의 손실 구간에서 평균적으로 얼마나 손실이 났는지 보여주는 지표에요.",
            "대시보드 위치": "Overview, VaR Analysis, Asset Risk",
        },
        {
            "용어": "Parametric VaR",
            "한 줄 정의": "수익률이 정규분포를 따른다고 가정해 평균과 표준편차로 계산하는 VaR이에요.",
            "대시보드 위치": "Risk Summary, VaR Analysis",
        },
        {
            "용어": "Parametric ES",
            "한 줄 정의": "정규분포 가정하에서 VaR를 초과한 꼬리구간 평균손실을 추정하는 지표에요.",
            "대시보드 위치": "Risk Summary, VaR Analysis",
        },
        {
            "용어": "Monte Carlo VaR",
            "한 줄 정의": "난수 시뮬레이션으로 수많은 가상 수익률을 만들고 그 분포에서 계산하는 VaR이에요.",
            "대시보드 위치": "Risk Summary, VaR Analysis",
        },
        {
            "용어": "Monte Carlo ES",
            "한 줄 정의": "Monte Carlo 시뮬레이션에서 VaR를 초과한 최악 구간의 평균손실이에요.",
            "대시보드 위치": "Risk Summary, VaR Analysis",
        },
        {
            "용어": "Volatility",
            "한 줄 정의": "수익률이 평균 주변에서 얼마나 크게 흔들리는지 나타내는 표준편차에요.",
            "대시보드 위치": "Overview, Risk Summary, Asset Risk",
        },
        {
            "용어": "Drawdown",
            "한 줄 정의": "각 시점에서 직전 고점 대비 현재 얼마나 하락했는지를 나타내는 시계열이에요.",
            "대시보드 위치": "Portfolio Trend, Charts",
        },
        {
            "용어": "MDD",
            "한 줄 정의": "분석기간 중 고점 대비 가장 크게 하락한 비율이에요.",
            "대시보드 위치": "Overview, Risk Summary, Asset Risk",
        },
        {
            "용어": "Correlation",
            "한 줄 정의": "두 자산 수익률이 함께 움직이는 정도에요.",
            "대시보드 위치": "Correlation",
        },
        {
            "용어": "Plotly Heatmap",
            "한 줄 정의": "상관관계 행렬처럼 숫자 행렬을 색상으로 시각화하는 차트에요.",
            "대시보드 위치": "Correlation",
        },
        {
            "용어": "Stress Test",
            "한 줄 정의": "특정 충격 시나리오에서 포트폴리오 손실이 얼마나 발생하는지 보는 분석이에요.",
            "대시보드 위치": "Stress Test",
        },
        {
            "용어": "VaR Backtesting",
            "한 줄 정의": "과거에 추정한 VaR와 실제 다음 날 손실을 비교해 VaR 모델이 적절했는지 검증하는 절차에요.",
            "대시보드 위치": "Backtesting",
        },
        {
            "용어": "Kupiec Test",
            "한 줄 정의": "VaR 초과 손실 발생 횟수가 이론적으로 기대한 횟수와 통계적으로 다른지 검정하는 방법이에요.",
            "대시보드 위치": "Backtesting",
        },
        {
            "용어": "현재 포트폴리오 기준 Historical Simulation",
            "한 줄 정의": "현재 보유 포트폴리오 구성을 과거 시장 데이터에 대입해 손실위험을 추정하는 방식이에요.",
            "대시보드 위치": "Overview, VaR Analysis, Report",
        },
    ]
    st.markdown("#### 핵심 용어 빠른 요약")
    st.dataframe(pd.DataFrame(summary_rows), use_container_width=True, hide_index=True)


def render_glossary_expanders() -> None:
    """용어별 상세 설명 expander."""
    glossary_items = [
        (
            "Historical VaR",
            True,
            """
### 한 줄 정의
Historical VaR는 과거 실제 수익률을 정렬해서 특정 신뢰수준에서 손실이 어느 정도까지 발생할 수 있는지 보는 지표입니다.

### 왜 필요한가
포트폴리오가 하루 동안 얼마나 손실날 수 있는지 직관적으로 보기 위해 사용합니다. 정규분포 같은 이론적 분포를 가정하지 않고 실제 과거 수익률을 사용합니다.

### 계산 방식
95% Historical VaR는 과거 수익률 중 하위 5% 지점의 손실률입니다.

```text
95% Historical VaR = - 과거 수익률의 5% 분위수
99% Historical VaR = - 과거 수익률의 1% 분위수
```

### 숫자 예시
과거 100일 수익률을 손실이 큰 순서대로 정렬했을 때 가장 나쁜 수익률 5개가 -7.0%, -6.2%, -5.1%, -4.5%, -4.0%라고 하겠습니다. 100일 중 하위 5번째 수익률이 -4.0%라면 95% Historical VaR는 4.0%입니다.

포트폴리오 현재 가치가 100,000,000원이라면 VaR 금액은 100,000,000원 × 4.0% = 4,000,000원입니다.

### 대시보드에서 해석하는 법
95% Historical VaR가 4,000,000원이라면, 과거 수익률 분포 기준으로 하루 손실이 약 400만 원을 초과할 가능성이 약 5%였다고 해석합니다. 99% VaR는 더 극단적인 구간을 보기 때문에 일반적으로 95% VaR보다 큽니다.

### 주의할 점
- VaR는 최악의 손실이 아닙니다.
- VaR를 초과하면 얼마까지 손실날 수 있는지는 알려주지 않습니다.
- 과거에 없었던 충격은 반영하기 어렵습니다.
- 표본 기간에 따라 결과가 크게 달라질 수 있습니다.

### 이 대시보드에서 나오는 위치
Overview, Risk Summary, Asset Risk, VaR Analysis
            """,
        ),
        (
            "Historical ES / Expected Shortfall",
            True,
            """
### 한 줄 정의
Historical ES는 Historical VaR를 초과한 최악의 손실들만 모아서 평균 손실을 계산한 지표입니다.

### 왜 필요한가
VaR는 손실 경계선만 알려줍니다. 하지만 VaR를 넘는 더 나쁜 날에는 실제 손실이 얼마나 깊어질 수 있는지 알기 어렵습니다. ES는 이 꼬리위험을 보완합니다.

### 계산 방식
1. 과거 수익률에서 VaR 기준선을 찾습니다.
2. VaR보다 더 나쁜 수익률만 모읍니다.
3. 그 손실률들의 평균을 계산합니다.

### 숫자 예시
95% Historical VaR가 4.0%이고, VaR를 초과한 최악 5일 수익률이 -4.2%, -4.8%, -5.1%, -6.0%, -7.0%라고 하겠습니다.

손실률 평균은 (4.2% + 4.8% + 5.1% + 6.0% + 7.0%) / 5 = 5.42%입니다. 포트폴리오 현재 가치가 100,000,000원이라면 ES 금액은 5,420,000원입니다.

### 대시보드에서 해석하는 법
95% Historical ES가 5,420,000원이라면, 95% VaR를 넘는 나쁜 날이 발생했을 때 평균적으로 약 542만 원 손실이 발생했다는 뜻입니다.

### 주의할 점
- ES는 보통 VaR보다 큽니다.
- ES와 VaR 차이가 클수록 꼬리 손실이 깊다는 의미입니다.
- 표본이 적으면 ES 추정이 불안정할 수 있습니다.

### 이 대시보드에서 나오는 위치
Overview, Risk Summary, Asset Risk, VaR Analysis
            """,
        ),
        (
            "Parametric VaR",
            False,
            """
### 한 줄 정의
Parametric VaR는 수익률이 정규분포를 따른다고 가정하고 평균과 표준편차로 계산하는 VaR입니다.

### 왜 필요한가
Historical VaR는 과거 데이터에 강하게 의존합니다. Parametric VaR는 평균과 변동성만 있으면 빠르게 계산할 수 있어 간단한 리스크 추정에 유용합니다.

### 계산 방식
```text
VaR = -(평균수익률 + z × 표준편차)
95% VaR의 z 값 ≈ -1.645
99% VaR의 z 값 ≈ -2.326
```

### 숫자 예시
일간 평균수익률이 0.1%, 일간 변동성이 2.0%라면 95% Parametric VaR는 다음과 같습니다.

```text
VaR = -(0.1% + (-1.645 × 2.0%))
VaR = -(0.1% - 3.29%)
VaR = 3.19%
```

포트폴리오 가치가 100,000,000원이라면 VaR 금액은 3,190,000원입니다.

### 대시보드에서 해석하는 법
95% Parametric VaR가 3,190,000원이라면, 정규분포 가정하에서 하루 손실이 약 319만 원을 초과할 확률이 약 5%라고 해석합니다. Historical VaR와 차이가 크면 실제 수익률 분포가 정규분포와 다를 가능성이 있습니다.

### 주의할 점
- 실제 금융수익률은 정규분포보다 꼬리가 두꺼운 경우가 많습니다.
- 급락장에서는 손실위험을 과소평가할 수 있습니다.
- 평균과 표준편차에 민감합니다.

### 이 대시보드에서 나오는 위치
Risk Summary, VaR Analysis
            """,
        ),
        (
            "Parametric ES",
            False,
            """
### 한 줄 정의
Parametric ES는 정규분포 가정하에서 VaR를 초과한 꼬리구간의 평균손실을 계산한 지표입니다.

### 왜 필요한가
Parametric VaR가 정규분포상의 손실 경계선을 보여준다면, Parametric ES는 그 경계선을 넘었을 때 평균적으로 얼마나 손실나는지를 보여줍니다.

### 계산 방식
정규분포의 평균, 표준편차, 신뢰수준을 이용해 꼬리구간 평균손실을 계산합니다. 이 대시보드에서는 Parametric VaR와 같은 정규분포 가정을 사용합니다.

### 숫자 예시
일간 평균수익률이 0.1%, 일간 변동성이 2.0%이고 95% Parametric ES가 4.0%로 계산되었다고 하겠습니다. 포트폴리오 가치 100,000,000원 기준 ES 금액은 4,000,000원입니다.

### 대시보드에서 해석하는 법
95% Parametric ES가 4,000,000원이라면, 정규분포 가정하에서 95% VaR를 넘는 나쁜 날의 평균손실이 약 400만 원이라는 뜻입니다.

### 주의할 점
- 정규분포 가정이 틀리면 Parametric ES도 왜곡됩니다.
- Historical ES와 비교해서 보는 것이 좋습니다.
- 실제 시장에서는 극단 손실이 정규분포보다 자주 나타날 수 있습니다.

### 이 대시보드에서 나오는 위치
Risk Summary, VaR Analysis
            """,
        ),
        (
            "Monte Carlo VaR",
            False,
            """
### 한 줄 정의
Monte Carlo VaR는 가상의 수익률 시나리오를 많이 생성한 뒤, 그 시뮬레이션 분포에서 손실 분위수를 계산하는 VaR입니다.

### 왜 필요한가
포트폴리오 수익률이 앞으로 여러 방식으로 움직일 수 있다고 보고, 많은 가상 경로를 만들어 손실위험을 추정하기 위해 사용합니다.

### 계산 방식
1. 포트폴리오 또는 자산 수익률의 평균, 변동성, 공분산을 계산합니다.
2. 난수를 이용해 가상의 하루 수익률을 수만~수십만 개 생성합니다.
3. 생성된 수익률을 정렬합니다.
4. 95% VaR는 하위 5%, 99% VaR는 하위 1% 손실 지점을 사용합니다.

### 숫자 예시
100,000개의 가상 하루 수익률을 만들었고, 하위 5% 지점이 -3.8%라고 하겠습니다. 95% Monte Carlo VaR는 3.8%입니다. 포트폴리오 가치 100,000,000원 기준 VaR 금액은 3,800,000원입니다.

### 대시보드에서 해석하는 법
Monte Carlo VaR가 Historical VaR보다 크면, 시뮬레이션 가정에서 더 큰 손실위험이 관측된다는 뜻입니다. 반대로 작으면 과거 실제 분포보다 시뮬레이션 분포가 덜 위험하게 추정되었을 수 있습니다.

### 주의할 점
- 난수 시뮬레이션은 입력한 평균, 변동성, 공분산 가정에 의존합니다.
- 가정이 잘못되면 결과도 왜곡됩니다.
- 시뮬레이션 횟수가 너무 적으면 결과가 흔들릴 수 있습니다.

### 이 대시보드에서 나오는 위치
Risk Summary, VaR Analysis
            """,
        ),
        (
            "Monte Carlo ES",
            False,
            """
### 한 줄 정의
Monte Carlo ES는 Monte Carlo 시뮬레이션에서 VaR를 초과한 최악 구간의 평균손실입니다.

### 왜 필요한가
Monte Carlo VaR는 손실 경계선만 보여줍니다. Monte Carlo ES는 그 경계선을 넘은 극단 시나리오들의 평균손실을 보여줘 꼬리위험을 더 잘 설명합니다.

### 계산 방식
1. 가상 수익률 시나리오를 많이 생성합니다.
2. VaR 기준선을 찾습니다.
3. VaR보다 나쁜 시뮬레이션만 모읍니다.
4. 해당 손실들의 평균을 계산합니다.

### 숫자 예시
100,000개 시뮬레이션에서 95% VaR가 3.8%이고, VaR를 넘은 최악 5,000개 손실의 평균이 5.2%라고 하겠습니다. 포트폴리오 가치 100,000,000원 기준 Monte Carlo ES 금액은 5,200,000원입니다.

### 대시보드에서 해석하는 법
95% Monte Carlo ES가 5,200,000원이라면, 시뮬레이션상 나쁜 5% 상황에서 평균적으로 약 520만 원 손실이 발생했다는 의미입니다.

### 주의할 점
- ES는 VaR보다 꼬리 손실에 민감합니다.
- 시뮬레이션 가정이 틀리면 ES도 틀릴 수 있습니다.
- 극단 손실 구간의 표본 수가 작으면 불안정할 수 있습니다.

### 이 대시보드에서 나오는 위치
Risk Summary, VaR Analysis
            """,
        ),
        (
            "Volatility / 변동성",
            True,
            """
### 한 줄 정의
변동성은 수익률이 평균 주변에서 얼마나 크게 흔들리는지 나타내는 표준편차입니다.

### 왜 필요한가
변동성이 높다는 것은 수익률이 크게 오르내린다는 뜻입니다. 손실뿐 아니라 상승도 포함하지만, 리스크관리에서는 큰 흔들림 자체를 위험으로 봅니다.

### 계산 방식
일간 변동성은 일별 수익률의 표준편차입니다. 연환산 변동성은 보통 252거래일 기준으로 계산합니다.

```text
연환산 변동성 = 일간 변동성 × sqrt(252)
```

### 숫자 예시
일간 변동성이 2.0%라면 연환산 변동성은 2.0% × sqrt(252) = 2.0% × 15.87 = 31.74%입니다.

### 대시보드에서 해석하는 법
연환산 변동성이 31.74%라면, 이 포트폴리오가 연간 기준으로 상당히 크게 흔들릴 수 있다는 뜻입니다. 변동성이 높은 자산은 포트폴리오 수익률을 크게 흔들 수 있습니다.

### 주의할 점
- 변동성은 상승과 하락을 모두 위험으로 봅니다.
- 손실 방향만 보고 싶다면 VaR, ES, Drawdown도 함께 봐야 합니다.
- 변동성은 평균적인 흔들림이고, 극단 손실 크기를 직접 말해주지는 않습니다.

### 이 대시보드에서 나오는 위치
Overview, Risk Summary, Asset Risk
            """,
        ),
        (
            "Drawdown",
            True,
            """
### 한 줄 정의
Drawdown은 특정 시점의 포트폴리오 가치가 그 이전 최고점 대비 얼마나 하락했는지를 나타내는 지표입니다.

### 왜 필요한가
투자자는 단순 하루 손실보다 “고점 대비 얼마나 깨졌는가”를 크게 체감합니다. Drawdown은 누적 하락 압력을 보여줍니다.

### 계산 방식
```text
Drawdown = 현재 포트폴리오 가치 / 과거 최고 포트폴리오 가치 - 1
```

### 숫자 예시
포트폴리오 가치가 100,000,000원 → 120,000,000원 → 110,000,000원 → 90,000,000원 → 95,000,000원으로 움직였다고 하겠습니다. 최고점은 120,000,000원입니다.

4일차 Drawdown은 90,000,000 / 120,000,000 - 1 = -25%입니다. 5일차 Drawdown은 95,000,000 / 120,000,000 - 1 = -20.83%입니다.

### 대시보드에서 해석하는 법
Drawdown 차트가 -25%까지 내려갔다면, 해당 시점에 포트폴리오가 이전 최고점 대비 25% 하락했다는 뜻입니다.

### 주의할 점
- Drawdown은 회복 전까지 계속 음수로 유지됩니다.
- Drawdown은 기간 중 누적 하락을 보여주지만, 미래 손실 확률을 직접 말해주지는 않습니다.
- VaR는 하루 손실위험, Drawdown은 누적 하락위험에 가깝습니다.

### 이 대시보드에서 나오는 위치
Portfolio Trend, Charts
            """,
        ),
        (
            "MDD / Maximum Drawdown",
            True,
            """
### 한 줄 정의
MDD는 분석기간 중 발생한 가장 큰 Drawdown입니다.

### 왜 필요한가
MDD는 포트폴리오가 분석기간 동안 고점 대비 최대로 얼마나 하락했는지를 보여줍니다. 투자자가 실제로 버텨야 했던 최대 낙폭을 이해하는 데 유용합니다.

### 계산 방식
1. 매일 과거 최고 포트폴리오 가치를 계산합니다.
2. 매일 현재 가치가 최고점 대비 얼마나 낮은지 계산합니다.
3. 그중 가장 낮은 Drawdown을 MDD로 사용합니다.

### 숫자 예시
Drawdown 시계열이 0%, -5%, -12%, -8%, -25%, -10%, -3%라면 가장 낮은 값은 -25%이므로 MDD는 -25%입니다. 포트폴리오가 120,000,000원에서 90,000,000원까지 하락했다면 90,000,000 / 120,000,000 - 1 = -25%입니다.

### 대시보드에서 해석하는 법
MDD가 -25%라면, 분석기간 동안 포트폴리오가 고점 대비 최대 25%까지 하락한 적이 있다는 뜻입니다. Drawdown은 매일 변하는 시계열이고, MDD는 그중 가장 나쁜 한 점입니다.

### 주의할 점
- MDD는 한 번의 최대 하락만 보여줍니다.
- 손실이 얼마나 자주 발생했는지는 알려주지 않습니다.
- 분석기간이 길수록 MDD가 커질 가능성이 있습니다.
- MDD는 VaR처럼 확률 기반 지표가 아닙니다.

### 이 대시보드에서 나오는 위치
Overview, Risk Summary, Asset Risk, Portfolio Trend
            """,
        ),
        (
            "Correlation / 상관관계",
            False,
            """
### 한 줄 정의
상관관계는 두 자산의 수익률이 함께 움직이는 정도를 나타냅니다.

### 왜 필요한가
포트폴리오에 여러 자산을 넣는 이유는 분산효과를 얻기 위해서입니다. 그런데 자산들이 모두 같은 방향으로 움직이면 분산효과가 약해집니다. 상관관계는 이 분산효과를 판단하는 데 필요합니다.

### 계산 방식
상관계수는 -1에서 +1 사이의 값을 가집니다. +1에 가까우면 두 자산이 거의 같은 방향으로 움직이고, 0에 가까우면 뚜렷한 관계가 약하며, -1에 가까우면 반대 방향으로 움직이는 경향이 있습니다.

### 숫자 예시
삼성전자와 SK하이닉스 상관관계가 0.75라면 두 자산은 대체로 같은 방향으로 움직이는 경향이 강합니다. 삼성전자와 GOOGL 상관관계가 0.20이라면 움직임이 상대적으로 덜 비슷합니다. 어떤 방어자산과의 상관관계가 -0.30이라면 일부 반대 방향 움직임이 있을 수 있습니다.

### 대시보드에서 해석하는 법
상관관계가 높은 자산들이 많으면 위기 시 포트폴리오 전체가 함께 하락할 수 있습니다. 상관관계가 낮은 자산을 섞으면 일부 분산효과를 기대할 수 있습니다.

### 주의할 점
- 상관관계는 시기에 따라 변합니다.
- 위기 시에는 평소보다 상관관계가 높아지는 경우가 많습니다.
- 상관관계가 낮다고 손실이 없다는 뜻은 아닙니다.
- 상관관계는 선형 관계만 보여줍니다.

### 이 대시보드에서 나오는 위치
Correlation
            """,
        ),
        (
            "Plotly Heatmap / 상관관계 히트맵",
            False,
            """
### 한 줄 정의
Heatmap은 숫자 행렬을 색상으로 표현하는 차트입니다. 이 대시보드에서는 자산 간 상관관계 행렬을 색상으로 보여줍니다.

### 왜 필요한가
상관관계 행렬은 숫자가 많아지면 표만으로 보기 어렵습니다. Heatmap을 사용하면 어떤 자산쌍이 강하게 함께 움직이는지 색상으로 빠르게 확인할 수 있습니다.

### 계산 방식
자산별 수익률 상관계수를 행렬로 만든 뒤, 값이 높거나 낮은 정도를 색상으로 표시합니다. Plotly Heatmap은 마우스를 올려 값을 확인할 수 있는 인터랙티브 차트입니다.

### 숫자 예시
상관관계 행렬이 다음과 같다고 하겠습니다.

```text
          삼성전자   SK하이닉스   GOOGL
삼성전자     1.00      0.75      0.20
SK하이닉스   0.75      1.00      0.15
GOOGL       0.20      0.15      1.00
```

삼성전자와 SK하이닉스는 0.75로 비교적 높은 양의 상관관계이고, 삼성전자와 GOOGL은 0.20으로 상대적으로 낮은 상관관계입니다. 대각선 1.00은 자기 자신과의 상관관계입니다.

### 대시보드에서 해석하는 법
색상이 강하게 표시되는 자산쌍은 함께 움직이는 경향이 강합니다. 위기 시 같은 방향으로 움직일 가능성이 커서 분산효과가 약할 수 있습니다.

### 주의할 점
- 대각선 1.00은 자기 자신과의 상관관계라 해석 대상이 아닙니다.
- 색상은 상대적 강도를 보여주는 보조 도구입니다.
- 실제 리스크 판단은 VaR, ES, MDD와 함께 봐야 합니다.

### 이 대시보드에서 나오는 위치
Correlation
            """,
        ),
        (
            "Stress Test / 스트레스 테스트",
            True,
            """
### 한 줄 정의
스트레스 테스트는 특정 충격 시나리오를 가정했을 때 포트폴리오 손실이 얼마나 발생하는지 계산하는 분석입니다.

### 왜 필요한가
VaR는 과거 수익률 분포에서 일반적인 손실위험을 추정합니다. 하지만 투자자는 “주식시장이 20% 하락하면 내 포트폴리오는 얼마나 손실날까?” 같은 시나리오도 궁금해합니다. 스트레스 테스트는 이런 질문에 답합니다.

### 계산 방식
이 대시보드의 기본 시나리오는 위험자산 -5%, -10%, -20%, -30%입니다. 현금은 하락하지 않는다고 가정합니다.

### 숫자 예시
주식 평가금액이 80,000,000원, 현금이 20,000,000원, 총 포트폴리오 가치가 100,000,000원이라고 하겠습니다. 위험자산 -20% 시나리오에서는 주식 손실이 80,000,000원 × 20% = 16,000,000원이고 현금 손실은 0원입니다. 스트레스 후 포트폴리오 가치는 84,000,000원, 전체 손실률은 -16%입니다.

### 대시보드에서 해석하는 법
위험자산 -20% 시나리오에서 손실률이 -16%라면, 주식 자산이 20% 하락할 때 전체 포트폴리오는 약 16% 손실을 본다는 의미입니다. 현금 비중이 있기 때문에 전체 손실률은 주식 하락률보다 작을 수 있습니다.

### 주의할 점
- 스트레스 테스트는 확률을 알려주지 않습니다.
- “이런 충격이 오면 얼마를 잃는가”를 보는 시나리오 분석입니다.
- VaR와 함께 보면 정상 구간 손실과 극단 시나리오 손실을 비교할 수 있습니다.
- 실제 위기에서는 자산별 하락률과 환율이 동시에 변할 수 있습니다.

### 이 대시보드에서 나오는 위치
Stress Test
            """,
        ),
        (
            "VaR Backtesting / VaR 백테스팅",
            True,
            """
### 한 줄 정의
VaR 백테스팅은 과거 시점에서 계산한 VaR가 실제 다음 날 손실을 얼마나 잘 설명했는지 확인하는 절차입니다.

### 왜 필요한가
VaR를 계산하는 것만으로는 충분하지 않습니다. 계산한 VaR가 실제 손실위험을 잘 설명했는지 검증해야 합니다. 백테스팅은 VaR 모델의 신뢰성을 확인하는 과정입니다.

### 계산 방식
이 대시보드는 rolling window 방식을 사용합니다. 과거 252거래일 수익률로 다음 날 VaR를 계산하고, 다음 날 실제 수익률과 VaR를 비교합니다. 실제 수익률이 -VaR보다 낮으면 breach로 기록하고, 하루씩 이동하면서 전체 기간에 대해 반복합니다.

```text
Breach 조건: 실제수익률 < -VaR
```

### 숫자 예시
VaR가 4%이고 실제수익률이 -6%라면 -6% < -4%이므로 breach가 발생합니다. 95% VaR의 예상 초과확률은 5%입니다. 백테스트 관측일이 500일이면 예상 초과횟수는 500 × 5% = 25회입니다. 실제 초과횟수가 27회라면 대체로 기대와 비슷하지만, 60회라면 VaR가 손실위험을 과소평가했을 가능성이 있습니다.

### 대시보드에서 해석하는 법
Backtesting 탭에서 실제 초과횟수와 예상 초과횟수를 비교합니다. 차이가 크면 VaR 모델이 실제 손실을 잘 설명하지 못했을 수 있습니다.

### 주의할 점
- 백테스팅에서는 미래 데이터를 쓰면 안 됩니다.
- Rolling window 방식은 룩어헤드 편향을 줄입니다.
- 백테스팅은 손실 발생 빈도를 검증하지만, 초과 손실의 크기를 완전히 설명하지는 않습니다.
- 초과 손실이 특정 시기에 몰리는지도 함께 봐야 합니다.

### 이 대시보드에서 나오는 위치
Backtesting
            """,
        ),
        (
            "Kupiec Test",
            False,
            """
### 한 줄 정의
Kupiec Test는 VaR 초과 손실 발생 횟수가 이론적으로 기대한 횟수와 통계적으로 다른지 검정하는 방법입니다.

### 왜 필요한가
예상 초과횟수와 실제 초과횟수가 조금 다른 것은 자연스럽습니다. 하지만 차이가 너무 크면 VaR 모델이 부적절할 수 있습니다. Kupiec Test는 이 차이가 통계적으로 유의한지 확인합니다.

### 계산 방식
95% VaR라면 예상 초과확률은 5%이고, 99% VaR라면 예상 초과확률은 1%입니다. Kupiec Test는 실제 breach 횟수가 이 기대 초과확률과 얼마나 다른지 검정합니다.

### 숫자 예시
95% VaR, 관측일수 500일이면 예상 초과횟수는 500 × 5% = 25회입니다. 실제 초과횟수가 27회라면 차이가 작아 p-value가 높게 나올 가능성이 있습니다. 실제 초과횟수가 60회라면 p-value가 낮게 나올 수 있고, VaR 모델이 실제 손실을 과소평가했을 가능성이 있습니다.

### 대시보드에서 해석하는 법
p-value가 0.05 이상이면 초과횟수가 이론적 기대와 크게 다르다고 보기 어려워 대시보드에서는 “통과”로 표시합니다. p-value가 0.05 미만이면 초과횟수가 이론적 기대와 유의하게 다를 수 있어 “실패”로 표시합니다.

### 주의할 점
- Kupiec Test는 초과 손실 발생 빈도만 봅니다.
- 초과 손실이 연속적으로 몰리는지는 보지 않습니다.
- 손실의 크기 자체도 직접 평가하지 않습니다.
- 독립성 검정까지 하려면 Christoffersen Test 같은 추가 검정이 필요합니다.

### 이 대시보드에서 나오는 위치
Backtesting
            """,
        ),
        (
            "현재 포트폴리오 기준 Historical Simulation",
            True,
            """
### 한 줄 정의
현재 입력된 보유 종목과 수량을 기준으로 과거 가격과 환율 데이터를 적용해 손실위험을 추정하는 방식입니다.

### 왜 필요한가
사용자는 보통 “내가 지금 들고 있는 포트폴리오가 얼마나 위험한가”를 알고 싶어 합니다. 이를 위해 현재 포트폴리오 구성을 과거 시장환경에 대입해 리스크를 측정합니다.

### 계산 방식
1. 사용자가 현재 보유 종목, 수량, 현금을 입력합니다.
2. 각 자산의 과거 가격과 환율을 가져옵니다.
3. 현재 보유 수량을 과거 가격에 대입해 과거 포트폴리오 가치 흐름을 만듭니다.
4. 이 가치 흐름에서 수익률을 계산합니다.
5. 이 수익률로 VaR, ES, MDD, 변동성 등을 계산합니다.

### 숫자 예시
현재 포트폴리오가 삼성전자 236주, SK하이닉스 24주, GOOGL 29주, 현금 5,000,000원이라고 하겠습니다. 이 조합을 과거 3년 가격과 환율 데이터에 대입한 결과 95% Historical VaR가 4.5%로 계산되었다면, 현재 포트폴리오 가치 100,000,000원 기준 VaR 금액은 4,500,000원입니다.

### 대시보드에서 해석하는 법
이 결과는 “실제로 과거 3년 동안 이 포트폴리오를 운용했다”는 뜻이 아닙니다. “현재 포트폴리오가 과거 시장환경에 노출되었다면 이 정도 손실위험이 관측되었을 수 있다”는 의미입니다.

### 주의할 점
- 실제 과거 매수·매도 내역을 복원하는 분석은 아닙니다.
- 실제 운용성과 분석을 하려면 거래내역 또는 일별 보유수량 데이터가 필요합니다.
- 현재 포트폴리오의 현재 위험을 측정하는 목적에는 적절합니다.
- 과거에 없었던 미래 충격은 반영하기 어렵습니다.

### 이 대시보드에서 나오는 위치
Overview, VaR Analysis, Report
            """,
        ),
    ]

    st.markdown("#### 용어별 상세 설명")
    for title, expanded, body in glossary_items:
        with st.expander(title, expanded=expanded):
            st.markdown(body.strip())


def render_risk_glossary_tab() -> None:
    """용어 해설 탭."""
    render_glossary_intro()
    render_glossary_summary_table()
    render_glossary_expanders()


def render_report_tab(data: dict[str, Any]) -> None:
    """Report 탭."""
    render_tab_explanation(
        "자동 생성된 텍스트 리포트를 확인하는 화면입니다. "
        "입력 포트폴리오, 리스크 지표, 스트레스 테스트, 백테스팅 결과를 요약합니다."
    )
    report = data["report"]
    if report is None:
        show_missing_file_warning(REPORT_FILE, "report_summary.txt")
        return
    st.text_area("리포트 내용", report, height=720, disabled=True)
    st.download_button("report_summary.txt 다운로드", report.encode("utf-8"), "report_summary.txt", "text/plain")


def render_sidebar(file_status: pd.DataFrame) -> None:
    """사이드바."""
    with st.sidebar:
        st.header("Portfolio VaR Dashboard")
        st.caption("한국주식 · 미국주식 · 원화 현금")
        st.divider()
        st.markdown("#### 파일 상태")
        for _, row in file_status.iterrows():
            icon = "✅" if row["존재"] else "❌"
            st.caption(f"{icon} {row['산출물']}")
        st.divider()
        if PORTFOLIO_CONFIG_FILE.exists():
            st.download_button(
                "portfolio_config.json 다운로드",
                PORTFOLIO_CONFIG_FILE.read_bytes(),
                "portfolio_config.json",
                "application/json",
                use_container_width=True,
            )
        if REPORT_FILE.exists():
            st.download_button(
                "report_summary.txt 다운로드",
                REPORT_FILE.read_bytes(),
                "report_summary.txt",
                "text/plain",
                use_container_width=True,
            )


def main() -> None:
    """대시보드 진입점."""
    configure_page()
    apply_custom_css()

    st.title("RiskFolio")
    st.markdown(
        '',
        unsafe_allow_html=True,
    )

    data = load_dashboard_data()
    file_status = check_file_status()
    render_sidebar(file_status)

    tabs = st.tabs(
        [
            "Portfolio Input",
            "Overview",
            "Position Summary",
            "Risk Summary",
            "Asset Risk",
            "Portfolio Trend",
            "VaR Analysis",
            "Backtesting",
            "Correlation",
            "Stress Test",
            "Charts",
            "Raw Data",
            "용어 해설",
            "Report",
        ]
    )
    with tabs[0]:
        render_portfolio_input_tab(data)
    with tabs[1]:
        render_overview_tab(data)
    with tabs[2]:
        render_position_summary_tab(data)
    with tabs[3]:
        render_risk_summary_tab(data)
    with tabs[4]:
        render_asset_risk_tab(data)
    with tabs[5]:
        render_portfolio_trend_tab(data)
    with tabs[6]:
        render_var_analysis_tab(data)
    with tabs[7]:
        render_backtesting_tab(data)
    with tabs[8]:
        render_correlation_tab(data)
    with tabs[9]:
        render_stress_test_tab(data)
    with tabs[10]:
        render_charts_tab()
    with tabs[11]:
        render_raw_data_tab(data)
    with tabs[12]:
        render_risk_glossary_tab()
    with tabs[13]:
        render_report_tab(data)

    st.markdown(
        """
        <div class="footer-note">
            본 대시보드는 과거 데이터 기반 리스크 측정 도구이며 투자 손실을 예측하거나 보장하지 않습니다.
        </div>
        """,
        unsafe_allow_html=True,
    )


if __name__ == "__main__":
    main()
