"""10단계: 다자산 포트폴리오 차트와 텍스트 리포트를 생성한다."""

from __future__ import annotations

import json
import logging
from itertools import combinations
from pathlib import Path
from typing import Any

import matplotlib.pyplot as plt
import numpy as np
import pandas as pd

import matplotlib as mpl
from matplotlib import font_manager

from matplotlib.text import Text

KOREAN_FONT_PROP = None


def set_korean_matplotlib_font() -> None:
    """Matplotlib 저장 이미지에서 한글이 깨지지 않도록 폰트를 강제 설정한다."""
    global KOREAN_FONT_PROP

    font_paths = [
        "/usr/share/fonts/opentype/noto/NotoSansCJK-Regular.ttc",
        "/usr/share/fonts/opentype/noto/NotoSansCJK-Bold.ttc",
        "/usr/share/fonts/truetype/nanum/NanumGothic.ttf",
        "C:/Windows/Fonts/malgun.ttf",
        "/System/Library/Fonts/AppleGothic.ttf",
    ]

    for font_path in font_paths:
        path = Path(font_path)
        if path.exists():
            font_manager.fontManager.addfont(str(path))
            KOREAN_FONT_PROP = font_manager.FontProperties(fname=str(path))
            font_name = KOREAN_FONT_PROP.get_name()

            mpl.rcParams["font.family"] = font_name
            mpl.rcParams["axes.unicode_minus"] = False
            plt.rcParams["font.family"] = font_name
            plt.rcParams["axes.unicode_minus"] = False
            return

    # fallback
    mpl.rcParams["axes.unicode_minus"] = False
    plt.rcParams["axes.unicode_minus"] = False


def apply_korean_font_to_figure(fig=None) -> None:
    """이미 생성된 Matplotlib figure 안의 모든 텍스트 객체에 한글 폰트를 강제 적용한다."""
    if KOREAN_FONT_PROP is None:
        return

    if fig is None:
        fig = plt.gcf()

    for text in fig.findobj(match=Text):
        text.set_fontproperties(KOREAN_FONT_PROP)

set_korean_matplotlib_font()

from config import (
    ASSET_MASTER_FILE,
    ASSET_RISK_SUMMARY_FILE,
    CHART_DIR,
    CORRELATION_FILE,
    DRAWDOWN_FILE,
    PORTFOLIO_CONFIG_FILE,
    PORTFOLIO_RETURNS_FILE,
    PORTFOLIO_VALUE_FILE,
    POSITION_SUMMARY_FILE,
    REPORT_FILE,
    RISK_SUMMARY_FILE,
    STRESS_TEST_FILE,
    VAR_BACKTEST_CHART_FILE,
    VAR_BACKTEST_SUMMARY_FILE,
    ensure_directories,
)


def configure_logging() -> None:
    """단계 실행 상태를 콘솔에 표시하도록 logging을 설정한다."""
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s | %(levelname)s | %(message)s",
        datefmt="%H:%M:%S",
    )


def configure_matplotlib() -> None:
    """Windows에서 한글과 음수 기호가 안정적으로 표시되도록 설정한다."""
    plt.rcParams["font.family"] = "Malgun Gothic"
    plt.rcParams["axes.unicode_minus"] = False


def read_indexed_csv(file_path: Path) -> pd.DataFrame:
    """날짜 인덱스 CSV를 읽는다."""
    if not file_path.exists():
        raise FileNotFoundError(f"{file_path}가 없습니다. 먼저 이전 단계를 실행하세요.")
    frame = pd.read_csv(file_path, encoding="utf-8-sig", index_col="날짜", parse_dates=["날짜"])
    frame.index = pd.to_datetime(frame.index)
    frame = frame[~frame.index.duplicated(keep="last")].sort_index()
    frame.index.name = "날짜"
    return frame


def read_csv(file_path: Path) -> pd.DataFrame:
    """일반 CSV를 읽는다."""
    if not file_path.exists():
        raise FileNotFoundError(f"{file_path}가 없습니다. 먼저 이전 단계를 실행하세요.")
    return pd.read_csv(file_path, encoding="utf-8-sig")


def normalize_correlation_matrix(correlation: pd.DataFrame | None) -> pd.DataFrame:
    """CSV 저장/재로딩 중 깨진 상관관계 행렬의 index와 columns를 안전하게 정규화한다."""
    if correlation is None or correlation.empty:
        return pd.DataFrame()

    matrix = correlation.copy()
    logging.debug(
        "Raw correlation matrix shape=%s index=%s columns=%s",
        matrix.shape,
        list(matrix.index),
        list(matrix.columns),
    )

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
        logging.debug(
            "Correlation matrix has fewer than two common assets after normalization. "
            "shape=%s index=%s columns=%s",
            matrix.shape,
            list(matrix.index),
            list(matrix.columns),
        )
        return pd.DataFrame()

    matrix = matrix.loc[common_assets, common_assets]
    matrix = matrix.apply(pd.to_numeric, errors="coerce")
    logging.debug(
        "Normalized correlation matrix shape=%s index=%s columns=%s",
        matrix.shape,
        list(matrix.index),
        list(matrix.columns),
    )
    return matrix


def build_display_name_map(
    position_summary: pd.DataFrame | None = None,
    asset_master: pd.DataFrame | None = None,
) -> dict[str, str]:
    """티커를 회사명 기반 표시명으로 바꾸는 매핑을 만든다."""
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


def display_name(ticker: Any, name_map: dict[str, str]) -> str:
    """표시명 매핑이 있으면 표시명을, 없으면 티커 문자열을 반환한다."""
    ticker_text = str(ticker).strip()
    return name_map.get(ticker_text, ticker_text)


def shorten_chart_label(label: str, max_length: int = 26) -> str:
    """차트 축에서 지나치게 긴 표시명을 완만하게 줄인다."""
    label = str(label)
    if len(label) <= max_length:
        return label
    return f"{label[: max_length - 1]}…"


def load_inputs() -> dict[str, Any]:
    """시각화와 리포트 생성에 필요한 산출물을 로드한다."""
    correlation = (
        pd.read_csv(CORRELATION_FILE, encoding="utf-8-sig", index_col=0)
        if CORRELATION_FILE.exists()
        else pd.DataFrame()
    )
    correlation = normalize_correlation_matrix(correlation)

    config = (
        json.loads(PORTFOLIO_CONFIG_FILE.read_text(encoding="utf-8"))
        if PORTFOLIO_CONFIG_FILE.exists()
        else {}
    )
    position_summary = read_csv(POSITION_SUMMARY_FILE)
    asset_master = (
        pd.read_csv(ASSET_MASTER_FILE, encoding="utf-8-sig", dtype=str)
        if ASSET_MASTER_FILE.exists()
        else pd.DataFrame()
    )

    return {
        "config": config,
        "portfolio_returns": read_indexed_csv(PORTFOLIO_RETURNS_FILE),
        "portfolio_values": read_indexed_csv(PORTFOLIO_VALUE_FILE),
        "drawdown": read_indexed_csv(DRAWDOWN_FILE),
        "position_summary": position_summary,
        "asset_master": asset_master,
        "risk_summary": read_csv(RISK_SUMMARY_FILE),
        "asset_risk_summary": read_csv(ASSET_RISK_SUMMARY_FILE),
        "stress_test": read_csv(STRESS_TEST_FILE),
        "correlation": correlation,
        "backtest_summary": (
            pd.read_csv(VAR_BACKTEST_SUMMARY_FILE, encoding="utf-8-sig")
            if VAR_BACKTEST_SUMMARY_FILE.exists()
            else pd.DataFrame()
        ),
    }


def get_metric(summary: pd.DataFrame, metric_name: str, column: str = "수익률") -> float | None:
    """리스크 요약표에서 특정 지표의 값을 읽는다."""
    if not {"지표", column}.issubset(summary.columns):
        return None
    matched = summary.loc[summary["지표"] == metric_name, column]
    if matched.empty or pd.isna(matched.iloc[0]):
        return None
    return float(matched.iloc[0])


def format_won(value: Any) -> str:
    """원화 금액 표시."""
    if value is None or pd.isna(value):
        return "N/A"
    return f"{float(value):,.0f}원"


def format_percent(value: Any) -> str:
    """비율 표시."""
    if value is None or pd.isna(value):
        return "N/A"
    return f"{float(value):.2%}"


def format_signed_won(value: Any) -> str:
    """손익 원화 표시."""
    if value is None or pd.isna(value):
        return "N/A"
    number = float(value)
    if abs(number) < 0.5:
        return "0원"
    sign = "+" if number > 0 else "-"
    return f"{sign}{abs(number):,.0f}원"


def format_signed_percent(value: Any) -> str:
    """손익률 표시."""
    if value is None or pd.isna(value):
        return "N/A"
    number = float(value)
    if abs(number) < 0.00005:
        return "0.00%"
    sign = "+" if number > 0 else "-"
    return f"{sign}{abs(number):.2%}"


def create_portfolio_value_chart(portfolio_values: pd.DataFrame) -> Path:
    """전체 포트폴리오 가치 추이 차트를 저장한다."""
    output_path = CHART_DIR / "portfolio_value.png"
    plt.figure(figsize=(12, 6))
    plt.plot(portfolio_values.index, portfolio_values["TOTAL_VALUE_KRW"], label="포트폴리오 가치")
    plt.title("전체 포트폴리오 원화 평가금액")
    plt.xlabel("날짜")
    plt.ylabel("평가금액 (원)")
    plt.grid(True, alpha=0.3)
    plt.legend()
    plt.tight_layout()
    apply_korean_font_to_figure(plt.gcf())
    plt.savefig(output_path, dpi=150)
    plt.close()
    return output_path


def create_cumulative_return_chart(portfolio_returns: pd.DataFrame) -> Path:
    """누적수익률 차트를 저장한다."""
    output_path = CHART_DIR / "cumulative_return.png"
    plt.figure(figsize=(12, 6))
    plt.plot(portfolio_returns.index, portfolio_returns["누적수익률"] * 100, label="누적수익률")
    plt.title("전체 포트폴리오 누적수익률")
    plt.xlabel("날짜")
    plt.ylabel("누적수익률 (%)")
    plt.grid(True, alpha=0.3)
    plt.legend()
    plt.tight_layout()
    apply_korean_font_to_figure(plt.gcf())
    plt.savefig(output_path, dpi=150)
    plt.close()
    return output_path


def create_return_distribution_chart(portfolio_returns: pd.DataFrame, historical_var_95: float | None) -> Path:
    """수익률 분포와 95% Historical VaR 기준선 차트를 저장한다."""
    output_path = CHART_DIR / "return_distribution.png"
    returns_percent = portfolio_returns["포트폴리오_수익률"] * 100
    plt.figure(figsize=(12, 6))
    plt.hist(returns_percent, bins=50, label="일별 포트폴리오 수익률")
    if historical_var_95 is not None:
        cutoff = -historical_var_95 * 100
        plt.axvline(cutoff, linestyle="--", linewidth=2, label=f"95% Historical VaR ({cutoff:.2f}%)")
    plt.title("전체 포트폴리오 일별 수익률 분포")
    plt.xlabel("일별 수익률 (%)")
    plt.ylabel("빈도")
    plt.grid(True, alpha=0.3)
    plt.legend()
    plt.tight_layout()
    apply_korean_font_to_figure(plt.gcf())
    plt.savefig(output_path, dpi=150)
    plt.close()
    return output_path


def create_drawdown_chart(drawdown: pd.DataFrame) -> Path:
    """Drawdown 차트를 저장한다."""
    output_path = CHART_DIR / "drawdown.png"
    plt.figure(figsize=(12, 6))
    plt.plot(drawdown.index, drawdown["Drawdown"] * 100, label="Drawdown")
    plt.title("전체 포트폴리오 Drawdown")
    plt.xlabel("날짜")
    plt.ylabel("Drawdown (%)")
    plt.grid(True, alpha=0.3)
    plt.legend()
    plt.tight_layout()
    apply_korean_font_to_figure(plt.gcf())
    plt.savefig(output_path, dpi=150)
    plt.close()
    return output_path


def create_asset_weights_chart(position_summary: pd.DataFrame, name_map: dict[str, str]) -> Path:
    """현재 자산별 비중 막대그래프를 저장한다."""
    output_path = CHART_DIR / "asset_weights.png"
    labels = [
        shorten_chart_label(row.get("표시명") or display_name(row["티커"], name_map))
        for _, row in position_summary.iterrows()
    ]
    plt.figure(figsize=(12, 6))
    plt.bar(labels, position_summary["포트폴리오비중"] * 100)
    plt.title("현재 자산별 포트폴리오 비중")
    plt.xlabel("자산")
    plt.ylabel("비중 (%)")
    plt.xticks(rotation=25, ha="right")
    plt.grid(axis="y", alpha=0.3)
    plt.tight_layout()
    apply_korean_font_to_figure(plt.gcf())
    plt.savefig(output_path, dpi=150)
    plt.close()
    return output_path


def create_correlation_heatmap(correlation: pd.DataFrame, name_map: dict[str, str]) -> Path:
    """자산 수익률 상관관계 히트맵을 저장한다."""
    matrix = normalize_correlation_matrix(correlation)
    output_path = CHART_DIR / "correlation_heatmap.png"
    plt.figure(figsize=(8, 6))
    if matrix.empty:
        plt.text(0.5, 0.5, "상관관계 데이터 없음", ha="center", va="center", fontsize=14)
        plt.axis("off")
    else:
        display_columns = [shorten_chart_label(display_name(column, name_map), 24) for column in matrix.columns]
        display_index = [shorten_chart_label(display_name(index, name_map), 24) for index in matrix.index]
        image = plt.imshow(matrix, cmap="RdBu_r", vmin=-1, vmax=1)
        plt.colorbar(image, fraction=0.046, pad=0.04)
        plt.xticks(range(len(matrix.columns)), display_columns, rotation=45, ha="right")
        plt.yticks(range(len(matrix.index)), display_index)
        for row in range(len(matrix.index)):
            for col in range(len(matrix.columns)):
                plt.text(col, row, f"{matrix.iloc[row, col]:.2f}", ha="center", va="center", fontsize=9)
        plt.title("자산별 수익률 상관관계")
    plt.tight_layout()
    apply_korean_font_to_figure(plt.gcf())
    plt.savefig(output_path, dpi=150)
    plt.close()
    return output_path


def find_highest_correlation_pair(correlation: pd.DataFrame, name_map: dict[str, str] | None = None) -> str:
    """상관관계가 가장 높은 자산쌍을 문자열로 반환한다."""
    matrix = normalize_correlation_matrix(correlation)
    name_map = name_map or {}

    if matrix.empty or len(matrix.columns) < 2:
        return "비교 가능한 위험자산 쌍이 없습니다."

    best_pair = None
    best_value = None

    for left, right in combinations(matrix.columns, 2):
        try:
            value = float(matrix.loc[left, right])
        except (KeyError, TypeError, ValueError):
            continue

        if pd.isna(value):
            continue

        if best_value is None or abs(value) > abs(best_value):
            best_value = value
            best_pair = (left, right)

    if best_pair is None:
        return "비교 가능한 위험자산 쌍이 없습니다."

    left_name = display_name(best_pair[0], name_map)
    right_name = display_name(best_pair[1], name_map)
    return f"{left_name} - {right_name}: {best_value:.2f}"


def build_backtest_lines(backtest_summary: pd.DataFrame) -> str:
    """백테스팅 요약 문장을 만든다."""
    if backtest_summary.empty:
        return "- 백테스팅 결과 파일이 없습니다."
    lines = []
    for _, row in backtest_summary.iterrows():
        p_value = row.get("Kupiec_p_value")
        p_value_text = "N/A" if pd.isna(p_value) else f"{float(p_value):.4f}"
        lines.append(
            f"- {row['방법론']} {row['신뢰수준']}: 관측일수 {int(row['관측일수']):,}일, "
            f"예상 초과횟수 {float(row['예상초과횟수']):.1f}회, 실제 초과횟수 {int(row['실제초과횟수']):,}회, "
            f"Kupiec p-value {p_value_text}, 판정 {row['판정']}"
        )
    return "\n".join(lines)


def build_report_text(data: dict[str, Any]) -> str:
    """최종 텍스트 리포트를 생성한다."""
    position_summary = data["position_summary"]
    risk_summary = data["risk_summary"]
    asset_risk_summary = data["asset_risk_summary"]
    stress_test = data["stress_test"]
    correlation = data["correlation"]
    backtest_summary = data["backtest_summary"]
    portfolio_returns = data["portfolio_returns"]
    asset_master = data.get("asset_master", pd.DataFrame())
    name_map = build_display_name_map(position_summary, asset_master)

    total_value = float(position_summary["현재평가금액_원화"].sum())
    cash_value = float(position_summary.loc[position_summary["시장"] == "CASH", "현재평가금액_원화"].sum())
    risky_value = total_value - cash_value
    cash_weight = cash_value / total_value if total_value else 0.0
    risky_weight = risky_value / total_value if total_value else 0.0
    investment_value = None
    total_profit = None
    total_profit_rate = None
    profit_basis_text = "전체 자산 매수가 기준"
    if {"매수금액_원화", "총수익_원화"}.issubset(position_summary.columns):
        purchase_amounts = pd.to_numeric(position_summary["매수금액_원화"], errors="coerce")
        profits = pd.to_numeric(position_summary["총수익_원화"], errors="coerce")
        if purchase_amounts.notna().all() and profits.notna().all() and purchase_amounts.sum() > 0:
            investment_value = float(purchase_amounts.sum())
            total_profit = float(profits.sum())
            total_profit_rate = total_profit / investment_value
        else:
            profit_basis_text = "매수가격이 누락된 자산이 있어 전체 평가손익은 N/A입니다."

    annual_volatility = get_metric(risk_summary, "연환산 변동성")
    mdd = get_metric(risk_summary, "MDD")
    hvar95 = get_metric(risk_summary, "95% Historical VaR")
    hes95 = get_metric(risk_summary, "95% Historical ES")
    hvar95_amount = get_metric(risk_summary, "95% Historical VaR", "금액")
    hes95_amount = get_metric(risk_summary, "95% Historical ES", "금액")

    if "95% Historical VaR 금액" in asset_risk_summary.columns and not asset_risk_summary.empty:
        largest_var_asset = asset_risk_summary.sort_values("95% Historical VaR 금액", ascending=False).iloc[0]
        largest_var_name = display_name(largest_var_asset["티커"], name_map)
        largest_var_text = (
            f"{largest_var_name} "
            f"({format_won(largest_var_asset['95% Historical VaR 금액'])})"
        )
    else:
        largest_var_text = "N/A"

    largest_weight_asset = position_summary.sort_values("포트폴리오비중", ascending=False).iloc[0]
    largest_weight_name = display_name(largest_weight_asset["티커"], name_map)
    largest_weight_text = f"{largest_weight_name} ({format_percent(largest_weight_asset['포트폴리오비중'])})"

    stress_lines = "\n".join(
        f"- {row['시나리오']}: 예상손실 {format_won(row['예상손실금액'])}, "
        f"예상손실률 {format_percent(row['예상손실률'])}, "
        f"스트레스 후 가치 {format_won(row['스트레스후포트폴리오가치'])}"
        for _, row in stress_test.iterrows()
    )
    position_lines = "\n".join(
        f"- {row['시장']} {display_name(row['티커'], name_map)}: 수량 {row['수량']:g}, 평가금액 {format_won(row['현재평가금액_원화'])}, "
        f"비중 {format_percent(row['포트폴리오비중'])}"
        for _, row in position_summary.iterrows()
    )

    return f"""다자산 포트폴리오 VaR 기반 리스크 측정 프로젝트
{'=' * 72}

1. 입력 포트폴리오 요약
본 프로젝트는 사용자가 입력한 한국주식, 미국주식, 원화 현금을 원화 기준으로 평가한 뒤 포트폴리오 손실위험을 측정합니다.
미국주식은 일별 USD/KRW 환율을 적용해 원화 평가금액으로 변환했으며, 미국주식 수익률에는 주가 변동과 환율 변동이 함께 반영됩니다.

{position_lines}

2. 현재 포트폴리오 구성
- 현재 총 포트폴리오 가치: {format_won(total_value)}
- 위험자산 평가금액: {format_won(risky_value)}
- 현금: {format_won(cash_value)}
- 위험자산 비중: {format_percent(risky_weight)}
- 현금 비중: {format_percent(cash_weight)}
- 총 투자원금: {format_won(investment_value)}
- 총 평가손익: {format_signed_won(total_profit)}
- 평가 수익률: {format_signed_percent(total_profit_rate)}
- 평가손익 계산 기준: {profit_basis_text}
- 분석 기간: {portfolio_returns.index.min():%Y-%m-%d} ~ {portfolio_returns.index.max():%Y-%m-%d}
- 유효 관측일수: {len(portfolio_returns):,}일

3. 전체 포트폴리오 핵심 리스크
- 연환산 변동성: {format_percent(annual_volatility)}
- MDD: {format_percent(mdd)}
- 95% Historical VaR: {format_percent(hvar95)} / {format_won(hvar95_amount)}
- 95% Historical ES: {format_percent(hes95)} / {format_won(hes95_amount)}

4. 개별 자산 리스크 하이라이트
- 95% Historical VaR 금액이 가장 큰 자산: {largest_var_text}
- 포트폴리오 비중이 가장 큰 자산: {largest_weight_text}
- 상관관계가 가장 높은 자산쌍: {find_highest_correlation_pair(correlation, name_map)}

5. 스트레스 테스트 요약
위험자산에는 시나리오별 하락 충격을 적용하고 현금에는 손실을 적용하지 않았습니다.
{stress_lines}

6. VaR 백테스팅 요약
{build_backtest_lines(backtest_summary)}

7. 결측치 및 환율 처리 가정
- 한국과 미국 시장의 휴장일 차이는 outer join 후 forward-fill로 처리했습니다.
- 휴장일에는 직전 거래일 가격이 유지된다고 가정합니다.
- 미국주식은 달러 종가 × 수량 × USD/KRW 환율로 원화 평가금액을 계산했습니다.
- 한국주식 매수가격은 원화 기준입니다.
- 미국주식 매수가격은 달러 기준입니다.
- 미국주식의 매수금액 원화 환산에는 매수일자 기준 USD/KRW 환율을 사용했습니다.
- 미국주식의 현재평가금액 원화 환산에는 최신 USD/KRW 환율을 사용했습니다.
- 따라서 미국주식의 평가 수익률에는 주가 변동과 환율 변동이 함께 반영됩니다.

8. 한계점
- 과거 수익률 기반 분석이므로 미래 손실을 보장하지 않습니다.
- 배당, 세금, 수수료, 슬리피지는 반영하지 않았습니다.
- Monte Carlo는 과거 평균·변동성 또는 공분산 구조가 유지된다는 가정에 의존합니다.
- 데이터 제공처의 가격·환율 결측 또는 수정 방식에 영향을 받을 수 있습니다.
"""


def save_report(report_text: str) -> None:
    """최종 리포트를 저장한다."""
    REPORT_FILE.write_text(report_text, encoding="utf-8")


def main() -> None:
    """차트와 텍스트 리포트를 생성한다."""
    configure_logging()
    configure_matplotlib()
    ensure_directories()
    data = load_inputs()
    name_map = build_display_name_map(data["position_summary"], data.get("asset_master"))

    historical_var_95 = get_metric(data["risk_summary"], "95% Historical VaR")
    chart_paths = [
        create_portfolio_value_chart(data["portfolio_values"]),
        create_cumulative_return_chart(data["portfolio_returns"]),
        create_return_distribution_chart(data["portfolio_returns"], historical_var_95),
        create_drawdown_chart(data["drawdown"]),
        create_asset_weights_chart(data["position_summary"], name_map),
        create_correlation_heatmap(data["correlation"], name_map),
    ]
    if VAR_BACKTEST_CHART_FILE.exists():
        chart_paths.append(VAR_BACKTEST_CHART_FILE)

    report_text = build_report_text(data)
    save_report(report_text)

    print("\n" + "=" * 70)
    print("10단계 완료: 다자산 포트폴리오 시각화 및 리포트 생성")
    print("=" * 70)
    for chart_path in chart_paths:
        print(f"그래프 저장: {chart_path}")
    print(f"리포트 저장: {REPORT_FILE}")


if __name__ == "__main__":
    main()
