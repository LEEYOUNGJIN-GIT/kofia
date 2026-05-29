"""DART Open API fallback: fund disclosure document → holdings (variable length)."""

from __future__ import annotations

import io
import os
import zipfile
from datetime import datetime, timedelta, timezone
from typing import Any

import requests

from holdings_parse import parse_holdings_html

DART_LIST_URL = "https://opendart.fss.or.kr/api/list.json"
DART_DOCUMENT_URL = "https://opendart.fss.or.kr/api/document.xml"

_REPORT_KEYWORDS = ("운용보고", "운용 보고", "집합투자", "투자설명", "결산", "보고서")


def _api_key() -> str:
    return os.environ.get("OPENDART_API_KEY", "").strip()


def _search_window(bas_dt: str, *, months_back: int = 6) -> tuple[str, str]:
    raw = (bas_dt or "").replace("-", "")[:8]
    if len(raw) == 8 and raw.isdigit():
        end = datetime.strptime(raw, "%Y%m%d").replace(tzinfo=timezone.utc)
    else:
        end = datetime.now(timezone.utc)
    start = end - timedelta(days=31 * months_back)
    return start.strftime("%Y%m%d"), end.strftime("%Y%m%d")


def _fund_name_tokens(fnd_nm: str) -> list[str]:
    nm = fnd_nm.replace(" ", "")
    tokens = [nm[:12], nm[:8]] if nm else []
    if len(nm) > 15:
        tokens.append(nm[:15])
    return [t for t in tokens if len(t) >= 4]


def search_fund_disclosure_rcept_no(
    *,
    fnd_nm: str,
    bas_dt: str = "",
    corp_code: str = "",
    page_count: int = 100,
) -> str:
    key = _api_key()
    if not key:
        return ""
    bgn, end = _search_window(bas_dt)
    tokens = _fund_name_tokens(fnd_nm)
    best = ""
    best_dt = ""
    for page in range(1, 6):
        params: dict[str, str | int] = {
            "crtfc_key": key,
            "bgn_de": bgn,
            "end_de": end,
            "pblntf_ty": "G",
            "page_no": page,
            "page_count": page_count,
        }
        if corp_code:
            params["corp_code"] = corp_code
        try:
            resp = requests.get(DART_LIST_URL, params=params, timeout=30)
            resp.raise_for_status()
            data = resp.json()
        except Exception:
            break
        if str(data.get("status")) != "000":
            break
        for item in data.get("list") or []:
            report_nm = str(item.get("report_nm") or "")
            rcept_dt = str(item.get("rcept_dt") or "")
            if not any(k in report_nm for k in _REPORT_KEYWORDS):
                continue
            if tokens and not any(t in report_nm.replace(" ", "") for t in tokens):
                if fnd_nm and fnd_nm[:6] not in report_nm:
                    continue
            if rcept_dt >= best_dt:
                best_dt = rcept_dt
                best = str(item.get("rcept_no") or "")
        if page >= int(data.get("total_page") or 1):
            break
    return best


def download_disclosure_text(rcept_no: str) -> str:
    key = _api_key()
    if not key or not rcept_no:
        return ""
    try:
        resp = requests.get(
            DART_DOCUMENT_URL,
            params={"crtfc_key": key, "rcept_no": rcept_no},
            timeout=60,
        )
        resp.raise_for_status()
    except Exception:
        return ""

    content = resp.content
    if content[:2] == b"PK":
        texts: list[str] = []
        try:
            with zipfile.ZipFile(io.BytesIO(content)) as zf:
                for name in zf.namelist():
                    if not name.lower().endswith((".htm", ".html", ".xml")):
                        continue
                    texts.append(zf.read(name).decode("utf-8", errors="replace"))
        except Exception:
            return ""
        return "\n".join(texts)
    return content.decode("utf-8", errors="replace")


def fetch_holdings_dart(
    *,
    fnd_nm: str,
    srtn_cd: str = "",
    bas_dt: str = "",
    corp_code: str = "",
    use_gemini: bool = False,
) -> tuple[list[dict[str, Any]], str]:
    """Return (holdings, status). status: dart | unavailable."""
    rcept_no = search_fund_disclosure_rcept_no(
        fnd_nm=fnd_nm,
        bas_dt=bas_dt,
        corp_code=corp_code,
    )
    if not rcept_no:
        return [], "unavailable"

    text = download_disclosure_text(rcept_no)
    if not text:
        return [], "unavailable"

    holdings = parse_holdings_html(text, source=f"dart:{rcept_no}")
    if not holdings and use_gemini:
        from gemini_extract import extract_holdings_from_report_text

        holdings = extract_holdings_from_report_text(
            text,
            srtn_cd=srtn_cd,
            bas_dt=bas_dt,
            source="dart:gemini",
        )
    return (holdings, "dart") if holdings else ([], "unavailable")
