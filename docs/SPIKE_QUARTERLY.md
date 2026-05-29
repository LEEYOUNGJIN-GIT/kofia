# Spike: 분기영업·자산구성·top10 (TDF2050)

> 검증일: 2026-05-29 · HTTP only (Playwright 없음)

## 확정 ProFrame 경로

| 용도 | app | SO | fn | inDto |
|------|-----|----|----|-------|
| 펀드 검색 | FS-DIS2 | DISComFundSrchSO | search | DISComFundSrchListDTO |
| 결산 기준일 목록 | FS-DIS2 | DISBsInq2SO | inquiryBs | DISBsListDTO |
| 결산 대차대조표 | FS-DIS | DISFundSetRptBSSO | selectBS | DISFundSetRptBSDTO |
| 펀드 기준가 그리드 | FS-DIS2 | DISFundStdPriceSO | select | DISCondFuncDTO |
| 손익계산서 | FS-DIS | DISFundSetRptPLSO | selectPL | DISFundSetRptPLDTO |
| BS 세부(일반현황) | FS-DIS | DISFundSetRptGnrStutSO | select | DTOStandardDtList |

팝업 참고: `data/logs/DISFundSetRptBSPop.xml`, `DISFundSetRptPLPop.xml`, `DISFundSetRptGnrStutPop.xml` (로컬 Spike, git 제외)

## Open Q1 (PDF vs API)

| 항목 | 결과 |
|------|------|
| 분기영업 PDF 전용 여부 | 일부 보고서는 PDF; **결산 BS는 ProFrame XML로 즉시 조회 가능** |
| `DISRptFundSO` / `DISFixedAnnSO` | 공개 서버 **미배포** (COMS9009/COMS9002) |
| `DISFundSetRptGnrStutSO` | inDto `DTOStandardDtList` — 추가 필드 조합 Spike 필요, M2 top10 보조 |
| M1 구현 | **BS 다계정 → `asset_class_map.yaml` → fund_allocation** |
| M2 top10 | BS 계정 상위 N금액 **proxy** + 추후 PDF/`pdf_parse.py` |

## TDF2050 (K55301D51271)

- 최신 결산 기준일 예: `20250719`, `txCd`: `2RF0100`
- BS: `profitBnd` 비중 대부분 (혼합/TDF 특성)

## 구현 우선순위 (코드)

1. `dis_quarterly.allocation_from_bs` — map 확장
2. `dis_reports` BS fallback
3. `dis_top10` — BS 계정 top10 proxy
4. `pdf_parse` — PDF URL 확보 시 표 추출
