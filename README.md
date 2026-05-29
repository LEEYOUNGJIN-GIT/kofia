# Kofia — dis.kofia 분기 수집

KOFIA 전자공시(dis)에서 보유 펀드의 분기 **자산배분**·**top10(BS proxy)** 을 수집해 `data/timeseries/` CSV로 누적합니다.

## 펀드 목록

1. [docs/holdings_fund_list.md](docs/holdings_fund_list.md) 표 편집
2. `python src/fund_list_sync.py` → `config/fund_list.yaml`
3. GitHub **Actions → Sync fund list and fetch** (또는 holdings push) → sync 후 **리스트 전체** fetch

| Workflow | 용도 |
|----------|------|
| [sync-and-fetch.yml](.github/workflows/sync-and-fetch.yml) | holdings 동기화 + fetch |
| [test.yml](.github/workflows/test.yml) | `src`/`tests` 변경 시 pytest |

`alias`로 1종만, `enabled_only: true`로 enabled만 수집 가능.

## 로컬

```bash
pip install -r requirements.txt
python src/fund_list_sync.py
python src/dis_parser.py --sync --fetch --all-funds
python src/dis_parser.py --dry-run
python -m pytest tests/ -q
```

## 산출물 (`data/timeseries/`)

`fund_allocation.csv` · `fund_holdings_top10.csv` · `fund_registry.csv` · `fund_std_price.csv`

HTTP only (`requests`, ProFrame). Playwright 없음.
