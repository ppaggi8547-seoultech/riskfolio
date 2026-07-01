"""4~9단계: 다자산 포트폴리오와 개별 자산의 리스크 지표를 계산한다."""

from __future__ import annotations

import logging
from math import exp, pi, sqrt
from statistics import NormalDist
from typing import Any

import numpy as np
import pandas as pd

from config import (
    ASSET_RETURN_FILE,
    ASSET_RISK_SUMMARY_FILE,
    ASSET_STRESS_TEST_FILE,
    ASSET_VALUE_FILE,
    CONFIDENCE_LEVELS,
    CORRELATION_FILE,
    DRAWDOWN_FILE,
    MONTE_CARLO_FILE,
    MONTE_CARLO_SIMULATIONS,
    PORTFOLIO_RETURNS_FILE,
    PORTFOLIO_VALUE_FILE,
    POSITION_SUMMARY_FILE,
    RANDOM_SEED,
    RISK_SUMMARY_FILE,
    STRESS_SCENARIOS,
    STRESS_TEST_FILE,
    TRADING_DAYS_PER_YEAR,
    ensure_directories,
)


def configure_logging() -> None:
    """단계 실행 상태를 콘솔에 표시하도록 logging을 설정한다."""
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s | %(levelname)s | %(message)s",
        datefmt="%H:%M:%S",
    )


def read_indexed_csv(file_path) -> pd.DataFrame:
    """날짜 인덱스 CSV를 읽고 숫자형 컬럼을 정리한다."""
    if not file_path.exists():
        raise FileNotFoundError(f"{file_path}가 없습니다. 먼저 이전 단계를 실행하세요.")
    frame = pd.read_csv(file_path, encoding="utf-8-sig", index_col="날짜", parse_dates=["날짜"])
    frame.index = pd.to_datetime(frame.index)
    frame = frame[~frame.index.duplicated(keep="last")].sort_index()
    frame.index.name = "날짜"
    for column in frame.columns:
        frame[column] = pd.to_numeric(frame[column], errors="coerce")
    return frame


def load_inputs() -> tuple[pd.DataFrame, pd.DataFrame, pd.DataFrame, pd.DataFrame, pd.DataFrame]:
    """리스크 계산에 필요한 산출물을 로드한다."""
    portfolio_returns = read_indexed_csv(PORTFOLIO_RETURNS_FILE)
    portfolio_values = read_indexed_csv(PORTFOLIO_VALUE_FILE)
    asset_returns = read_indexed_csv(ASSET_RETURN_FILE)
    asset_values = read_indexed_csv(ASSET_VALUE_FILE)

    if not POSITION_SUMMARY_FILE.exists():
        raise FileNotFoundError(f"{POSITION_SUMMARY_FILE}가 없습니다. 먼저 step2_return_calculation.py를 실행하세요.")
    position_summary = pd.read_csv(POSITION_SUMMARY_FILE, encoding="utf-8-sig")
    for column in ("수량", "현재가격_원화", "현재평가금액_원화", "포트폴리오비중"):
        if column in position_summary.columns:
            position_summary[column] = pd.to_numeric(position_summary[column], errors="coerce")

    required_portfolio_columns = {"포트폴리오_가치", "포트폴리오_수익률"}
    if missing := required_portfolio_columns.difference(portfolio_returns.columns):
        raise ValueError(f"portfolio_returns.csv에 필수 컬럼이 없습니다: {sorted(missing)}")
    if "TOTAL_VALUE_KRW" not in portfolio_values.columns:
        raise ValueError("portfolio_values.csv에 TOTAL_VALUE_KRW 컬럼이 없습니다.")
    return portfolio_returns, portfolio_values, asset_returns, asset_values, position_summary


def normal_pdf(value: float) -> float:
    """표준정규분포 PDF를 계산한다."""
    return exp(-0.5 * value * value) / sqrt(2 * pi)


def max_loss(value: float) -> float:
    """-0.0 같은 표현을 피하고 손실률은 0 이상으로 정리한다."""
    if pd.isna(value):
        return 0.0
    cleaned = max(float(value), 0.0)
    return 0.0 if abs(cleaned) < 1e-15 else cleaned


def calculate_drawdown_from_values(values: pd.Series) -> tuple[pd.Series, float]:
    """가치 시계열에서 drawdown과 MDD를 계산한다."""
    values = pd.to_numeric(values, errors="coerce").dropna()
    if values.empty:
        return pd.Series(dtype=float), 0.0
    running_max = values.cummax()
    drawdown = values / running_max - 1
    return drawdown, float(drawdown.min())


def calculate_tail_metrics(
    returns: pd.Series,
    current_value: float,
    rng: np.random.Generator,
    simulations: np.ndarray | None = None,
) -> dict[str, Any]:
    """수익률 시계열 하나의 변동성, VaR, ES, Monte Carlo 지표를 계산한다."""
    clean_returns = pd.to_numeric(returns, errors="coerce").dropna()
    if clean_returns.empty:
        clean_returns = pd.Series([0.0])

    mean_return = float(clean_returns.mean())
    daily_volatility = float(clean_returns.std(ddof=1)) if len(clean_returns) > 1 else 0.0
    if pd.isna(daily_volatility):
        daily_volatility = 0.0

    metrics: dict[str, Any] = {
        "일간 평균수익률": mean_return,
        "일간 변동성": daily_volatility,
        "연환산 평균수익률": mean_return * TRADING_DAYS_PER_YEAR,
        "연환산 변동성": daily_volatility * sqrt(TRADING_DAYS_PER_YEAR),
    }

    if simulations is None:
        if daily_volatility == 0:
            simulations = np.full(MONTE_CARLO_SIMULATIONS, mean_return)
        else:
            simulations = rng.normal(mean_return, daily_volatility, MONTE_CARLO_SIMULATIONS)

    normal_distribution = NormalDist()
    for confidence in CONFIDENCE_LEVELS:
        label = f"{confidence:.0%}"
        tail_probability = 1 - confidence
        historical_threshold = float(np.quantile(clean_returns, tail_probability))
        historical_tail = clean_returns[clean_returns <= historical_threshold]
        historical_var = max_loss(-historical_threshold)
        historical_es = max_loss(-float(historical_tail.mean())) if not historical_tail.empty else historical_var

        z_score = normal_distribution.inv_cdf(tail_probability)
        if daily_volatility == 0:
            parametric_var = max_loss(-mean_return)
            parametric_es = parametric_var
        else:
            parametric_cutoff = mean_return + z_score * daily_volatility
            parametric_var = max_loss(-parametric_cutoff)
            parametric_es = max_loss(-(mean_return - daily_volatility * normal_pdf(z_score) / tail_probability))

        monte_carlo_threshold = float(np.quantile(simulations, tail_probability))
        monte_carlo_tail = simulations[simulations <= monte_carlo_threshold]
        monte_carlo_var = max_loss(-monte_carlo_threshold)
        monte_carlo_es = (
            max_loss(-float(np.mean(monte_carlo_tail))) if len(monte_carlo_tail) else monte_carlo_var
        )

        metrics[f"{label} Historical VaR"] = historical_var
        metrics[f"{label} Historical VaR 금액"] = historical_var * current_value
        metrics[f"{label} Historical ES"] = historical_es
        metrics[f"{label} Historical ES 금액"] = historical_es * current_value
        metrics[f"{label} Parametric VaR"] = parametric_var
        metrics[f"{label} Parametric VaR 금액"] = parametric_var * current_value
        metrics[f"{label} Parametric ES"] = parametric_es
        metrics[f"{label} Parametric ES 금액"] = parametric_es * current_value
        metrics[f"{label} Monte Carlo VaR"] = monte_carlo_var
        metrics[f"{label} Monte Carlo VaR 금액"] = monte_carlo_var * current_value
        metrics[f"{label} Monte Carlo ES"] = monte_carlo_es
        metrics[f"{label} Monte Carlo ES 금액"] = monte_carlo_es * current_value

    return metrics


def generate_portfolio_monte_carlo(
    portfolio_returns: pd.Series,
    asset_returns: pd.DataFrame,
    position_summary: pd.DataFrame,
    rng: np.random.Generator,
) -> np.ndarray:
    """가능하면 자산 공분산과 현재 비중으로 포트폴리오 Monte Carlo 수익률을 생성한다."""
    risky_positions = position_summary[position_summary["시장"] != "CASH"].copy()
    risky_tickers = [ticker for ticker in risky_positions["티커"].astype(str) if ticker in asset_returns.columns]
    if len(risky_tickers) >= 2:
        returns = asset_returns[risky_tickers].dropna()
        if len(returns) >= 2:
            means = returns.mean().to_numpy(dtype=float)
            covariance = returns.cov().to_numpy(dtype=float)
            weights = (
                risky_positions.set_index("티커")
                .loc[risky_tickers, "포트폴리오비중"]
                .to_numpy(dtype=float)
            )
            try:
                simulated_assets = rng.multivariate_normal(
                    means,
                    covariance,
                    MONTE_CARLO_SIMULATIONS,
                    check_valid="ignore",
                )
                return simulated_assets @ weights
            except Exception as exc:
                logging.warning("공분산 기반 Monte Carlo 실패, 단일분포 방식으로 대체합니다: %s", exc)

    clean_returns = pd.to_numeric(portfolio_returns, errors="coerce").dropna()
    mean_return = float(clean_returns.mean()) if not clean_returns.empty else 0.0
    volatility = float(clean_returns.std(ddof=1)) if len(clean_returns) > 1 else 0.0
    if pd.isna(volatility) or volatility == 0:
        return np.full(MONTE_CARLO_SIMULATIONS, mean_return)
    return rng.normal(mean_return, volatility, MONTE_CARLO_SIMULATIONS)


def build_risk_summary(
    metrics: dict[str, Any],
    current_value: float,
    mdd: float,
    cumulative_return: float,
) -> pd.DataFrame:
    """전체 포트폴리오 리스크 요약표를 생성한다."""
    rows: list[dict[str, Any]] = []

    def add_row(category: str, metric: str, value: float, amount: float | None, description: str, confidence: str = "") -> None:
        rows.append(
            {
                "구분": category,
                "지표": metric,
                "신뢰수준": confidence,
                "수익률": value,
                "금액": amount,
                "현재평가금액_기준_금액": amount,
                "설명": description,
            }
        )

    add_row("포트폴리오 가치", "현재 포트폴리오 가치", np.nan, current_value, "분석 마지막 거래일 기준 총 평가금액")
    add_row("기초 리스크 지표", "일간 평균수익률", metrics["일간 평균수익률"], None, "분석기간 일별 포트폴리오 수익률 평균")
    add_row("기초 리스크 지표", "일간 변동성", metrics["일간 변동성"], None, "일별 포트폴리오 수익률 표준편차")
    add_row("기초 리스크 지표", "연환산 평균수익률", metrics["연환산 평균수익률"], None, "일간 평균수익률 × 252거래일")
    add_row("기초 리스크 지표", "연환산 변동성", metrics["연환산 변동성"], None, "일간 변동성 × √252")
    add_row("기초 리스크 지표", "누적수익률", cumulative_return, None, "평가 시작일 대비 누적수익률")
    add_row("기초 리스크 지표", "MDD", mdd, None, "분석기간 중 고점 대비 최대 하락률")

    for confidence in CONFIDENCE_LEVELS:
        label = f"{confidence:.0%}"
        for methodology in ("Historical", "Parametric", "Monte Carlo"):
            for risk_type in ("VaR", "ES"):
                metric_name = f"{label} {methodology} {risk_type}"
                add_row(
                    f"{methodology} {risk_type}",
                    metric_name,
                    metrics[metric_name],
                    metrics[f"{metric_name} 금액"],
                    f"{methodology} 방식의 {label} 1일 {risk_type}",
                    label,
                )

    return pd.DataFrame(rows)


def build_asset_risk_summary(
    asset_returns: pd.DataFrame,
    asset_values: pd.DataFrame,
    position_summary: pd.DataFrame,
    rng: np.random.Generator,
) -> pd.DataFrame:
    """개별 자산별 리스크 요약표를 생성한다."""
    rows: list[dict[str, Any]] = []
    for _, position in position_summary.iterrows():
        ticker = str(position["티커"])
        market = str(position["시장"])
        current_value = float(position["현재평가금액_원화"])
        weight = float(position["포트폴리오비중"])

        if ticker in asset_returns.columns:
            returns = asset_returns[ticker]
        else:
            returns = pd.Series(0.0, index=asset_returns.index)

        if ticker in asset_values.columns:
            _, mdd = calculate_drawdown_from_values(asset_values[ticker])
        else:
            mdd = 0.0

        metrics = calculate_tail_metrics(returns, current_value, rng)
        row: dict[str, Any] = {
            "자산명": position["자산명"],
            "시장": market,
            "티커": ticker,
            "수량": position["수량"],
            "비중": weight,
            "현재평가금액": current_value,
            "일간 평균수익률": metrics["일간 평균수익률"],
            "일간 변동성": metrics["일간 변동성"],
            "연환산 변동성": metrics["연환산 변동성"],
            "MDD": mdd,
        }
        for confidence in CONFIDENCE_LEVELS:
            label = f"{confidence:.0%}"
            for methodology in ("Historical", "Parametric", "Monte Carlo"):
                for risk_type in ("VaR", "ES"):
                    metric_name = f"{label} {methodology} {risk_type}"
                    row[metric_name] = metrics[metric_name]
                    row[f"{metric_name} 금액"] = metrics[f"{metric_name} 금액"]
        rows.append(row)

    return pd.DataFrame(rows)


def calculate_correlation(asset_returns: pd.DataFrame, position_summary: pd.DataFrame) -> pd.DataFrame:
    """현금을 제외한 위험자산 수익률 상관관계를 계산한다."""
    risky_tickers = [
        str(row["티커"])
        for _, row in position_summary.iterrows()
        if row["시장"] != "CASH" and str(row["티커"]) in asset_returns.columns
    ]
    if not risky_tickers:
        return pd.DataFrame()
    returns = asset_returns[risky_tickers].dropna(how="all")
    if returns.empty:
        return pd.DataFrame()
    if len(risky_tickers) == 1:
        return pd.DataFrame([[1.0]], index=risky_tickers, columns=risky_tickers)
    return returns.corr()


def calculate_stress_tests(position_summary: pd.DataFrame) -> tuple[pd.DataFrame, pd.DataFrame]:
    """전체 포트폴리오와 개별 자산 스트레스 테스트 결과를 계산한다."""
    total_value = float(position_summary["현재평가금액_원화"].sum())
    risky_positions = position_summary[position_summary["시장"] != "CASH"].copy()
    risky_value = float(risky_positions["현재평가금액_원화"].sum()) if not risky_positions.empty else 0.0

    portfolio_rows: list[dict[str, Any]] = []
    asset_rows: list[dict[str, Any]] = []
    for scenario, shock in STRESS_SCENARIOS.items():
        loss_amount = risky_value * max(-shock, 0.0)
        portfolio_rows.append(
            {
                "시나리오": scenario,
                "위험자산충격률": shock,
                "총포트폴리오가치": total_value,
                "예상손실금액": loss_amount,
                "예상손실률": loss_amount / total_value if total_value else 0.0,
                "스트레스후포트폴리오가치": total_value - loss_amount,
            }
        )

        for _, position in position_summary.iterrows():
            current_value = float(position["현재평가금액_원화"])
            asset_shock = 0.0 if position["시장"] == "CASH" else shock
            asset_loss = current_value * max(-asset_shock, 0.0)
            asset_rows.append(
                {
                    "자산명": position["자산명"],
                    "시장": position["시장"],
                    "티커": position["티커"],
                    "시나리오": scenario,
                    "현재평가금액": current_value,
                    "충격률": asset_shock,
                    "예상손실금액": asset_loss,
                    "스트레스후평가금액": current_value - asset_loss,
                }
            )

    return pd.DataFrame(portfolio_rows), pd.DataFrame(asset_rows)


def save_outputs(
    risk_summary: pd.DataFrame,
    asset_risk_summary: pd.DataFrame,
    stress_test: pd.DataFrame,
    asset_stress_test: pd.DataFrame,
    correlation: pd.DataFrame,
    drawdown: pd.DataFrame,
    monte_carlo_returns: pd.DataFrame,
) -> None:
    """리스크 산출물을 UTF-8-SIG CSV로 저장한다."""
    ensure_directories()
    risk_summary.to_csv(RISK_SUMMARY_FILE, index=False, encoding="utf-8-sig")
    asset_risk_summary.to_csv(ASSET_RISK_SUMMARY_FILE, index=False, encoding="utf-8-sig")
    stress_test.to_csv(STRESS_TEST_FILE, index=False, encoding="utf-8-sig")
    asset_stress_test.to_csv(ASSET_STRESS_TEST_FILE, index=False, encoding="utf-8-sig")
    correlation.to_csv(CORRELATION_FILE, encoding="utf-8-sig")
    drawdown.to_csv(DRAWDOWN_FILE, encoding="utf-8-sig", date_format="%Y-%m-%d")
    monte_carlo_returns.to_csv(MONTE_CARLO_FILE, encoding="utf-8-sig")


def main() -> None:
    """전체 포트폴리오와 개별 자산 리스크 산출물을 생성한다."""
    configure_logging()
    ensure_directories()
    portfolio_returns, portfolio_values, asset_returns, asset_values, position_summary = load_inputs()
    rng = np.random.default_rng(RANDOM_SEED)

    current_portfolio_value = float(portfolio_returns["포트폴리오_가치"].iloc[-1])
    portfolio_simulations = generate_portfolio_monte_carlo(
        portfolio_returns["포트폴리오_수익률"],
        asset_returns,
        position_summary,
        rng,
    )
    portfolio_metrics = calculate_tail_metrics(
        portfolio_returns["포트폴리오_수익률"],
        current_portfolio_value,
        rng,
        simulations=portfolio_simulations,
    )

    drawdown_series, portfolio_mdd = calculate_drawdown_from_values(portfolio_values["TOTAL_VALUE_KRW"])
    drawdown_frame = pd.DataFrame(
        {
            "포트폴리오_가치": portfolio_values["TOTAL_VALUE_KRW"],
            "Running_Max": portfolio_values["TOTAL_VALUE_KRW"].cummax(),
            "Drawdown": drawdown_series,
        }
    )
    drawdown_frame.index.name = "날짜"
    cumulative_return = float(portfolio_returns["누적수익률"].iloc[-1])

    risk_summary = build_risk_summary(
        portfolio_metrics,
        current_portfolio_value,
        portfolio_mdd,
        cumulative_return,
    )
    asset_risk_summary = build_asset_risk_summary(asset_returns, asset_values, position_summary, rng)
    correlation = calculate_correlation(asset_returns, position_summary)
    stress_test, asset_stress_test = calculate_stress_tests(position_summary)
    monte_carlo_frame = pd.DataFrame({"시뮬레이션_수익률": portfolio_simulations})
    monte_carlo_frame.index = monte_carlo_frame.index + 1
    monte_carlo_frame.index.name = "시나리오번호"

    save_outputs(
        risk_summary,
        asset_risk_summary,
        stress_test,
        asset_stress_test,
        correlation,
        drawdown_frame,
        monte_carlo_frame,
    )

    print("\n" + "=" * 70)
    print("4~9단계 완료: 다자산 포트폴리오 리스크 지표 계산")
    print("=" * 70)
    print(f"현재 총 포트폴리오 가치: {current_portfolio_value:,.0f}원")
    print(f"연환산 변동성: {portfolio_metrics['연환산 변동성']:.2%}")
    print(f"MDD: {portfolio_mdd:.2%}")
    print(f"95% Historical VaR: {portfolio_metrics['95% Historical VaR']:.2%}")
    print(f"저장 파일: {RISK_SUMMARY_FILE}")
    print(f"저장 파일: {ASSET_RISK_SUMMARY_FILE}")
    print(f"저장 파일: {CORRELATION_FILE}")
    print(f"저장 파일: {STRESS_TEST_FILE}")
    print(f"저장 파일: {ASSET_STRESS_TEST_FILE}")


if __name__ == "__main__":
    main()
