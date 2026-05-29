# Kofia — dis.kofia 분기 수집 (GHA / HTTP only)

**목표:** GitHub Actions에서 `requests` + ProFrame XML로 펀드 메타·자산배분·top10(proxy) 시계열을 수집한다.

## 문서

- [docs/PRD.md](docs/PRD.md)
- [docs/VERIFICATION.md](docs/VERIFICATION.md)
- [docs/holdings_fund_list.md](docs/holdings_fund_list.md)
- [docs/SPIKE_QUARTERLY.md](docs/SPIKE_QUARTERLY.md)

## 로컬 실행

```bash
pip install -r requirements.txt
python src/dis_parser.py --dry-run --alias TDF2050_Ce
python src/dis_parser.py --fetch --alias TDF2050_Ce
python src/dis_parser.py --fetch --from 2024Q4 --to 2025Q1 --alias TDF2050_Ce
python src/resolve_srtn.py   # srtn_cd 일괄 조회 (enabled/missing)
python -m pytest tests/ -q
```

## 산출물 (`data/timeseries/`)

| 파일 | 설명 |
|------|------|
| `fund_allocation.csv` | 자산군 비중 (BS·asset_class_map) |
| `fund_holdings_top10.csv` | BS 계정 상위 10 proxy |
| `fund_registry.csv` | 표준코드·펀드명 |
| `fund_std_price.csv` | 기준가 그리드 (가능 시) |

## GitHub Actions

| Workflow | 역할 |
|----------|------|
| [verify-dis.yml](.github/workflows/verify-dis.yml) | G1 dry-run |
| [kofia-fetch.yml](.github/workflows/kofia-fetch.yml) | fetch + artifact (`commit_data` 기본 false) |
| [test.yml](.github/workflows/test.yml) | fixture 회귀 테스트 |

Secrets (선택): `GEMINI_API_KEY`

## 아키텍처

- Playwright 없음 · `FS-DIS2` / `FS-DIS` ProFrame
- M1 배분: `dis_quarterly` + `config/asset_class_map.yaml`
- M2 top10: `dis_top10` (BS 계정 proxy; PDF는 `pdf_parse.py`)
