# Kofia — dis.kofia 분기 수집

[docs/holdings_fund_list.md](docs/holdings_fund_list.md) **전체 펀드**에 대해 dis 데이터를 수집하고, **포트폴리오 분석 JSON**으로 통합합니다.

## 산출물

| 파일 | 설명 |
|------|------|
| **`data/reports/fund_portfolio_analysis_YYYYMMDD.json`** | **메인 분석 자료** — `allocation`, `holdings`, `top10_bs`, `price_trend` |
| `data/logs/run_*_fetch.json` | 실행 manifest (동일 fetch 결과) |
| `data/timeseries/fund_allocation.csv` | 자산배분 시계열 |
| `data/timeseries/fund_std_price.csv` | 기준가 **가격 추세** (일자별 upsert) |

`holdings`(공시 보유내역, 가변 길이) / `top10_bs` / `price_trend`는 JSON 본문입니다. `top10`은 `holdings`와 동일(호환용).

## 펀드 목록

1. [docs/holdings_fund_list.md](docs/holdings_fund_list.md) 표 편집
2. `python src/fund_list_sync.py`
3. **Actions → Sync fund list and fetch** (또는 holdings push)

| Workflow | 용도 |
|----------|------|
| [sync-and-fetch.yml](.github/workflows/sync-and-fetch.yml) | sync + **전체 펀드** fetch |
| [test.yml](.github/workflows/test.yml) | pytest |

`use_gemini` / `use_dart` / `use_funddoctor` — 보유내역 fallback (아래 참고).

## 로컬

```bash
pip install -r requirements.txt
python src/fund_list_sync.py
python src/dis_parser.py --fetch --all-funds
python src/dis_parser.py --fetch --alias TDF2050_Ce
python src/dis_parser.py --fetch --all-funds --gemini --dart
python src/dis_parser.py --fetch --alias TDF2050_Ce --funddoctor
python -m pytest tests/ -q
```

환경 변수(선택): `GEMINI_API_KEY`, `OPENDART_API_KEY`.

## 보유내역 · 가격 추세

- **holdings** — 공시 표 전체(가변 길이). **fallback 순서**
  1. KOFIA ProFrame SO
  2. (`--gemini`) KOFIA 첨부 PDF/HTML → Gemini
  3. (`--dart`) DART 원본 → HTML 파서 → 실패/노이즈 시 Gemini (KOFIA와 **동일 본문**이면 Gemini 생략)
  4. (`--funddoctor`) funddoctor HTML → 동일
- HTML 파서가 전화번호·날짜 등 **노이즈만** 잡으면 빈 결과로 보고 다음 단계 또는 Gemini 시도
- **top10_bs** — 결산 BS 계정 상위(프록시, 항상)
- **price_trend** — `DISFundStdPriceSO` 월말 `tmpV30` 다회 조회

HTTP only. Playwright 없음.

## 문서

- [docs/SPIKE_HOLDINGS.md](docs/SPIKE_HOLDINGS.md) — top10 SO·Gemini 경로
