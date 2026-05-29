# 검증 결과 (dis.kofia · GHA · Playwright 없음)

> 검증일: 2026-05-29 · parser `0.3.0`

## 운영 설정 (현재)

| 항목 | 값 |
|------|-----|
| 펀드 마스터 | `docs/holdings_fund_list.md` |
| 수집 대상 | `enabled: true` 만 (현재 **TDF2050_Ce** 1종) |
| `srtn_cd` | `K55301D51271` |

## 게이트

| 게이트 | 기준 | 로컬 |
|--------|------|------|
| G1 | `--dry-run` (enabled 전체) | 통과 |
| G2 | `fund_allocation.csv` | 통과 |
| G3 | upsert 재실행 | 통과 |
| G5 | `fund_holdings_top10.csv` | 통과 |
| sync | `fund_list_sync.py` | 34종 → YAML |

## 로컬 명령

```bash
pip install -r requirements.txt
python src/fund_list_sync.py
python -m pytest tests/ -q
python src/dis_parser.py --dry-run
python src/dis_parser.py --fetch
```

## GitHub Actions

| Workflow | 트리거 |
|----------|--------|
| **Sync fund list and fetch** | `holdings_fund_list.md` push |
| **Kofia fetch (code push)** | `src/`·`tests/` push |
| **Verify dis.kofia** | 설정·코드 push |
| **Test parsers** | `tests/` push |

## 변경 이력

| 날짜 | 내용 |
|------|------|
| 2026-05-29 | holdings 마스터 + sync 파이프라인 |
| 2026-05-29 | M1 fetch / M2 top10 proxy |
