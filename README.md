# Kofia — dis.kofia 분기 수집

[docs/holdings_fund_list.md](docs/holdings_fund_list.md) **전체 펀드**에 대해 dis 데이터를 수집하고, **포트폴리오 분석 JSON 하나**로 통합합니다.

## 산출물

| 저장 위치 | 설명 |
|-----------|------|
| **`data/reports/fund_portfolio_analysis_YYYYMMDD.json`** | **메인·유일한 분석 산출물** (GitHub Actions fetch 후 `main`에 커밋) |
| `data/logs/run_*_fetch.json` | 실행 manifest (로컬·gitignore; Actions Artifacts로만 제공) |

### JSON `funds[]` 한 펀드에 들어가는 필드

| 필드 | 내용 |
|------|------|
| `registry` | DIS `standardCd`, 한글명, 운용사 코드, `fnd_tp` |
| `price_trend` | 월말 기준가 시계열 |
| `std_price_month_end` | 최근 월말 기준가 스냅샷 |
| `std_price_latest` | 최근 영업일 기준가 스냅샷 |
| `report_standard_dt`, `bas_dt` | 결산보고 기준일(메타) |

## 펀드 목록

1. [docs/holdings_fund_list.md](docs/holdings_fund_list.md) 표 편집
2. `python src/fund_list_sync.py`
3. **Actions → Sync fund list and fetch** (또는 fund list push)

| Workflow | 용도 |
|----------|------|
| [sync-and-fetch.yml](.github/workflows/sync-and-fetch.yml) | sync + 전체 펀드 fetch → **JSON 커밋** |
| [test.yml](.github/workflows/test.yml) | pytest |

## 로컬

```bash
pip install -r requirements.txt
python src/fund_list_sync.py
python src/dis_parser.py --fetch --all-funds
python src/dis_parser.py --fetch --alias TDF2050_Ce
python -m pytest tests/ -q
```

`price_trend[].chg_pct`는 **전일(이전 시계열 점) 대비 %**로 계산합니다 (`tmpV7`은 이전 기준가 참고용 `prior_std_price`).
