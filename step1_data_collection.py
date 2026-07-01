"""1단계: 입력 포트폴리오에 포함된 한국/미국 주식과 USD/KRW 환율만 수집한다."""

from __future__ import annotations

import json
import logging
from datetime import date, timedelta
from pathlib import Path
from typing import Any, cast

import pandas as pd

from config import (
    ASSET_MASTER_FILE,
    KR_PRICE_FILE,
    LOOKBACK_CALENDAR_DAYS,
    METADATA_FILE,
    RAW_PRICE_DIR,
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


def get_collection_period() -> tuple[date, date]:
    """최근 LOOKBACK_CALENDAR_DAYS 기준 수집 시작일과 종료일을 반환한다."""
    end_date = date.today()
    start_date = end_date - timedelta(days=LOOKBACK_CALENDAR_DAYS)
    return start_date, end_date


def clean_previous_raw_outputs() -> None:
    """이번 입력에 해당하지 않는 이전 raw 산출물이 앱에 섞이지 않도록 제거한다."""
    for path in (KR_PRICE_FILE, US_PRICE_FILE, USD_KRW_FILE):
        if path.exists():
            path.unlink()


def read_close_from_fdr(ticker: str, start_date: date, end_date: date) -> pd.Series:
    """FinanceDataReader로 한국주식 종가를 읽는다."""
    try:
        import FinanceDataReader as fdr
    except ImportError as exc:
        raise ImportError(
            "한국주식 데이터 수집에는 FinanceDataReader가 필요합니다. "
            "`python -m pip install finance-datareader`를 실행하세요."
        ) from exc

    frame = fdr.DataReader(ticker, start_date.isoformat(), end_date.isoformat())
    if frame.empty or "Close" not in frame.columns:
        raise ValueError("Close 가격 데이터가 비어 있습니다.")
    close = pd.to_numeric(frame["Close"], errors="coerce").dropna()
    close.index = pd.to_datetime(close.index)
    close.name = ticker
    return close


def extract_yfinance_price(frame: pd.DataFrame, ticker: str) -> pd.Series:
    """yfinance 다운로드 결과에서 Adj Close 또는 Close 가격 Series를 안전하게 추출한다."""
    if frame.empty:
        raise ValueError("다운로드된 가격 데이터가 비어 있습니다.")

    if isinstance(frame.columns, pd.MultiIndex):
        for price_column in ("Adj Close", "Close"):
            if (price_column, ticker) in frame.columns:
                series = frame[(price_column, ticker)]
                break
            if price_column in frame.columns.get_level_values(0):
                subset = frame[price_column]
                if isinstance(subset, pd.DataFrame) and ticker in subset.columns:
                    series = subset[ticker]
                    break
        else:
            raise ValueError("Adj Close 또는 Close 컬럼을 찾을 수 없습니다.")
    else:
        if "Adj Close" in frame.columns:
            series = frame["Adj Close"]
        elif "Close" in frame.columns:
            series = frame["Close"]
        else:
            raise ValueError("Adj Close 또는 Close 컬럼을 찾을 수 없습니다.")

    price = pd.to_numeric(series, errors="coerce").dropna()
    price.index = pd.to_datetime(price.index)
    price.name = ticker
    return price


def read_close_from_yfinance(ticker: str, start_date: date, end_date: date) -> pd.Series:
    """yfinance로 미국주식 달러 가격을 읽는다."""
    try:
        import yfinance as yf
    except ImportError as exc:
        raise ImportError(
            "미국주식 데이터 수집에는 yfinance가 필요합니다. "
            "`python -m pip install yfinance`를 실행하세요."
        ) from exc

    # yfinance의 end는 대체로 exclusive라 하루를 더한다.
    raw_frame = yf.download(
    ticker,
    start=start_date.isoformat(),
    end=(end_date + timedelta(days=1)).isoformat(),
    auto_adjust=False,
    progress=False,
    threads=False,
    )
    frame = cast(pd.DataFrame, raw_frame)
    return extract_yfinance_price(frame, ticker)


def read_usdkrw_from_yfinance(start_date: date, end_date: date) -> pd.Series:
    """yfinance의 KRW=X로 USD/KRW 환율을 읽는다."""
    try:
        import yfinance as yf
    except ImportError as exc:
        raise ImportError(
            "USD/KRW 환율 데이터 수집에는 yfinance가 필요합니다. "
            "`python -m pip install yfinance`를 실행하세요."
        ) from exc

    raw_frame = yf.download(
    "KRW=X",
    start=start_date.isoformat(),
    end=(end_date + timedelta(days=1)).isoformat(),
    auto_adjust=False,
    progress=False,
    threads=False,
    )
    frame = cast(pd.DataFrame, raw_frame)
    usdkrw = extract_yfinance_price(frame, "KRW=X")
    usdkrw.name = "USD_KRW"
    return usdkrw


def normalize_kr_ticker(ticker: Any) -> str:
    """한국 주식 종목코드를 6자리 문자열로 정리한다."""
    text = str(ticker).strip()
    if text.endswith(".0"):
        text = text[:-2]
    return text.zfill(6) if text.isdigit() else text


def normalize_us_ticker(ticker: Any) -> str:
    """미국 주식 티커를 대문자 문자열로 정리한다."""
    return str(ticker).strip().upper()


def unique_positions_by_ticker(positions: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """입력 순서를 유지하면서 동일 티커의 데이터 수집 요청을 하나로 줄인다.

    이 함수는 가격·회사명 조회 대상만 중복 제거한다. 수량, 매수가격, 매수일자 같은
    lot 정보는 원본 portfolio_config에 그대로 남아 step2에서 합산 계산에 사용된다.
    """
    unique: dict[str, dict[str, Any]] = {}
    for position in positions:
        ticker = str(position.get("ticker", "")).strip()
        if not ticker:
            continue
        normalized_position = dict(position)
        normalized_position["ticker"] = ticker
        unique[ticker] = normalized_position
    return list(unique.values())


def get_korean_stock_names(tickers: list[str]) -> dict[str, str]:
    """FinanceDataReader KRX 목록에서 한국 주식 회사명을 조회한다.

    조회 실패 또는 목록 미포함 종목은 종목코드를 회사명으로 사용한다.
    """
    normalized_tickers = [normalize_kr_ticker(ticker) for ticker in tickers]
    names = {ticker: ticker for ticker in normalized_tickers}
    if not normalized_tickers:
        return names

    try:
        import FinanceDataReader as fdr

        listing = fdr.StockListing("KRX")
    except Exception as exc:
        logging.warning("KRX 종목명 조회 실패, 종목코드로 대체합니다: %s", exc)
        return names

    if listing is None or listing.empty or not {"Code", "Name"}.issubset(listing.columns):
        logging.warning("KRX 종목 목록에 Code/Name 컬럼이 없어 종목코드로 대체합니다.")
        return names

    listing = listing.copy()
    listing["Code"] = listing["Code"].map(normalize_kr_ticker)
    code_to_name = (
        listing.dropna(subset=["Code", "Name"])
        .drop_duplicates(subset=["Code"], keep="first")
        .set_index("Code")["Name"]
        .astype(str)
        .str.strip()
        .to_dict()
    )

    for ticker in normalized_tickers:
        name = code_to_name.get(ticker)
        if name:
            names[ticker] = name
    return names


def get_us_stock_name(ticker: str) -> str:
    """yfinance에서 미국 주식 회사명을 조회한다.

    longName, shortName, ticker 순서로 fallback한다.
    """
    ticker = normalize_us_ticker(ticker)
    if not ticker:
        return ticker

    try:
        import yfinance as yf

        ticker_object = yf.Ticker(ticker)
        try:
            info = ticker_object.get_info()
        except Exception:
            info = ticker_object.info
        if not isinstance(info, dict):
            return ticker
        for key in ("longName", "shortName"):
            value = info.get(key)
            if value and str(value).strip():
                return str(value).strip()
    except Exception as exc:
        logging.warning("미국주식 회사명 조회 실패, 티커로 대체합니다: %s | %s", ticker, exc)
    return ticker


def build_display_name(market: str, ticker: str, company_name: str) -> str:
    """시장/티커/회사명을 바탕으로 대시보드 표시명을 만든다."""
    if market == "CASH":
        return "현금"
    if not company_name or company_name == ticker:
        return ticker
    if market == "US" and ticker.upper() in {"GOOGL", "GOOG"} and "google" not in company_name.lower():
        return f"Google / {company_name} ({ticker})"
    return f"{company_name} ({ticker})"


def build_asset_master(config: dict[str, Any]) -> pd.DataFrame:
    """입력 포트폴리오의 자산별 회사명/표시명 매핑표를 생성한다."""
    korean_positions = unique_positions_by_ticker(config.get("korean_stocks", []))
    us_positions = unique_positions_by_ticker(config.get("us_stocks", []))
    korean_tickers = [normalize_kr_ticker(position["ticker"]) for position in korean_positions]
    us_tickers = [normalize_us_ticker(position["ticker"]) for position in us_positions]

    korean_names = get_korean_stock_names(korean_tickers)
    rows: list[dict[str, str]] = []

    for ticker in korean_tickers:
        company_name = korean_names.get(ticker, ticker)
        rows.append(
            {
                "시장": "KR",
                "티커": ticker,
                "회사명": company_name,
                "표시명": build_display_name("KR", ticker, company_name),
            }
        )

    for ticker in us_tickers:
        company_name = get_us_stock_name(ticker)
        rows.append(
            {
                "시장": "US",
                "티커": ticker,
                "회사명": company_name,
                "표시명": build_display_name("US", ticker, company_name),
            }
        )

    rows.append({"시장": "CASH", "티커": "CASH", "회사명": "현금", "표시명": "현금"})
    asset_master = pd.DataFrame(rows, columns=["시장", "티커", "회사명", "표시명"])
    return asset_master.drop_duplicates(subset=["시장", "티커"], keep="first")


def save_asset_master(asset_master: pd.DataFrame) -> None:
    """자산 회사명/표시명 매핑표를 UTF-8-SIG CSV로 저장한다."""
    ASSET_MASTER_FILE.parent.mkdir(parents=True, exist_ok=True)
    asset_master.to_csv(ASSET_MASTER_FILE, index=False, encoding="utf-8-sig")


def collect_korean_prices(
    korean_stocks: list[dict[str, Any]],
    start_date: date,
    end_date: date,
) -> tuple[pd.DataFrame | None, list[str], list[dict[str, str]]]:
    """입력된 한국주식만 수집하고 성공/실패 목록을 반환한다."""
    price_series: list[pd.Series] = []
    success: list[str] = []
    failures: list[dict[str, str]] = []

    for position in unique_positions_by_ticker(korean_stocks):
        ticker = normalize_kr_ticker(position["ticker"])
        try:
            series = read_close_from_fdr(ticker, start_date, end_date)
        except Exception as exc:
            failures.append({"market": "KR", "ticker": ticker, "error": str(exc)})
            logging.warning("한국주식 수집 실패: %s | %s", ticker, exc)
            continue
        price_series.append(series)
        success.append(ticker)

    if not price_series:
        return None, success, failures

    prices = pd.concat(price_series, axis=1).sort_index()
    prices.index.name = "날짜"
    return prices, success, failures


def collect_us_prices(
    us_stocks: list[dict[str, Any]],
    start_date: date,
    end_date: date,
) -> tuple[pd.DataFrame | None, list[str], list[dict[str, str]]]:
    """입력된 미국주식만 수집하고 성공/실패 목록을 반환한다."""
    price_series: list[pd.Series] = []
    success: list[str] = []
    failures: list[dict[str, str]] = []

    for position in unique_positions_by_ticker(us_stocks):
        ticker = normalize_us_ticker(position["ticker"])
        try:
            series = read_close_from_yfinance(ticker, start_date, end_date)
        except Exception as exc:
            failures.append({"market": "US", "ticker": ticker, "error": str(exc)})
            logging.warning("미국주식 수집 실패: %s | %s", ticker, exc)
            continue
        price_series.append(series)
        success.append(ticker)

    if not price_series:
        return None, success, failures

    prices = pd.concat(price_series, axis=1).sort_index()
    prices.index.name = "날짜"
    return prices, success, failures


def save_price_frame(frame: pd.DataFrame | None, file_path: Path) -> None:
    """가격 DataFrame이 있을 때만 UTF-8-SIG CSV로 저장한다."""
    if frame is None or frame.empty:
        return
    file_path.parent.mkdir(parents=True, exist_ok=True)
    frame.to_csv(file_path, encoding="utf-8-sig", date_format="%Y-%m-%d")


def save_metadata(metadata: dict[str, Any]) -> None:
    """수집 메타데이터를 JSON으로 저장한다."""
    METADATA_FILE.write_text(json.dumps(metadata, ensure_ascii=False, indent=2), encoding="utf-8")


def main() -> None:
    """입력 포트폴리오에 필요한 가격과 환율 데이터만 수집한다."""
    configure_logging()
    ensure_directories()
    clean_previous_raw_outputs()

    config = load_portfolio_config()
    korean_stocks = config["korean_stocks"]
    us_stocks = config["us_stocks"]
    cash_krw = config["cash_krw"]
    start_date, end_date = get_collection_period()

    logging.info("데이터 수집 시작")
    logging.info("요청 기간: %s ~ %s", start_date, end_date)

    asset_master = build_asset_master(config)
    save_asset_master(asset_master)

    kr_prices, kr_success, kr_failures = collect_korean_prices(korean_stocks, start_date, end_date)
    us_prices, us_success, us_failures = collect_us_prices(us_stocks, start_date, end_date)

    fx_success = False
    fx_error = ""
    usdkrw_frame: pd.DataFrame | None = None
    if us_stocks:
        if not us_success:
            raise RuntimeError("미국주식이 입력되었지만 수집에 성공한 미국주식이 없습니다.")
        try:
            usdkrw = read_usdkrw_from_yfinance(start_date, end_date)
            usdkrw_frame = usdkrw.to_frame()
            usdkrw_frame.index.name = "날짜"
            fx_success = True
        except Exception as exc:
            fx_error = str(exc)
            raise RuntimeError(f"미국주식 환율 USD/KRW 수집에 실패했습니다: {exc}") from exc

    requested_risky_count = len(korean_stocks) + len(us_stocks)
    successful_risky_count = len(kr_success) + len(us_success)
    if requested_risky_count > 0 and successful_risky_count == 0:
        raise RuntimeError("입력된 모든 위험자산의 가격 수집에 실패했습니다.")

    save_price_frame(kr_prices, KR_PRICE_FILE)
    save_price_frame(us_prices, US_PRICE_FILE)
    save_price_frame(usdkrw_frame, USD_KRW_FILE)

    metadata = {
        "collection_start_date": start_date.isoformat(),
        "collection_end_date": end_date.isoformat(),
        "input_korean_stocks": korean_stocks,
        "input_us_stocks": us_stocks,
        "cash_krw": cash_krw,
        "successful_symbols": {
            "KR": kr_success,
            "US": us_success,
        },
        "failed_symbols": kr_failures + us_failures,
        "fx_collected": fx_success,
        "fx_error": fx_error,
        "asset_master_file": str(ASSET_MASTER_FILE),
        "kr_price_file": str(KR_PRICE_FILE) if KR_PRICE_FILE.exists() else None,
        "us_price_file": str(US_PRICE_FILE) if US_PRICE_FILE.exists() else None,
        "usdkrw_file": str(USD_KRW_FILE) if USD_KRW_FILE.exists() else None,
    }
    save_metadata(metadata)

    print("\n" + "=" * 70)
    print("1단계 완료: 포트폴리오 입력 종목 데이터 수집")
    print("=" * 70)
    print(f"수집 기간: {start_date} ~ {end_date}")
    print(f"한국주식 성공: {', '.join(kr_success) if kr_success else '없음'}")
    print(f"미국주식 성공: {', '.join(us_success) if us_success else '없음'}")
    print(f"환율 수집: {'성공' if fx_success else '해당 없음'}")
    print(f"현금: {cash_krw:,.0f}원")
    print(f"자산명 매핑: {ASSET_MASTER_FILE}")
    print(f"메타데이터: {METADATA_FILE}")
    if KR_PRICE_FILE.exists():
        print(f"한국주식 가격: {KR_PRICE_FILE}")
    if US_PRICE_FILE.exists():
        print(f"미국주식 가격: {US_PRICE_FILE}")
    if USD_KRW_FILE.exists():
        print(f"USD/KRW 환율: {USD_KRW_FILE}")
    if metadata["failed_symbols"]:
        print("\n[수집 실패 종목]")
        for failure in metadata["failed_symbols"]:
            print(f"- {failure['market']} {failure['ticker']}: {failure['error']}")


if __name__ == "__main__":
    main()
