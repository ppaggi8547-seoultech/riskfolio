"""2~3단계: 다자산 포트폴리오의 원화 평가금액과 수익률을 계산한다."""

from __future__ import annotations

import logging
from datetime import date, timedelta
from pathlib import Path
from typing import Any

import pandas as pd

from config import (
    ASSET_MASTER_FILE,
    ASSET_RETURN_FILE,
    ASSET_VALUE_FILE,
    KR_PRICE_FILE,
    LOOKBACK_CALENDAR_DAYS,
    PORTFOLIO_RETURNS_FILE,
    PORTFOLIO_VALUE_FILE,
    POSITION_SUMMARY_FILE,
    US_PRICE_FILE,
    USD_KRW_FILE,
    ensure_directories,
)
from portfolio_input import load_portfolio_config


def configure_logging() -> None:
    """단계 실행 상태를 콘솔에 표시하도록 logging을 설정한다."""
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s | %(levelname)s | %(message)s",
        datefmt="%H:%M:%S",
    )


def read_indexed_csv(file_path: Path) -> pd.DataFrame | None:
    """날짜 인덱스 CSV를 읽는다. 파일이 없으면 None을 반환한다."""
    if not file_path.exists():
        return None
    frame = pd.read_csv(file_path, encoding="utf-8-sig", index_col="날짜", parse_dates=["날짜"])
    frame.index = pd.to_datetime(frame.index)
    frame = frame[~frame.index.duplicated(keep="last")].sort_index()
    for column in frame.columns:
        frame[column] = pd.to_numeric(frame[column], errors="coerce")
    frame.index.name = "날짜"
    return frame


def read_asset_master() -> pd.DataFrame:
    """step1에서 생성한 자산 회사명/표시명 매핑표를 읽는다.

    파일이 없거나 깨져 있으면 빈 DataFrame을 반환해 기존 티커 fallback 흐름을 유지한다.
    """
    if not ASSET_MASTER_FILE.exists():
        return pd.DataFrame(columns=["시장", "티커", "회사명", "표시명"])
    try:
        asset_master = pd.read_csv(ASSET_MASTER_FILE, encoding="utf-8-sig", dtype=str)
    except Exception as exc:
        logging.warning("asset_master.csv 로딩 실패, 티커 fallback을 사용합니다: %s", exc)
        return pd.DataFrame(columns=["시장", "티커", "회사명", "표시명"])

    for column in ("시장", "티커", "회사명", "표시명"):
        if column not in asset_master.columns:
            asset_master[column] = ""
        asset_master[column] = asset_master[column].fillna("").astype(str).str.strip()
    return asset_master[["시장", "티커", "회사명", "표시명"]]


def get_asset_identity(asset_master: pd.DataFrame, market: str, ticker: str) -> dict[str, str]:
    """시장과 티커에 해당하는 자산명/회사명/표시명을 반환한다."""
    market = str(market).strip()
    ticker = str(ticker).strip()

    if market == "CASH" or ticker == "CASH":
        return {"자산명": "현금", "회사명": "현금", "표시명": "현금"}

    if asset_master is not None and not asset_master.empty:
        matched = asset_master[
            (asset_master["시장"].astype(str) == market)
            & (asset_master["티커"].astype(str) == ticker)
        ]
        if matched.empty:
            matched = asset_master[asset_master["티커"].astype(str) == ticker]
        if not matched.empty:
            row = matched.iloc[0]
            company_name = str(row.get("회사명") or ticker).strip() or ticker
            display_name = str(row.get("표시명") or company_name).strip() or company_name
            return {
                "자산명": company_name,
                "회사명": company_name,
                "표시명": display_name,
            }

    return {"자산명": ticker, "회사명": ticker, "표시명": ticker}


def fallback_cash_only_index() -> pd.DatetimeIndex:
    """현금만 있는 포트폴리오용 영업일 인덱스를 만든다."""
    end_date = date.today()
    start_date = end_date - timedelta(days=LOOKBACK_CALENDAR_DAYS)
    return pd.bdate_range(start=start_date, end=end_date, name="날짜")


def build_union_index(frames: list[pd.DataFrame | None], cash_only: bool) -> pd.DatetimeIndex:
    """모든 가격·환율 데이터의 날짜를 outer join 기준으로 합친다."""
    indexes = [frame.index for frame in frames if frame is not None and not frame.empty]
    if not indexes:
        if cash_only:
            return fallback_cash_only_index()
        raise ValueError("가격 데이터가 없습니다. 먼저 step1_data_collection.py를 실행하세요.")

    union_index = indexes[0]
    for index in indexes[1:]:
        union_index = union_index.union(index)
    union_index = pd.DatetimeIndex(union_index).sort_values()
    union_index.name = "날짜"
    return union_index


def align_frame(frame: pd.DataFrame | None, index: pd.DatetimeIndex) -> pd.DataFrame | None:
    """가격 또는 환율 DataFrame을 전체 날짜 인덱스에 맞추고 forward-fill한다."""
    if frame is None or frame.empty:
        return None
    aligned = frame.reindex(index).sort_index().ffill()
    aligned.index.name = "날짜"
    return aligned


def is_available_number(value: Any) -> bool:
    """None/NaN이 아닌 숫자 여부를 확인한다."""
    return value is not None and not pd.isna(value)


def group_positions_by_market_ticker(
    positions: list[dict[str, Any]],
    market: str,
) -> dict[str, list[dict[str, Any]]]:
    """동일 시장·티커의 포지션을 lot 목록으로 묶는다."""
    grouped: dict[str, list[dict[str, Any]]] = {}
    normalized_market = str(market).strip().upper()
    for position in positions:
        ticker = str(position.get("ticker", "")).strip()
        if normalized_market == "US":
            ticker = ticker.upper()
        elif normalized_market == "KR" and ticker.isdigit():
            ticker = ticker.zfill(6)
        if not ticker:
            continue
        normalized_position = dict(position)
        normalized_position["ticker"] = ticker
        grouped.setdefault(ticker, []).append(normalized_position)
    return grouped


def get_fx_rate_on_or_before(usdkrw: pd.DataFrame | None, purchase_date: str | None) -> float:
    """매수일자 또는 그 이전의 가장 가까운 USD/KRW 환율을 반환한다.

    매수일자가 환율 데이터 시작일보다 앞서면 이후 첫 유효 환율을 fallback으로 사용한다.
    그래도 찾을 수 없으면 NaN을 반환한다.
    """
    if usdkrw is None or usdkrw.empty or "USD_KRW" not in usdkrw.columns or not purchase_date:
        return float("nan")

    series = pd.to_numeric(usdkrw["USD_KRW"], errors="coerce").dropna()
    if series.empty:
        return float("nan")

    target_date = pd.to_datetime(purchase_date, errors="coerce")
    if pd.isna(target_date):
        return float("nan")

    before_or_same = series.loc[series.index <= target_date]
    if not before_or_same.empty:
        return float(before_or_same.iloc[-1])

    after_or_same = series.loc[series.index >= target_date]
    if not after_or_same.empty:
        return float(after_or_same.iloc[0])

    return float("nan")


def calculate_asset_values(
    config: dict[str, Any],
    kr_prices: pd.DataFrame | None,
    us_prices: pd.DataFrame | None,
    usdkrw: pd.DataFrame | None,
    asset_master: pd.DataFrame | None = None,
) -> tuple[pd.DataFrame, pd.DataFrame]:
    """개별 자산 원화 평가금액과 position_summary를 계산한다."""
    korean_stocks = config["korean_stocks"]
    us_stocks = config["us_stocks"]
    cash_krw = float(config["cash_krw"])
    cash_only = not korean_stocks and not us_stocks

    union_index = build_union_index([kr_prices, us_prices, usdkrw], cash_only=cash_only)
    kr_aligned = align_frame(kr_prices, union_index)
    us_aligned = align_frame(us_prices, union_index)
    fx_aligned = align_frame(usdkrw, union_index)

    values = pd.DataFrame(index=union_index)
    position_rows: list[dict[str, Any]] = []
    asset_master = asset_master if asset_master is not None else pd.DataFrame()

    korean_groups = group_positions_by_market_ticker(korean_stocks, "KR")
    for ticker, lots in korean_groups.items():
        total_quantity = sum(float(lot["quantity"]) for lot in lots)
        if kr_aligned is None or ticker not in kr_aligned.columns:
            logging.warning("한국주식 %s 가격 데이터가 없어 계산에서 제외합니다.", ticker)
            continue
        values[ticker] = kr_aligned[ticker] * total_quantity
        latest_price = float(kr_aligned[ticker].dropna().iloc[-1])
        latest_value = latest_price * total_quantity
        has_complete_purchase_prices = all(is_available_number(lot.get("purchase_price")) for lot in lots)
        if has_complete_purchase_prices:
            purchase_amount = sum(
                float(lot["purchase_price"]) * float(lot["quantity"])
                for lot in lots
            )
            purchase_price = purchase_amount / total_quantity if total_quantity else float("nan")
        else:
            purchase_amount = float("nan")
            purchase_price = float("nan")
        total_profit = latest_value - purchase_amount if is_available_number(purchase_amount) else float("nan")
        profit_rate = total_profit / purchase_amount if is_available_number(purchase_amount) and purchase_amount else float("nan")
        identity = get_asset_identity(asset_master, "KR", ticker)
        position_rows.append(
            {
                "자산명": identity["자산명"],
                "시장": "KR",
                "티커": ticker,
                "회사명": identity["회사명"],
                "표시명": identity["표시명"],
                "수량": total_quantity,
                "매수일자": "-",
                "매수가격": purchase_price,
                "매수가격_통화": "KRW",
                "매수환율_USD_KRW": float("nan"),
                "매수금액_원화": purchase_amount,
                "현재가격": latest_price,
                "현재가격_통화": "KRW",
                "현재가격_원화": latest_price,
                "최신환율_USD_KRW": float("nan"),
                "현재평가금액_원화": latest_value,
                "총수익_원화": total_profit,
                "수익률": profit_rate,
            }
        )

    us_groups = group_positions_by_market_ticker(us_stocks, "US")
    for ticker, lots in us_groups.items():
        total_quantity = sum(float(lot["quantity"]) for lot in lots)
        if us_aligned is None or ticker not in us_aligned.columns:
            logging.warning("미국주식 %s 가격 데이터가 없어 계산에서 제외합니다.", ticker)
            continue
        if fx_aligned is None or "USD_KRW" not in fx_aligned.columns:
            raise ValueError("미국주식 계산에는 USD/KRW 환율 데이터가 필요합니다.")
        krw_price = us_aligned[ticker] * fx_aligned["USD_KRW"]
        values[ticker] = krw_price * total_quantity
        latest_usd_price = float(us_aligned[ticker].dropna().iloc[-1])
        latest_fx_rate = float(pd.to_numeric(fx_aligned["USD_KRW"], errors="coerce").dropna().iloc[-1])
        latest_krw_price = latest_usd_price * latest_fx_rate
        latest_value = latest_krw_price * total_quantity

        purchase_dates = [
            str(lot.get("purchase_date")).strip()
            for lot in lots
            if lot.get("purchase_date")
        ]
        unique_purchase_dates = list(dict.fromkeys(purchase_dates))
        if not unique_purchase_dates:
            purchase_date = "-"
        elif len(unique_purchase_dates) == 1:
            purchase_date = unique_purchase_dates[0]
        else:
            purchase_date = "복수"

        has_complete_purchase_prices = all(is_available_number(lot.get("purchase_price")) for lot in lots)
        if has_complete_purchase_prices:
            purchase_price = sum(
                float(lot["purchase_price"]) * float(lot["quantity"])
                for lot in lots
            ) / total_quantity
        else:
            purchase_price = float("nan")

        lot_fx_rates = [
            get_fx_rate_on_or_before(fx_aligned, lot.get("purchase_date"))
            for lot in lots
        ]
        has_complete_purchase_data = has_complete_purchase_prices and all(
            lot.get("purchase_date") and is_available_number(fx_rate)
            for lot, fx_rate in zip(lots, lot_fx_rates)
        )
        if has_complete_purchase_data:
            purchase_amount = sum(
                float(lot["purchase_price"])
                * float(lot["quantity"])
                * float(fx_rate)
                for lot, fx_rate in zip(lots, lot_fx_rates)
            )
            purchase_fx_rate = sum(
                float(fx_rate) * float(lot["quantity"])
                for lot, fx_rate in zip(lots, lot_fx_rates)
            ) / total_quantity
            total_profit = latest_value - purchase_amount
            profit_rate = latest_value / purchase_amount - 1 if purchase_amount else float("nan")
        else:
            purchase_amount = float("nan")
            purchase_fx_rate = float("nan")
            total_profit = float("nan")
            profit_rate = float("nan")
        identity = get_asset_identity(asset_master, "US", ticker)
        position_rows.append(
            {
                "자산명": identity["자산명"],
                "시장": "US",
                "티커": ticker,
                "회사명": identity["회사명"],
                "표시명": identity["표시명"],
                "수량": total_quantity,
                "매수일자": purchase_date,
                "매수가격": purchase_price,
                "매수가격_통화": "USD",
                "매수환율_USD_KRW": purchase_fx_rate,
                "매수금액_원화": purchase_amount,
                "현재가격": latest_usd_price,
                "현재가격_통화": "USD",
                "현재가격_원화": latest_krw_price,
                "최신환율_USD_KRW": latest_fx_rate,
                "현재평가금액_원화": latest_value,
                "총수익_원화": total_profit,
                "수익률": profit_rate,
            }
        )

    values["CASH"] = cash_krw
    risky_columns = [column for column in values.columns if column != "CASH"]
    if risky_columns:
        values = values.dropna(subset=risky_columns)
    if values.empty:
        raise ValueError("모든 자산의 평가금액을 계산할 수 없습니다. 가격 데이터와 입력 수량을 확인하세요.")

    values["TOTAL_VALUE_KRW"] = values.sum(axis=1)
    if (values["TOTAL_VALUE_KRW"] <= 0).all():
        raise ValueError("총 포트폴리오 가치가 0입니다. 종목 또는 현금을 입력하세요.")

    latest_total_value = float(values["TOTAL_VALUE_KRW"].iloc[-1])
    if cash_krw > 0 or not position_rows:
        identity = get_asset_identity(asset_master, "CASH", "CASH")
        position_rows.append(
            {
                "자산명": identity["자산명"],
                "시장": "CASH",
                "티커": "CASH",
                "회사명": identity["회사명"],
                "표시명": identity["표시명"],
                "수량": 1.0,
                "매수일자": None,
                "매수가격": float("nan"),
                "매수가격_통화": "KRW",
                "매수환율_USD_KRW": float("nan"),
                "매수금액_원화": cash_krw,
                "현재가격": cash_krw,
                "현재가격_통화": "KRW",
                "현재가격_원화": cash_krw,
                "최신환율_USD_KRW": float("nan"),
                "현재평가금액_원화": cash_krw,
                "총수익_원화": 0.0,
                "수익률": 0.0,
            }
        )

    position_summary = pd.DataFrame(position_rows)
    if position_summary.empty:
        raise ValueError("포지션 요약을 생성할 수 없습니다.")
    position_summary["포트폴리오비중"] = (
        position_summary["현재평가금액_원화"] / latest_total_value if latest_total_value else 0.0
    )
    column_order = [
        "자산명",
        "시장",
        "티커",
        "회사명",
        "표시명",
        "수량",
        "매수일자",
        "매수가격",
        "매수가격_통화",
        "매수환율_USD_KRW",
        "매수금액_원화",
        "현재가격",
        "현재가격_통화",
        "현재가격_원화",
        "최신환율_USD_KRW",
        "현재평가금액_원화",
        "총수익_원화",
        "수익률",
        "포트폴리오비중",
    ]
    position_summary = position_summary[[column for column in column_order if column in position_summary.columns]]
    return values, position_summary


def calculate_returns(values: pd.DataFrame) -> tuple[pd.DataFrame, pd.DataFrame, pd.DataFrame]:
    """자산별 수익률, 포트폴리오 가치, 포트폴리오 수익률 표를 계산한다."""
    asset_columns = [column for column in values.columns if column != "TOTAL_VALUE_KRW"]
    asset_returns = values[asset_columns].pct_change()
    if "CASH" in asset_returns.columns:
        asset_returns["CASH"] = 0.0
    asset_returns = asset_returns.fillna(0.0)
    asset_returns.index.name = "날짜"

    portfolio_values = values.copy()
    if "CASH" in portfolio_values.columns:
        portfolio_values = portfolio_values.rename(columns={"CASH": "CASH_KRW"})
    portfolio_values.index.name = "날짜"

    portfolio_returns = pd.DataFrame(index=values.index)
    portfolio_returns.index.name = "날짜"
    portfolio_returns["포트폴리오_가치"] = values["TOTAL_VALUE_KRW"]
    portfolio_returns["포트폴리오_수익률"] = values["TOTAL_VALUE_KRW"].pct_change().fillna(0.0)
    portfolio_returns["누적수익률"] = values["TOTAL_VALUE_KRW"] / values["TOTAL_VALUE_KRW"].iloc[0] - 1
    portfolio_returns["포트폴리오_손익"] = values["TOTAL_VALUE_KRW"].diff().fillna(0.0)

    return asset_returns, portfolio_values, portfolio_returns


def save_outputs(
    asset_values: pd.DataFrame,
    asset_returns: pd.DataFrame,
    portfolio_values: pd.DataFrame,
    portfolio_returns: pd.DataFrame,
    position_summary: pd.DataFrame,
) -> None:
    """2~3단계 산출물을 저장한다."""
    ensure_directories()
    asset_values.to_csv(ASSET_VALUE_FILE, encoding="utf-8-sig", date_format="%Y-%m-%d")
    asset_returns.to_csv(ASSET_RETURN_FILE, encoding="utf-8-sig", date_format="%Y-%m-%d")
    portfolio_values.to_csv(PORTFOLIO_VALUE_FILE, encoding="utf-8-sig", date_format="%Y-%m-%d")
    portfolio_returns.to_csv(PORTFOLIO_RETURNS_FILE, encoding="utf-8-sig", date_format="%Y-%m-%d")
    position_summary.to_csv(POSITION_SUMMARY_FILE, index=False, encoding="utf-8-sig")


def main() -> None:
    """입력 포트폴리오의 원화 평가금액과 수익률 산출물을 생성한다."""
    configure_logging()
    ensure_directories()
    config = load_portfolio_config()
    kr_prices = read_indexed_csv(KR_PRICE_FILE)
    us_prices = read_indexed_csv(US_PRICE_FILE)
    usdkrw = read_indexed_csv(USD_KRW_FILE)
    asset_master = read_asset_master()

    asset_values, position_summary = calculate_asset_values(config, kr_prices, us_prices, usdkrw, asset_master)
    asset_returns, portfolio_values, portfolio_returns = calculate_returns(asset_values)
    save_outputs(asset_values, asset_returns, portfolio_values, portfolio_returns, position_summary)

    print("\n" + "=" * 70)
    print("2~3단계 완료: 다자산 포트폴리오 원화 가치와 수익률 계산")
    print("=" * 70)
    print(f"평가 시작일: {asset_values.index.min():%Y-%m-%d}")
    print(f"평가 종료일: {asset_values.index.max():%Y-%m-%d}")
    print(f"유효 관측일수: {len(asset_values):,}일")
    print(f"현재 총 포트폴리오 가치: {asset_values['TOTAL_VALUE_KRW'].iloc[-1]:,.0f}원")
    print(f"저장 파일: {ASSET_VALUE_FILE}")
    print(f"저장 파일: {ASSET_RETURN_FILE}")
    print(f"저장 파일: {PORTFOLIO_VALUE_FILE}")
    print(f"저장 파일: {PORTFOLIO_RETURNS_FILE}")
    print(f"저장 파일: {POSITION_SUMMARY_FILE}")


if __name__ == "__main__":
    main()
