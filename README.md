# Kofia — dis.kofia 분기 수집 (GHA / HTTP only)

KOFIA 전자공시(dis)에서 **보유 펀드**의 분기 자산배분·top10(proxy)을 수집해 `data/timeseries/` CSV로 누적합니다.

## 펀드 목록 변경 (핵심)

1. **[docs/holdings_fund_list.md](docs/holdings_fund_list.md)** 표만 편집 (`enabled`, `srtn_cd`, `alias`, 펀드명).
2. `python src/fund_list_sync.py` → [config/fund_list.yaml](config/fund_list.yaml) 생성.
3. `python src/dis_parser.py --fetch` → **`enabled: true` 펀드만** 수집.

**현재 설정:** 34종 등록, **TDF2050_Ce** (`K55301D51271`)만 `enabled: true`.

### GitHub Actions

| Workflow | 언제 |
|----------|------|
| [**Sync fund list and fetch**](.github/workflows/sync-and-fetch.yml) | `holdings_fund_list.md` 수정 후 push |
| [**Kofia fetch (code push)**](.github/workflows/kofia-fetch.yml) | 파서·설정 코드 변경 시 |
| [Verify](.github/workflows/verify-dis.yml) · [Test](.github/workflows/test.yml) | PR/push 검증 |

`workflow_dispatch`에서 `sync_only` / `commit_data` / `alias` 선택 가능.

## 로컬 실행

```bash
pip install -r requirements.txt
python src/fund_list_sync.py              # holdings → YAML
python src/fund_list_sync.py --dry-run
python src/dis_parser.py --sync --fetch   # 동기화 후 수집
python src/dis_parser.py --dry-run        # enabled 펀드 G1
python src/dis_parser.py --fetch
python src/resolve_srtn.py                # srtn_cd 일괄 조회 (선택)
python -m pytest tests/ -q
```

## 산출물

| 파일 | 설명 |
|------|------|
| `fund_allocation.csv` | 자산군 비중 |
| `fund_holdings_top10.csv` | BS 계정 top10 proxy |
| `fund_registry.csv` | 표준코드·펀드명 |
| `fund_std_price.csv` | 기준가 (가능 시) |

## 문서

- [docs/PRD.md](docs/PRD.md) · [docs/VERIFICATION.md](docs/VERIFICATION.md) · [docs/SPIKE_QUARTERLY.md](docs/SPIKE_QUARTERLY.md)

## 기술

- Playwright 없음 · ProFrame `requests` (`FS-DIS2` / `FS-DIS`)
- Secret (선택): `GEMINI_API_KEY`
