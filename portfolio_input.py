"""CLI와 Streamlit에서 공통으로 쓰는 포트폴리오 입력·검증·저장 유틸리티."""

from __future__ import annotations

import json
import re
from datetime import date, datetime
from typing import Any

from config import PORTFOLIO_CONFIG_FILE, ensure_directories

KR_TICKER_PATTERN = re.compile(r"^\d{6}$")
US_TICKER_PATTERN = re.compile(r"^[A-Z][A-Z0-9.\-]*$")


def validate_kr_ticker(ticker: str) -> str:
    """한국주식 종목코드를 6자리 숫자 문자열로 검증한다."""
    normalized = str(ticker).strip()
    if not KR_TICKER_PATTERN.fullmatch(normalized):
        raise ValueError("한국주식 종목코드는 6자리 숫자여야 합니다. 예: 000660")
    return normalized


def validate_us_ticker(ticker: str) -> str:
    """미국주식 티커를 대문자로 정규화하고 기본 형식을 검증한다."""
    normalized = str(ticker).strip().upper()
    if not US_TICKER_PATTERN.fullmatch(normalized):
        raise ValueError("미국주식 티커 형식이 올바르지 않습니다. 예: NVDA, MSFT")
    return normalized


def validate_positive_quantity(quantity: Any) -> float:
    """수량을 양수 float로 검증한다."""
    try:
        value = float(quantity)
    except (TypeError, ValueError) as exc:
        raise ValueError("수량은 양수 숫자여야 합니다.") from exc
    if value <= 0:
        raise ValueError("수량은 0보다 커야 합니다.")
    return value


def validate_cash(cash: Any) -> float:
    """원화 현금을 0 이상 float로 검증한다."""
    try:
        value = float(cash)
    except (TypeError, ValueError) as exc:
        raise ValueError("현금은 0 이상 숫자여야 합니다.") from exc
    if value < 0:
        raise ValueError("현금은 0 이상이어야 합니다.")
    return value


def validate_purchase_price(value: Any) -> float | None:
    """선택 입력 매수가격을 검증한다. 비어 있으면 None을 반환한다."""
    if value is None:
        return None
    if isinstance(value, str) and not value.strip():
        return None
    try:
        price = float(value)
    except (TypeError, ValueError) as exc:
        raise ValueError("매수가격은 0보다 큰 숫자여야 합니다.") from exc
    if price <= 0:
        raise ValueError("매수가격은 0보다 커야 합니다.")
    return price


def validate_purchase_date(value: Any) -> str | None:
    """선택 입력 매수일자를 YYYY-MM-DD 형식으로 검증한다."""
    if value is None:
        return None
    text = str(value).strip()
    if not text:
        return None
    try:
        parsed = datetime.strptime(text, "%Y-%m-%d").date()
    except ValueError as exc:
        raise ValueError("매수일자는 YYYY-MM-DD 형식이어야 합니다. 예: 2024-03-15") from exc
    if parsed > date.today():
        raise ValueError("미래 날짜는 매수일자로 입력할 수 없습니다.")
    return parsed.isoformat()


def normalize_portfolio_config(config: dict[str, Any]) -> dict[str, Any]:
    """입력 dict를 표준 portfolio_config.json 구조로 정규화한다."""
    korean_stocks: list[dict[str, Any]] = []
    us_stocks: list[dict[str, Any]] = []

    for position in config.get("korean_stocks", []) or []:
        ticker = validate_kr_ticker(position.get("ticker", ""))
        quantity = validate_positive_quantity(position.get("quantity", 0))
        purchase_price = validate_purchase_price(position.get("purchase_price"))
        korean_stocks.append(
            {
                "market": "KR",
                "ticker": ticker,
                "quantity": quantity,
                "purchase_price": purchase_price,
                "purchase_currency": "KRW",
            }
        )

    for position in config.get("us_stocks", []) or []:
        ticker = validate_us_ticker(position.get("ticker", ""))
        quantity = validate_positive_quantity(position.get("quantity", 0))
        purchase_price = validate_purchase_price(position.get("purchase_price"))
        purchase_date = validate_purchase_date(position.get("purchase_date"))
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

    cash_krw = validate_cash(config.get("cash_krw", 0))
    if not korean_stocks and not us_stocks and cash_krw == 0:
        raise ValueError("한국주식, 미국주식, 현금이 모두 비어 있습니다. 최소 하나는 입력해야 합니다.")

    return {
        "korean_stocks": korean_stocks,
        "us_stocks": us_stocks,
        "cash_krw": cash_krw,
    }


def parse_position_lines(text: str, market: str) -> list[dict[str, Any]]:
    """멀티라인 포지션 입력 텍스트를 포지션 목록으로 변환한다.

    한국주식: 종목코드,수량 또는 종목코드,수량,매수가격
    미국주식: 티커,수량 또는 티커,수량,매수가격,매수일자
    """
    positions: list[dict[str, Any]] = []
    validator = validate_kr_ticker if market == "KR" else validate_us_ticker

    for line_number, raw_line in enumerate((text or "").splitlines(), start=1):
        line = raw_line.strip()
        if not line:
            continue
        parts = [part.strip() for part in line.split(",")]
        if market == "KR" and len(parts) not in {2, 3}:
            raise ValueError(f"{line_number}번째 줄 형식이 올바르지 않습니다. 예: 005930,236,320656")
        if market == "US" and len(parts) == 3:
            raise ValueError(
                "미국주식은 매수가격을 입력할 경우 매수일자도 함께 입력해야 합니다. "
                "예: GOOGL,29,260.5,2024-03-15"
            )
        if market == "US" and len(parts) not in {2, 4}:
            raise ValueError(f"{line_number}번째 줄 형식이 올바르지 않습니다. 예: GOOGL,29,260.5,2024-03-15")
        ticker = validator(parts[0])
        quantity = validate_positive_quantity(parts[1])
        purchase_price = validate_purchase_price(parts[2]) if len(parts) >= 3 else None
        purchase_date = validate_purchase_date(parts[3]) if market == "US" and len(parts) == 4 else None
        if market == "US" and purchase_price is not None and purchase_date is None:
            raise ValueError(
                "미국주식은 매수가격을 입력할 경우 매수일자도 함께 입력해야 합니다. "
                "예: GOOGL,29,260.5,2024-03-15"
            )

        position = {
            "market": market,
            "ticker": ticker,
            "quantity": quantity,
            "purchase_price": purchase_price,
            "purchase_currency": "KRW" if market == "KR" else "USD",
        }
        if market == "US":
            position["purchase_date"] = purchase_date
        positions.append(position)

    return positions


def build_config_from_text_inputs(
    korean_text: str,
    us_text: str,
    cash_krw: Any,
) -> dict[str, Any]:
    """Streamlit 멀티라인 입력값을 portfolio_config 구조로 변환한다."""
    return normalize_portfolio_config(
        {
            "korean_stocks": parse_position_lines(korean_text, "KR"),
            "us_stocks": parse_position_lines(us_text, "US"),
            "cash_krw": cash_krw,
        }
    )


def save_portfolio_config(config: dict[str, Any]) -> dict[str, Any]:
    """검증된 포트폴리오 입력값을 data/input/portfolio_config.json에 저장한다."""
    normalized = normalize_portfolio_config(config)
    ensure_directories()
    PORTFOLIO_CONFIG_FILE.write_text(
        json.dumps(normalized, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    return normalized


def load_portfolio_config() -> dict[str, Any]:
    """portfolio_config.json을 읽고 표준 구조로 검증한다."""
    if not PORTFOLIO_CONFIG_FILE.exists():
        raise FileNotFoundError(
            f"{PORTFOLIO_CONFIG_FILE}가 없습니다. 먼저 python portfolio_input.py를 실행하세요."
        )
    try:
        raw_config = json.loads(PORTFOLIO_CONFIG_FILE.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        raise ValueError(f"portfolio_config.json 형식이 올바르지 않습니다: {exc}") from exc
    return normalize_portfolio_config(raw_config)


def _ask_menu(prompt: str) -> str:
    """0 또는 1 메뉴 입력을 받을 때까지 반복한다."""
    while True:
        answer = input(prompt).strip()
        if answer in {"0", "1"}:
            return answer
        print("0 또는 1만 입력하세요.")


def run_input_wizard() -> dict[str, Any]:
    """터미널에서 포트폴리오 구성을 입력받아 JSON으로 저장한다."""
    korean_stocks: list[dict[str, Any]] = []
    us_stocks: list[dict[str, Any]] = []

    print("\n[1단계] 한국주식 입력")
    while True:
        answer = _ask_menu("한국 주식 종목코드를 입력하시겠습니까?\n0: 입력\n1: 미국주식 입력 단계로 이동\n선택: ")
        if answer == "1":
            break
        try:
            ticker = validate_kr_ticker(input("종목코드: "))
            quantity = validate_positive_quantity(input("수량: "))
            purchase_price = validate_purchase_price(input("매수가격(원, 선택): "))
        except ValueError as exc:
            print(f"입력 오류: {exc}")
            continue
        korean_stocks.append(
            {
                "market": "KR",
                "ticker": ticker,
                "quantity": quantity,
                "purchase_price": purchase_price,
                "purchase_currency": "KRW",
            }
        )
        price_text = f", 매수가격 {purchase_price:,.0f}원" if purchase_price is not None else ""
        print(f"추가됨: {ticker}, 수량 {quantity:g}{price_text}")

    print("\n[2단계] 미국주식 입력")
    while True:
        answer = _ask_menu("미국 주식 티커를 입력하시겠습니까?\n0: 입력\n1: 현금 입력 단계로 이동\n선택: ")
        if answer == "1":
            break
        try:
            ticker = validate_us_ticker(input("티커: "))
            quantity = validate_positive_quantity(input("수량: "))
            purchase_price = validate_purchase_price(input("매수가격(달러, 선택): "))
            purchase_date = validate_purchase_date(input("매수일자(YYYY-MM-DD, 매수가격 입력 시 필수): "))
            if purchase_price is not None and purchase_date is None:
                raise ValueError(
                    "미국주식은 매수가격을 입력할 경우 매수일자도 함께 입력해야 합니다. "
                    "예: GOOGL,29,260.5,2024-03-15"
                )
        except ValueError as exc:
            print(f"입력 오류: {exc}")
            continue
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
        price_text = f", 매수가격 ${purchase_price:,.2f}, 매수일자 {purchase_date}" if purchase_price is not None else ""
        print(f"추가됨: {ticker}, 수량 {quantity:g}{price_text}")

    print("\n[3단계] 원화 현금 입력")
    while True:
        try:
            cash_krw = validate_cash(input("보유 원화 현금을 입력하세요.\n현금: "))
            config = save_portfolio_config(
                {
                    "korean_stocks": korean_stocks,
                    "us_stocks": us_stocks,
                    "cash_krw": cash_krw,
                }
            )
            break
        except ValueError as exc:
            print(f"입력 오류: {exc}")

    print("\n포트폴리오 입력이 저장되었습니다.")
    print(PORTFOLIO_CONFIG_FILE)
    print(json.dumps(config, ensure_ascii=False, indent=2))
    return config


def main() -> None:
    """CLI 진입점."""
    run_input_wizard()


if __name__ == "__main__":
    main()
