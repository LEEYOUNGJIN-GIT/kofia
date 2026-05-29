# 검증 결과 (dis.kofia · GHA · Playwright 없음)

> 검증일: 2026-05-29 · parser `0.3.0`

## 게이트

| 게이트 | 기준 | 로컬 | GHA (Release 후) |
|--------|------|------|------------------|
| G1 | `--dry-run` ProFrame | **통과** | push 후 Actions 확인 |
| G2 | `fund_allocation.csv` | **통과** (≥2 asset_class) | 동일 |
| G3 | upsert 재실행 | **통과** | 동일 |
| G5 | `fund_holdings_top10.csv` | **통과** (10행 proxy) | 동일 |
| Playwright | 미사용 | **준수** | — |

## 로컬 명령

```bash
pip install -r requirements.txt
python -m pytest tests/ -q
python src/dis_parser.py --dry-run --alias TDF2050_Ce
python src/dis_parser.py --fetch --alias TDF2050_Ce
```

## ProFrame 경로

- `POST https://dis.kofia.or.kr/proframeWeb/XMLSERVICES/`
- 검색 `DISComFundSrchSO` · 결산 `DISBsInq2SO` + `DISFundSetRptBSSO`
- 상세: [SPIKE_QUARTERLY.md](./SPIKE_QUARTERLY.md)

## TDF2050 C-e

| 필드 | 값 |
|------|-----|
| srtn_cd | `K55301D51271` |
| alias | `TDF2050_Ce` |

## 변경 이력

| 날짜 | 내용 |
|------|------|
| 2026-05-29 | M0.5 G1, M1 fetch+upsert, M2 top10 proxy, pytest fixtures |
