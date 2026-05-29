"""funddoctor.co.kr report HTML fallback (optional pfund_cd mapping in fund_list.yaml)."""

from __future__ import annotations

from typing import Any

import requests

from holdings_parse import (
    filter_valid_holdings,
    holdings_look_valid,
    parse_holdings_html,
    report_text_fingerprint,
)

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
    skip_gemini_if_fingerprint: str | None = None,
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

    source = f"funddoctor:{pfund_cd}"
    holdings = filter_valid_holdings(parse_holdings_html(html, source=source))

    need_gemini = use_gemini and not holdings
    if need_gemini and skip_gemini_if_fingerprint:
        if report_text_fingerprint(html) == skip_gemini_if_fingerprint:
            need_gemini = False

    if need_gemini:
        from gemini_extract import extract_holdings_from_report_text

        holdings = filter_valid_holdings(
            extract_holdings_from_report_text(
                html,
                srtn_cd=srtn_cd,
                bas_dt=bas_dt,
                source="funddoctor:gemini",
            )
        )
        if holdings:
            return holdings, "funddoctor"

    if holdings and holdings_look_valid(holdings):
        return holdings, "funddoctor"
    return [], "unavailable"
