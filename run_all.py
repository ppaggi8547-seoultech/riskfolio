"""다자산 포트폴리오 VaR 프로젝트의 전체 단계를 순서대로 실행한다."""

from __future__ import annotations

# cd "C:\Users\ppagg\Desktop\Python\VarProject.py"
# python portfolio_input.py
# python run_all.py
# python -m streamlit run app.py

import importlib
import logging
from collections.abc import Callable
from pathlib import Path

Path("data/raw").mkdir(parents=True, exist_ok=True)
Path("data/processed").mkdir(parents=True, exist_ok=True)
Path("outputs").mkdir(parents=True, exist_ok=True)

from config import (
    ASSET_RETURN_FILE,
    ASSET_RISK_SUMMARY_FILE,
    ASSET_STRESS_TEST_FILE,
    ASSET_VALUE_FILE,
    CHART_DIR,
    CORRELATION_FILE,
    DRAWDOWN_FILE,
    MONTE_CARLO_FILE,
    PORTFOLIO_CONFIG_FILE,
    PORTFOLIO_RETURNS_FILE,
    PORTFOLIO_VALUE_FILE,
    POSITION_SUMMARY_FILE,
    REPORT_FILE,
    RISK_SUMMARY_FILE,
    STRESS_TEST_FILE,
    VAR_BACKTEST_CHART_FILE,
    VAR_BACKTEST_FILE,
    VAR_BACKTEST_SUMMARY_FILE,
)
from portfolio_input import run_input_wizard


def configure_logging() -> None:
    """전체 실행의 단계별 진행 상태를 콘솔에 표시하도록 설정한다."""
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s | %(levelname)s | %(message)s",
        datefmt="%H:%M:%S",
    )


def ensure_portfolio_config(interactive: bool) -> None:
    """포트폴리오 입력 파일이 없을 때 실행 모드에 맞게 처리한다."""
    if PORTFOLIO_CONFIG_FILE.exists():
        return

    if interactive:
        print("portfolio_config.json이 없습니다. 포트폴리오 입력을 시작합니다.")
        run_input_wizard()
        return

    raise RuntimeError(
        "포트폴리오 입력값이 없습니다. Portfolio Input 탭에서 포트폴리오를 입력하고 저장한 뒤 분석을 실행하세요."
    )


def clean_previous_processed_outputs() -> None:
    """입력 변경 시 이전 처리 산출물이 섞이지 않도록 주요 CSV/PNG/TXT 산출물을 제거한다."""
    output_files: list[Path] = [
        ASSET_VALUE_FILE,
        ASSET_RETURN_FILE,
        PORTFOLIO_VALUE_FILE,
        PORTFOLIO_RETURNS_FILE,
        POSITION_SUMMARY_FILE,
        RISK_SUMMARY_FILE,
        ASSET_RISK_SUMMARY_FILE,
        CORRELATION_FILE,
        STRESS_TEST_FILE,
        ASSET_STRESS_TEST_FILE,
        MONTE_CARLO_FILE,
        DRAWDOWN_FILE,
        VAR_BACKTEST_FILE,
        VAR_BACKTEST_SUMMARY_FILE,
        VAR_BACKTEST_CHART_FILE,
        REPORT_FILE,
        CHART_DIR / "portfolio_value.png",
        CHART_DIR / "cumulative_return.png",
        CHART_DIR / "return_distribution.png",
        CHART_DIR / "drawdown.png",
        CHART_DIR / "asset_weights.png",
        CHART_DIR / "correlation_heatmap.png",
    ]
    for file_path in output_files:
        if file_path.exists() and file_path.is_file():
            file_path.unlink()


def run_step(step_name: str, module_name: str) -> None:
    """모듈을 지연 import한 뒤 main()을 실행하고, 실패 단계를 명확히 알린다."""
    print("\n" + "=" * 70)
    print(f"시작: {step_name}")
    print("=" * 70)
    try:
        module = importlib.import_module(module_name)
        main_function: Callable[[], None] = getattr(module, "main")
        main_function()
    except SystemExit as exc:
        print(f"실패: {step_name} | {exc}")
        raise
    except Exception as exc:
        print(f"실패: {step_name} | {type(exc).__name__}: {exc}")
        raise
    else:
        print(f"완료: {step_name}")


def main(interactive: bool = True) -> None:
    """데이터 수집부터 백테스팅, 리포트까지 의존 순서에 맞춰 실행한다."""
    configure_logging()
    ensure_portfolio_config(interactive)
    clean_previous_processed_outputs()

    steps = [
        ("1단계 - 입력 종목 가격·환율 데이터 수집", "step1_data_collection"),
        ("2~3단계 - 원화 평가금액 및 포트폴리오 수익률 계산", "step2_return_calculation"),
        ("4~9단계 - 전체·개별 자산 리스크 지표 계산", "step3_risk_metrics"),
        ("5단계 확장 - Rolling VaR 백테스팅", "step5_var_backtesting"),
        ("10단계 - 시각화 및 리포트", "step4_visualization_report"),
    ]

    for step_name, module_name in steps:
        run_step(step_name, module_name)

    print("\n프로젝트 전체 실행이 완료되었습니다.")


if __name__ == "__main__":
    main()
