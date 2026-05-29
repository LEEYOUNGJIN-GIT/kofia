# SPIKE: disclosed holdings (variable length)

## Parsing goal

Collect **all rows** in public disclosure tables (main holdings + 5%/1% footnotes), not a fixed top 10.

JSON field: `holdings` (array, `holdings_count`). `top10` is a deprecated alias of the same array.

## Fallback order

| Step | Source | Flag / config |
|------|--------|----------------|
| 1 | KOFIA ProFrame SO | always |
| 2 | KOFIA 첨부 + Gemini | `--gemini`, `GEMINI_API_KEY` |
| 3 | DART `document.xml` (+ optional Gemini) | `--dart`, `OPENDART_API_KEY`, optional `dart_corp_code` |
| 4 | funddoctor report HTML | `--funddoctor`, `funddoctor.memb_cd` / `pfund_cd` in yaml |

Code: [`src/dis_holdings.py`](../src/dis_holdings.py) → `resolve_holdings()`.

### Quality & Gemini dedup

- [`holdings_parse.holdings_look_valid`](../src/holdings_parse.py) — 비중 0–100%, 종목명 휴리스틱; 노이즈면 다음 단계
- KOFIA 첨부 본문 fingerprint 저장 → DART/funddoctor Gemini 시 **동일 본문**이면 API 재호출 생략

## ProFrame (step 1)

| SO | fn | inDto |
|----|-----|-------|
| DISStandValInqSO | inquiryStandVal | DISStandValDTO |
| DISTradeInqSO | inquiryTrade | DISTradeDTO |
| DISmetaRowDynm10SO | select | DISmetaRowInputListDTO |

## BS top10_bs (separate, always)

`DISFundSetRptBSSO` → account-line proxy, not securities — [`dis_top10.py`](../src/dis_top10.py).

## fund_list.yaml (optional)

```yaml
- alias: TDF2050_Ce
  fnd_nm: ...
  srtn_cd: K55301D51271
  dart_corp_code: ""   # optional, speeds DART search
  funddoctor:
    memb_cd: "7301"
    pfund_cd: "01A20"
```

## Price trend

See previous section — `DISFundStdPriceSO` + `tmpV30` month-end snapshots in [`dis_std_price.py`](../src/dis_std_price.py).
