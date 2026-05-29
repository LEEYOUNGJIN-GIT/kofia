# Kofia — dis.kofia 분기 수집

[docs/holdings_fund_list.md](docs/holdings_fund_list.md) **전체 펀드**에 대해 dis 데이터를 수집하고, **포트폴리오 분석 JSON**으로 통합합니다.

## 산출물

| 파일 | 설명 |
|------|------|
| **`data/reports/fund_portfolio_analysis_YYYYMMDD.json`** | **메인 분석 자료** — 요약 + 펀드별 `allocation`, `top10`, `top10_bs`, `price_trend` |
| `data/logs/run_*_fetch.json` | 실행 manifest (동일 fetch 결과) |
| `data/timeseries/fund_allocation.csv` | 자산배분 시계열 |
| `data/timeseries/fund_std_price.csv` | 기준가 **가격 추세** (일자별 upsert) |

`top10` / `top10_bs` / `price_trend`는 JSON에 본문이 들어갑니다. CSV는 allocation·기준가 이력 위주입니다.

## 펀드 목록

1. [docs/holdings_fund_list.md](docs/holdings_fund_list.md) 표 편집
2. `python src/fund_list_sync.py`
3. **Actions → Sync fund list and fetch** (또는 holdings push)

| Workflow | 용도 |
|----------|------|
| [sync-and-fetch.yml](.github/workflows/sync-and-fetch.yml) | sync + **전체 펀드** fetch |
| [test.yml](.github/workflows/test.yml) | pytest |

`enabled_only: true` → enabled 펀드만. `use_gemini: true` → top10 SO 실패 시 Gemini(선택, `GEMINI_API_KEY`).

## 로컬

```bash
pip install -r requirements.txt
python src/fund_list_sync.py
python src/dis_parser.py --fetch --all-funds
python src/dis_parser.py --fetch --alias TDF2050_Ce
python src/dis_parser.py --fetch --all-funds --gemini
python -m pytest tests/ -q
```

## top10 · 가격 추세

- **top10_bs** — 결산 BS 계정 상위 10 + 비중 (항상)
- **top10** — ProFrame SO 우선 → (선택) 공시 PDF/HTML + Gemini
- **price_trend** — `DISFundStdPriceSO` 그리드에서 해당 펀드 전 일자 기준가

HTTP only. Playwright 없음.

## 문서

- [docs/SPIKE_HOLDINGS.md](docs/SPIKE_HOLDINGS.md) — top10 SO·Gemini 경로
