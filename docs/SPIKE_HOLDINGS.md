# SPIKE: top10 data sources (HTTP only)

## ProFrame (primary)

| SO | fn | inDto | Notes |
|----|-----|-------|-------|
| DISStandValInqSO | inquiryStandVal | DISStandValDTO | Settlement report stand val |
| DISTradeInqSO | inquiryTrade | DISTradeDTO | Trade inquiry |
| DISmetaRowDynm10SO | select | DISmetaRowInputListDTO | Dynamic report rows |

Parser: [`src/dis_holdings.py`](../src/dis_holdings.py) — list rows with name + weight heuristics.

## Gemini (optional, no Playwright)

When SO returns no rows and `--gemini` + `GEMINI_API_KEY`:

1. `DISFTimeAnnSO` → attachment URL (best-effort)
2. `requests` download PDF/HTML → text
3. `gemini_extract.extract_top10_from_report_text`

## BS top10_bs (always)

`DISFundSetRptBSSO` → [`top10_bs_from_bs`](../src/dis_top10.py) — account lines, not securities.

## Price trend

`DISFundStdPriceSO` grid — all `selectMeta` rows where `tmpV12 == srtn_cd` → [`dis_std_price.py`](../src/dis_std_price.py).
