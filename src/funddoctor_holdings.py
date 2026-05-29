"""funddoctor.co.kr report HTML fallback (optional pfund_cd mapping in fund_list.yaml)."""

from __future__ import annotations

from typing import Any

import requests

from holdings_parse import parse_holdings_html

FUNDDOCTOR_REPORT_URL = (
    "https://file.funddoctor.co.kr/app/file_download.asp"
    "?file_gb=R5&memb_cd={memb_cd}&pfund_cd={pfund_cd}"
)


def fetch_holdings_funddoctor(
    *,
    memb_cd: str,
    pfund_cd: str,
    use_gemini: bool = False,
    srtn_cd: str = "",
    bas_dt: str = "",
) -> tuple[list[dict[str, Any]], str]:
    if not memb_cd or not pfund_cd:
        return [], "unavailable"
    url = FUNDDOCTOR_REPORT_URL.format(memb_cd=memb_cd, pfund_cd=pfund_cd)
    try:
        resp = requests.get(
            url,
            timeout=45,
            headers={"User-Agent": "Mozilla/5.0 (compatible; KofiaHoldingsBot/1.0)"},
        )
        resp.raise_for_status()
        html = resp.text
    except Exception:
        return [], "unavailable"

    holdings = parse_holdings_html(html, source=f"funddoctor:{pfund_cd}")
    if not holdings and use_gemini:
        from gemini_extract import extract_holdings_from_report_text

        holdings = extract_holdings_from_report_text(
            html,
            srtn_cd=srtn_cd,
            bas_dt=bas_dt,
            source="funddoctor:gemini",
        )
    return (holdings, "funddoctor") if holdings else ([], "unavailable")
