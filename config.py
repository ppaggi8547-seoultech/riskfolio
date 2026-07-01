"""다자산 포트폴리오 VaR 프로젝트의 공통 설정과 경로 정의."""

from __future__ import annotations

from pathlib import Path
from typing import Final

# 이전 단일 종목 버전과의 호환 및 예시용 기본값
ASSET_NAME: Final[str] = "SK하이닉스"
ASSET_TICKER: Final[str] = "000660"
INITIAL_CAPITAL: Final[int] = 10_000_000

# 분석/모형 설정
LOOKBACK_CALENDAR_DAYS: Final[int] = 365 * 3
TRADING_DAYS_PER_YEAR: Final[int] = 252
CONFIDENCE_LEVELS: Final[list[float]] = [0.95, 0.99]
MONTE_CARLO_SIMULATIONS: Final[int] = 100_000
RANDOM_SEED: Final[int] = 42
BACKTEST_WINDOW: Final[int] = 252
BACKTEST_CONFIDENCE_LEVELS: Final[list[float]] = [0.95, 0.99]
STRESS_SCENARIOS: Final[dict[str, float]] = {
    "하락 -5%": -0.05,
    "하락 -10%": -0.10,
    "하락 -20%": -0.20,
    "하락 -30%": -0.30,
}

# 프로젝트 경로
PROJECT_DIR: Final[Path] = Path(__file__).resolve().parent
INPUT_DATA_DIR: Final[Path] = PROJECT_DIR / "data" / "input"
RAW_DATA_DIR: Final[Path] = PROJECT_DIR / "data" / "raw"
RAW_PRICE_DIR: Final[Path] = RAW_DATA_DIR / "prices"
RAW_FX_DIR: Final[Path] = RAW_DATA_DIR / "fx"
PROCESSED_DATA_DIR: Final[Path] = PROJECT_DIR / "data" / "processed"
OUTPUT_DIR: Final[Path] = PROJECT_DIR / "outputs"
CHART_DIR: Final[Path] = OUTPUT_DIR / "charts"
CHARTS_DIR: Final[Path] = CHART_DIR  # 일부 기존 코드 호환용 별칭
TABLE_DIR: Final[Path] = OUTPUT_DIR / "tables"

# 입력 파일
PORTFOLIO_CONFIG_FILE: Final[Path] = INPUT_DATA_DIR / "portfolio_config.json"

# 원천 데이터 파일
KR_PRICE_FILE: Final[Path] = RAW_DATA_DIR / "kr_prices.csv"
US_PRICE_FILE: Final[Path] = RAW_DATA_DIR / "us_prices.csv"
USD_KRW_FILE: Final[Path] = RAW_FX_DIR / "usdkrw.csv"
METADATA_FILE: Final[Path] = RAW_DATA_DIR / "collection_metadata.json"

# 이전 단일 종목 버전 호환용 경로
PRICE_FILE: Final[Path] = KR_PRICE_FILE

# 처리 데이터 파일
ASSET_VALUE_FILE: Final[Path] = PROCESSED_DATA_DIR / "asset_values_krw.csv"
ASSET_RETURN_FILE: Final[Path] = PROCESSED_DATA_DIR / "asset_returns_krw.csv"
PORTFOLIO_VALUE_FILE: Final[Path] = PROCESSED_DATA_DIR / "portfolio_values.csv"
PORTFOLIO_RETURNS_FILE: Final[Path] = PROCESSED_DATA_DIR / "portfolio_returns.csv"
POSITION_SUMMARY_FILE: Final[Path] = PROCESSED_DATA_DIR / "position_summary.csv"
ASSET_MASTER_FILE: Final[Path] = PROCESSED_DATA_DIR / "asset_master.csv"
CORRELATION_FILE: Final[Path] = PROCESSED_DATA_DIR / "correlation_matrix.csv"
RETURNS_FILE: Final[Path] = ASSET_RETURN_FILE  # 기존 코드 호환용 별칭

# 리스크 산출물
RISK_SUMMARY_FILE: Final[Path] = PROCESSED_DATA_DIR / "risk_summary.csv"
ASSET_RISK_SUMMARY_FILE: Final[Path] = PROCESSED_DATA_DIR / "asset_risk_summary.csv"
STRESS_TEST_FILE: Final[Path] = PROCESSED_DATA_DIR / "stress_test.csv"
ASSET_STRESS_TEST_FILE: Final[Path] = PROCESSED_DATA_DIR / "asset_stress_test.csv"
MONTE_CARLO_FILE: Final[Path] = PROCESSED_DATA_DIR / "monte_carlo_returns.csv"
DRAWDOWN_FILE: Final[Path] = PROCESSED_DATA_DIR / "drawdown.csv"

# 백테스팅 및 리포트 산출물
VAR_BACKTEST_FILE: Final[Path] = PROCESSED_DATA_DIR / "var_backtest.csv"
VAR_BACKTEST_SUMMARY_FILE: Final[Path] = PROCESSED_DATA_DIR / "var_backtest_summary.csv"
VAR_BACKTEST_CHART_FILE: Final[Path] = CHART_DIR / "var_backtest_breaches.png"
REPORT_FILE: Final[Path] = OUTPUT_DIR / "report_summary.txt"


def ensure_directories() -> None:
    """프로젝트 실행에 필요한 데이터/결과 폴더를 안전하게 만든다."""
    for directory in (
        INPUT_DATA_DIR,
        RAW_DATA_DIR,
        RAW_PRICE_DIR,
        RAW_FX_DIR,
        PROCESSED_DATA_DIR,
        OUTPUT_DIR,
        CHART_DIR,
        TABLE_DIR,
    ):
        directory.mkdir(parents=True, exist_ok=True)
