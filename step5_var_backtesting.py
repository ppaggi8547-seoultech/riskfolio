"""5단계 확장: Rolling window 방식으로 Historical/Parametric VaR 백테스팅을 수행한다.

백테스팅은 룩어헤드 편향을 피하기 위해 t일 이전의 과거 N거래일 수익률만 사용해
t일 VaR을 추정하고, 그 t일의 실제 수익률과 비교한다.
"""

from __future__ import annotations

import logging
from math import erfc, isfinite, log, sqrt
from pathlib import Path
from statistics import NormalDist

import matplotlib.pyplot as plt
import numpy as np
import pandas as pd

import matplotlib as mpl
from matplotlib import font_manager
from matplotlib.text import Text

KOREAN_FONT_PROP = None


def set_korean_matplotlib_font() -> None:
    """VaR 백테스팅 Matplotlib 차트에서 한글 깨짐을 방지한다."""
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

    mpl.rcParams["axes.unicode_minus"] = False
    plt.rcParams["axes.unicode_minus"] = False


def apply_korean_font_to_figure(fig=None) -> None:
    """이미 생성된 Matplotlib figure 안의 모든 텍스트에 한글 폰트를 강제 적용한다."""
    if KOREAN_FONT_PROP is None:
        return

    if fig is None:
        fig = plt.gcf()

    for text in fig.findobj(match=Text):
        text.set_fontproperties(KOREAN_FONT_PROP)


set_korean_matplotlib_font()

from config import (
    BACKTEST_CONFIDENCE_LEVELS,
    BACKTEST_WINDOW,
    PORTFOLIO_RETURNS_FILE,
    VAR_BACKTEST_CHART_FILE,
    VAR_BACKTEST_FILE,
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


def confidence_suffix(confidence_level: float) -> str:
    """0.95를 95 같은 컬럼명 접미사로 변환한다."""
    return f"{confidence_level:.0%}".replace("%", "")


def confidence_label(confidence_level: float) -> str:
    """0.95를 95% 같은 보고서용 문자열로 변환한다."""
    return f"{confidence_level:.0%}"


def non_negative_loss(value: float) -> float:
    """VaR 손실률을 0 이상으로 정리하고 -0.0 표시를 방지한다."""
    cleaned = max(float(value), 0.0)
    return 0.0 if abs(cleaned) < 1e-15 else cleaned


def load_portfolio_returns() -> pd.DataFrame:
    """portfolio_returns.csv를 읽고 백테스팅에 필요한 수익률 컬럼을 검증한다."""
    if not PORTFOLIO_RETURNS_FILE.exists():
        raise FileNotFoundError(
            f"{PORTFOLIO_RETURNS_FILE}가 없습니다. 먼저 step2_return_calculation.py를 실행하세요."
        )

    try:
        portfolio = pd.read_csv(
            PORTFOLIO_RETURNS_FILE,
            encoding="utf-8-sig",
            index_col="날짜",
            parse_dates=["날짜"],
        )
    except Exception as exc:
        raise ValueError(f"포트폴리오 파일을 읽을 수 없습니다: {PORTFOLIO_RETURNS_FILE}") from exc

    if "포트폴리오_수익률" not in portfolio.columns:
        raise ValueError("portfolio_returns.csv에 '포트폴리오_수익률' 컬럼이 없습니다.")

    portfolio.index = pd.to_datetime(portfolio.index)
    portfolio = portfolio[~portfolio.index.duplicated(keep="last")].sort_index()
    portfolio["포트폴리오_수익률"] = pd.to_numeric(
        portfolio["포트폴리오_수익률"],
        errors="coerce",
    )
    portfolio = portfolio.dropna(subset=["포트폴리오_수익률"])

    if len(portfolio) <= BACKTEST_WINDOW:
        raise ValueError(
            f"백테스팅에는 rolling window({BACKTEST_WINDOW}거래일)보다 많은 수익률 데이터가 필요합니다. "
            f"현재 유효 관측치: {len(portfolio):,}개"
        )

    portfolio.index.name = "날짜"
    return portfolio


def calculate_rolling_historical_var(
    returns: pd.Series,
    confidence_level: float,
    window: int = BACKTEST_WINDOW,
) -> pd.Series:
    """과거 window개 수익률만 사용해 매일 Historical VaR를 계산한다."""
    var_values: list[float] = []
    for index in range(window, len(returns)):
        window_returns = returns.iloc[index - window : index]
        quantile = float(np.quantile(window_returns, 1 - confidence_level))
        var_values.append(non_negative_loss(-quantile))

    return pd.Series(
        var_values,
        index=returns.index[window:],
        name=f"Historical_VaR_{confidence_suffix(confidence_level)}",
    )


def calculate_rolling_parametric_var(
    returns: pd.Series,
    confidence_level: float,
    window: int = BACKTEST_WINDOW,
) -> pd.Series:
    """과거 window개 수익률의 평균·표준편차로 매일 Parametric VaR를 계산한다."""
    var_values: list[float] = []
    z_score = NormalDist().inv_cdf(1 - confidence_level)

    for index in range(window, len(returns)):
        window_returns = returns.iloc[index - window : index]
        mean_return = float(window_returns.mean())
        std_return = float(window_returns.std(ddof=1))
        if np.isnan(std_return) or std_return == 0:
            var_value = non_negative_loss(-mean_return)
        else:
            var_value = -(mean_return + z_score * std_return)
        var_values.append(non_negative_loss(var_value))

    return pd.Series(
        var_values,
        index=returns.index[window:],
        name=f"Parametric_VaR_{confidence_suffix(confidence_level)}",
    )


def safe_log_likelihood(observations: int, breaches: int, probability: float) -> float:
    """이항 로그우도를 x=0 또는 x=n인 경계 케이스까지 안전하게 계산한다."""
    if probability <= 0 or probability >= 1:
        if breaches == 0 and probability == 0:
            return 0.0
        if breaches == observations and probability == 1:
            return 0.0
        return float("nan")

    if breaches == 0:
        return observations * log(1 - probability)

    if breaches == observations:
        return observations * log(probability)

    return (observations - breaches) * log(1 - probability) + breaches * log(probability)


def calculate_kupiec_test(
    observations: int,
    breaches: int,
    expected_probability: float,
) -> tuple[float, float, str]:
    """Kupiec unconditional coverage test의 LR 통계량, p-value, 판정을 계산한다."""
    if observations <= 0 or breaches < 0 or breaches > observations:
        return float("nan"), float("nan"), "계산불가"

    actual_probability = breaches / observations
    log_likelihood_null = safe_log_likelihood(
        observations,
        breaches,
        expected_probability,
    )
    log_likelihood_alternative = safe_log_likelihood(
        observations,
        breaches,
        actual_probability,
    )

    if not isfinite(log_likelihood_null) or not isfinite(log_likelihood_alternative):
        return float("nan"), float("nan"), "계산불가"

    lr_statistic = -2 * (log_likelihood_null - log_likelihood_alternative)
    if lr_statistic < 0:
        lr_statistic = 0.0

    # 자유도 1인 카이제곱분포의 survival function: sf(x) = erfc(sqrt(x / 2))
    p_value = erfc(sqrt(lr_statistic / 2))
    decision = "통과" if p_value >= 0.05 else "실패"
    return float(lr_statistic), float(p_value), decision


def run_var_backtest(
    portfolio: pd.DataFrame,
    window: int = BACKTEST_WINDOW,
    confidence_levels: list[float] | None = None,
) -> pd.DataFrame:
    """Historical/Parametric VaR를 rolling window 방식으로 추정하고 breach 여부를 계산한다."""
    levels = confidence_levels or BACKTEST_CONFIDENCE_LEVELS
    returns = portfolio["포트폴리오_수익률"].dropna().copy()

    backtest = pd.DataFrame(
        {
            "날짜": returns.index[window:],
            "실제수익률": returns.iloc[window:].to_numpy(),
        }
    )
    backtest.index = returns.index[window:]

    for confidence_level in levels:
        suffix = confidence_suffix(confidence_level)
        historical_var = calculate_rolling_historical_var(returns, confidence_level, window)
        parametric_var = calculate_rolling_parametric_var(returns, confidence_level, window)

        backtest[f"Historical_VaR_{suffix}"] = historical_var.reindex(backtest.index).to_numpy()
        backtest[f"Historical_Breach_{suffix}"] = (
            backtest["실제수익률"] < -backtest[f"Historical_VaR_{suffix}"]
        )
        backtest[f"Parametric_VaR_{suffix}"] = parametric_var.reindex(backtest.index).to_numpy()
        backtest[f"Parametric_Breach_{suffix}"] = (
            backtest["실제수익률"] < -backtest[f"Parametric_VaR_{suffix}"]
        )

    ordered_columns = ["날짜", "실제수익률"]
    for confidence_level in levels:
        suffix = confidence_suffix(confidence_level)
        ordered_columns.extend([f"Historical_VaR_{suffix}", f"Historical_Breach_{suffix}"])
    for confidence_level in levels:
        suffix = confidence_suffix(confidence_level)
        ordered_columns.extend([f"Parametric_VaR_{suffix}", f"Parametric_Breach_{suffix}"])

    backtest = backtest.reset_index(drop=True)
    backtest = backtest[ordered_columns]
    backtest["날짜"] = pd.to_datetime(backtest["날짜"]).dt.strftime("%Y-%m-%d")
    return backtest


def summarize_backtest(
    backtest: pd.DataFrame,
    confidence_levels: list[float] | None = None,
) -> pd.DataFrame:
    """방법론·신뢰수준별 초과 빈도와 Kupiec test 결과를 요약한다."""
    levels = confidence_levels or BACKTEST_CONFIDENCE_LEVELS
    rows: list[dict[str, object]] = []

    for method in ("Historical", "Parametric"):
        for confidence_level in levels:
            suffix = confidence_suffix(confidence_level)
            breach_column = f"{method}_Breach_{suffix}"
            if breach_column not in backtest.columns:
                continue

            valid_breaches = backtest[breach_column].dropna().astype(bool)
            observations = int(valid_breaches.shape[0])
            actual_breaches = int(valid_breaches.sum())
            expected_probability = 1 - confidence_level
            expected_breaches = observations * expected_probability
            actual_breach_ratio = actual_breaches / observations if observations else np.nan
            lr_statistic, p_value, decision = calculate_kupiec_test(
                observations,
                actual_breaches,
                expected_probability,
            )

            rows.append(
                {
                    "방법론": f"{method} VaR",
                    "신뢰수준": confidence_label(confidence_level),
                    "관측일수": observations,
                    "예상초과확률": expected_probability,
                    "예상초과횟수": expected_breaches,
                    "실제초과횟수": actual_breaches,
                    "실제초과비율": actual_breach_ratio,
                    "초과횟수차이": actual_breaches - expected_breaches,
                    "Kupiec_LR": lr_statistic,
                    "Kupiec_p_value": p_value,
                    "판정": decision,
                }
            )

    return pd.DataFrame(rows)


def plot_backtest_results(backtest: pd.DataFrame) -> Path:
    """95% Historical VaR 기준선과 breach 발생일을 PNG 차트로 저장한다."""
    required_columns = {"날짜", "실제수익률", "Historical_VaR_95", "Historical_Breach_95"}
    missing_columns = required_columns.difference(backtest.columns)
    if missing_columns:
        raise ValueError(f"백테스트 차트에 필요한 컬럼이 없습니다: {sorted(missing_columns)}")

    chart_frame = backtest.copy()
    chart_frame["날짜"] = pd.to_datetime(chart_frame["날짜"])
    chart_frame["실제수익률(%)"] = chart_frame["실제수익률"] * 100
    chart_frame["-Historical VaR 95%(%)"] = -chart_frame["Historical_VaR_95"] * 100
    breach_frame = chart_frame[chart_frame["Historical_Breach_95"].astype(bool)]

    plt.figure(figsize=(13, 6))
    plt.plot(
        chart_frame["날짜"],
        chart_frame["실제수익률(%)"],
        label="실제수익률",
        linewidth=1.1,
        alpha=0.8,
    )
    plt.plot(
        chart_frame["날짜"],
        chart_frame["-Historical VaR 95%(%)"],
        label="-Historical VaR 95%",
        linestyle="--",
        linewidth=1.4,
        color="#1f77b4",
    )
    if not breach_frame.empty:
        plt.scatter(
            breach_frame["날짜"],
            breach_frame["실제수익률(%)"],
            color="#dc2626",
            label="VaR Breach",
            s=30,
            zorder=5,
        )

    plt.title("Historical VaR 95% Backtesting")
    plt.xlabel("날짜")
    plt.ylabel("수익률 (%)")
    plt.grid(True, alpha=0.3)
    plt.legend()
    plt.tight_layout()
    apply_korean_font_to_figure(plt.gcf())
    plt.savefig(VAR_BACKTEST_CHART_FILE, dpi=150)
    plt.close()
    return VAR_BACKTEST_CHART_FILE


def save_backtest_outputs(backtest: pd.DataFrame, summary: pd.DataFrame) -> None:
    """백테스트 결과 CSV와 요약 CSV를 UTF-8-SIG로 저장한다."""
    ensure_directories()
    backtest.to_csv(VAR_BACKTEST_FILE, index=False, encoding="utf-8-sig")
    summary.to_csv(VAR_BACKTEST_SUMMARY_FILE, index=False, encoding="utf-8-sig")


def main() -> None:
    """VaR 백테스팅 산출물 3종을 생성한다."""
    configure_logging()
    configure_matplotlib()
    ensure_directories()

    logging.info("VaR 백테스팅용 포트폴리오 수익률 로드 시작: %s", PORTFOLIO_RETURNS_FILE)
    portfolio = load_portfolio_returns()
    backtest = run_var_backtest(portfolio)
    summary = summarize_backtest(backtest)
    save_backtest_outputs(backtest, summary)
    chart_path = plot_backtest_results(backtest)

    print("\n" + "=" * 70)
    print("5단계 확장 완료: Rolling VaR 백테스팅")
    print("=" * 70)
    print(f"Rolling window: {BACKTEST_WINDOW:,}거래일")
    print(f"백테스트 관측일수: {len(backtest):,}일")
    print(f"백테스트 결과 저장: {VAR_BACKTEST_FILE}")
    print(f"백테스트 요약 저장: {VAR_BACKTEST_SUMMARY_FILE}")
    print(f"백테스트 차트 저장: {chart_path}")


if __name__ == "__main__":
    main()
