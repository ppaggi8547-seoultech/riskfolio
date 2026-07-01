# 다자산 포트폴리오 VaR 기반 리스크 측정 대시보드

## 프로젝트 개요

본 프로젝트는 사용자가 보유한 한국주식, 미국주식, 원화 현금을 입력하면 과거 가격 데이터와 일별 USD/KRW 환율 데이터를 기반으로 포트폴리오의 손실위험을 측정하는 Python 기반 리스크관리 대시보드입니다.

기존 SK하이닉스 단일 종목 VaR 프로젝트를 확장해, 입력된 종목만 데이터 수집하고 모든 평가금액과 수익률을 원화 기준으로 계산합니다.

## 입력 가능 자산

- 한국주식: 6자리 종목코드와 수량
- 미국주식: 티커와 수량
- 현금: 원화 금액

예시 입력:

```json
{
  "korean_stocks": [
    {
      "market": "KR",
      "ticker": "000660",
      "quantity": 10
    },
    {
      "market": "KR",
      "ticker": "005930",
      "quantity": 20
    }
  ],
  "us_stocks": [
    {
      "market": "US",
      "ticker": "NVDA",
      "quantity": 3
    },
    {
      "market": "US",
      "ticker": "MSFT",
      "quantity": 2
    }
  ],
  "cash_krw": 5000000
}
```

## 미국주식 환율 처리

미국주식은 일별 USD/KRW 환율을 적용해 원화 평가금액으로 변환한 뒤 수익률과 VaR을 계산합니다.

예를 들어 NVDA 3주, NVDA 달러 종가 150달러, USD/KRW 1,350원이라면 원화 평가금액은 다음과 같습니다.

```text
3 × 150 × 1,350 = 607,500원
```

따라서 미국주식 수익률에는 미국 주가 변동과 환율 변동이 모두 반영됩니다.

## 매수가격, 매수일자, 평가손익

본 프로젝트는 보유 종목 입력 시 매수가격을 함께 입력받아 현재 평가손익과 수익률을 계산합니다.

한국주식 입력 형식:

```text
종목코드,수량,매수가격
```

예:

```text
005930,236,320656
```

한국주식 매수가격은 원화 기준입니다.

미국주식 입력 형식:

```text
티커,수량,매수가격,매수일자
```

예:

```text
GOOGL,29,260.5,2024-03-15
```

미국주식 매수가격은 달러 기준이며, 매수일자는 `YYYY-MM-DD` 형식입니다.
미국주식의 매수금액 원화 환산에는 매수일자의 USD/KRW 환율을 적용합니다.
현재평가금액 원화 환산에는 최신 USD/KRW 환율을 적용합니다.

따라서 미국주식의 원화 기준 수익률은 주가 변동과 환율 변동을 모두 반영합니다.

예를 들어 GOOGL 29주를 주당 260.5달러에 2024-03-15 매수했고,
2024-03-15 USD/KRW 환율이 1,320원, 현재 GOOGL 가격이 386.45달러,
현재 USD/KRW 환율이 1,360원이라면 다음과 같이 계산합니다.

```text
매수금액 원화 = 260.5 × 29 × 1,320
현재평가금액 원화 = 386.45 × 29 × 1,360
총 수익 = 현재평가금액 원화 - 매수금액 원화
수익률 = 현재평가금액 원화 / 매수금액 원화 - 1
```

매수일자가 환율 데이터의 휴장일 또는 결측일이면 해당 날짜 이전의 가장 가까운 환율을 사용합니다.

## 주요 리스크 지표

- Historical VaR
- Parametric VaR
- Monte Carlo VaR
- Expected Shortfall
- MDD
- 일간/연환산 변동성
- 자산 간 상관관계
- 스트레스 테스트
- Rolling window VaR 백테스팅
- Kupiec unconditional coverage test

## 프로젝트 구조

```text
VarProject/
├─ config.py
├─ portfolio_input.py
├─ step1_data_collection.py
├─ step2_return_calculation.py
├─ step3_risk_metrics.py
├─ step5_var_backtesting.py
├─ step4_visualization_report.py
├─ run_all.py
├─ app.py
├─ requirements.txt
├─ README.md
├─ data/
│  ├─ input/
│  ├─ raw/
│  │  └─ fx/
│  └─ processed/
└─ outputs/
   ├─ charts/
   └─ tables/
```

## 설치 방법

PowerShell에서 프로젝트 폴더로 이동한 뒤 다음을 실행합니다.

```powershell
py -m pip install -r requirements.txt
```

`py` 명령이 없다면 Windows용 Python을 설치하고 Python Launcher를 활성화하세요.

## 실행 방법

CLI 입력:

```powershell
cd "C:\Users\ppagg\Desktop\Python\VarProject.py"
python portfolio_input.py
```

전체 분석:

```powershell
python run_all.py
```

대시보드 실행:

```powershell
python -m streamlit run app.py
```

Streamlit 앱의 `Portfolio Input` 탭에서도 한국주식, 미국주식, 현금을 입력하고 `포트폴리오 저장`, `전체 분석 실행` 버튼을 사용할 수 있습니다.

## 데이터 처리 흐름

1. `portfolio_input.py`
   - 한국주식 종목코드와 수량 입력
   - 미국주식 티커와 수량 입력
   - 원화 현금 입력
   - `data/input/portfolio_config.json` 저장

2. `step1_data_collection.py`
   - 입력된 한국주식만 FinanceDataReader로 수집
   - 입력된 미국주식만 yfinance로 수집
   - 미국주식이 있으면 yfinance의 `KRW=X`로 USD/KRW 환율 수집

3. `step2_return_calculation.py`
   - 한국주식: 원화 종가 × 수량
   - 미국주식: 달러 종가 × 수량 × USD/KRW
   - 현금: 원화 기준 고정
   - 전체 포트폴리오 원화 가치와 일별 수익률 계산

4. `step3_risk_metrics.py`
   - 전체 포트폴리오 리스크 지표 계산
   - 개별 자산 리스크 지표 계산
   - 상관관계와 스트레스 테스트 계산

5. `step5_var_backtesting.py`
   - 전체 포트폴리오 수익률 기준 rolling VaR 백테스팅

6. `step4_visualization_report.py`
   - 차트와 텍스트 리포트 생성

## 산출물 설명

| 경로 | 내용 |
|---|---|
| `data/input/portfolio_config.json` | 사용자가 입력한 포트폴리오 구성 |
| `data/raw/kr_prices.csv` | 입력 한국주식의 일별 원화 종가 |
| `data/raw/us_prices.csv` | 입력 미국주식의 일별 달러 가격 |
| `data/raw/fx/usdkrw.csv` | 일별 USD/KRW 환율 |
| `data/raw/collection_metadata.json` | 데이터 수집 성공/실패 및 기간 메타데이터 |
| `data/processed/asset_values_krw.csv` | 자산별 일별 원화 평가금액 |
| `data/processed/asset_returns_krw.csv` | 자산별 일별 원화 기준 수익률 |
| `data/processed/portfolio_values.csv` | 전체 포트폴리오 일별 원화 가치 |
| `data/processed/portfolio_returns.csv` | 전체 포트폴리오 일별 수익률, 손익, 누적수익률 |
| `data/processed/position_summary.csv` | 마지막 거래일 기준 보유 현황과 비중 |
| `data/processed/risk_summary.csv` | 전체 포트폴리오 리스크 요약 |
| `data/processed/asset_risk_summary.csv` | 개별 자산별 리스크 요약 |
| `data/processed/correlation_matrix.csv` | 위험자산 수익률 상관관계 |
| `data/processed/stress_test.csv` | 전체 포트폴리오 스트레스 테스트 |
| `data/processed/asset_stress_test.csv` | 개별 자산 스트레스 테스트 |
| `data/processed/var_backtest.csv` | rolling VaR 백테스팅 상세 결과 |
| `data/processed/var_backtest_summary.csv` | 백테스팅 요약과 Kupiec test 결과 |
| `outputs/charts/portfolio_value.png` | 전체 포트폴리오 가치 추이 |
| `outputs/charts/cumulative_return.png` | 누적수익률 추이 |
| `outputs/charts/return_distribution.png` | 수익률 분포와 95% Historical VaR 기준선 |
| `outputs/charts/drawdown.png` | Drawdown 추이 |
| `outputs/charts/asset_weights.png` | 현재 자산별 비중 |
| `outputs/charts/correlation_heatmap.png` | 상관관계 히트맵 |
| `outputs/charts/var_backtest_breaches.png` | VaR breach 백테스팅 차트 |
| `outputs/report_summary.txt` | 자동 생성 리스크 리포트 |

한국주식이 없으면 `kr_prices.csv`는 생성되지 않을 수 있습니다.
미국주식이 없으면 `us_prices.csv`와 `usdkrw.csv`는 생성되지 않을 수 있습니다.
현금만 있는 경우 가격 데이터 파일 없이도 포트폴리오 가치, 수익률, 리스크 지표, 대시보드가 정상 작동합니다.

## 휴장일과 결측치 처리

한국과 미국 시장은 휴장일이 다르고 환율 데이터도 휴일 차이가 있을 수 있습니다.

본 프로젝트는 다음 원칙으로 처리합니다.

1. 모든 자산 가격과 환율을 날짜 인덱스로 정렬합니다.
2. outer join으로 날짜를 합칩니다.
3. 가격과 환율은 forward-fill합니다.
4. 첫 유효 가격 이전 구간은 제거합니다.
5. 포트폴리오 전체 가치가 계산 가능한 날짜만 사용합니다.

휴장일에는 직전 거래일 가격이 유지된다고 가정합니다.

## VaR 백테스팅

VaR 백테스팅은 과거 데이터로 계산한 VaR이 실제 손실을 얼마나 잘 설명했는지 검증하는 절차입니다.

본 프로젝트는 rolling window 방식을 사용합니다.

- 과거 252거래일 수익률로 다음 날 VaR을 추정합니다.
- 다음 날 실제 수익률이 -VaR보다 낮으면 VaR breach로 기록합니다.
- 이 과정을 전체 기간에 대해 반복합니다.

95% VaR의 경우 이론적으로 약 5%의 거래일에서 VaR 초과 손실이 발생해야 합니다.
99% VaR의 경우 이론적으로 약 1%의 거래일에서 VaR 초과 손실이 발생해야 합니다.

Kupiec test의 p-value가 0.05 이상이면 VaR 모델의 초과 빈도가 이론적 기대와 크게 다르지 않다고 해석합니다.
p-value가 0.05 미만이면 VaR 모델이 실제 손실위험을 과소평가하거나 과대평가했을 가능성이 있습니다.

## 대시보드 탭

1. Portfolio Input
2. Overview
3. Position Summary
4. Risk Summary
5. Asset Risk
6. Portfolio Trend
7. VaR Analysis
8. Backtesting
9. Correlation
10. Stress Test
11. Charts
12. Raw Data
13. Risk Glossary
14. Report

`Risk Glossary` 탭에서는 VaR, ES, MDD, Drawdown, 상관관계, 스트레스 테스트, VaR 백테스팅, Kupiec Test 등 대시보드에 사용된 리스크관리 용어의 정의, 계산 방식, 숫자 예시, 해석 방법과 주의사항을 확인할 수 있습니다.

## 한계점

- 과거 수익률 기반 분석이므로 미래 손실을 보장하지 않습니다.
- 환율 데이터 소스에 따라 결측 가능성이 있습니다.
- 배당, 세금, 수수료, 슬리피지는 반영하지 않습니다.
- 한국/미국 휴장일 차이는 forward-fill로 처리합니다.
- Monte Carlo는 정규분포 또는 과거 공분산 구조가 유지된다는 가정에 의존합니다.
- 미국주식 가격은 데이터 소스 기준 종가 또는 조정종가를 사용합니다.
- 데이터 제공처의 오류 또는 수정 방식이 결과에 영향을 줄 수 있습니다.
