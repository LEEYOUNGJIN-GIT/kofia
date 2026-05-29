"""DART Open API fallback: fund disclosure document → holdings (variable length)."""

from __future__ import annotations

import io
import os
import zipfile
from datetime import datetime, timedelta, timezone
from typing import Any

import requests

from holdings_parse import (
    filter_valid_holdings,
    holdings_look_valid,
    parse_holdings_html,
    report_text_fingerprint,
)

DART_LIST_URL = "https://opendart.fss.or.kr/api/list.json"
DART_DOCUMENT_URL = "https://opendart.fss.or.kr/api/document.xml"

_REPORT_KEYWORDS = (
    "운용보고",
    "운용 보고",
    "집합투자",
    "투자설명",
    "일괄신고",
    "결산",
    "보고서",
    "증권발행",
)


def _api_key() -> str:
    return os.environ.get("OPENDART_API_KEY", "").strip()


def _search_window(_bas_dt: str = "") -> tuple[str, str]:
    """OpenDART list API without corp_code: rolling ~3 calendar months ending today."""
    end = datetime.now(timezone.utc)
    # 89 days keeps within DART's 3-month cap (92+ often returns status 100).
    start = end - timedelta(days=89)
    return start.strftime("%Y%m%d"), end.strftime("%Y%m%d")


def _fund_name_tokens(fnd_nm: str) -> list[str]:
    nm = fnd_nm.replace(" ", "")
    tokens: list[str] = []
    if nm:
        tokens.extend([nm[:15], nm[:12], nm[:8]])
    upper = fnd_nm.upper()
    for tag in ("TDF2050", "TDF2040", "TDF2060", "TDF"):
        if tag in upper:
            tokens.append(tag)
    if "적격" in fnd_nm and "TDF" in upper:
        tokens.append("적격TDF2050")
        tokens.append("전략배분적격")
    if "미래에셋" in fnd_nm:
        tokens.append("미래에셋")
    seen: set[str] = set()
    out: list[str] = []
    for t in tokens:
        if len(t) >= 4 and t not in seen:
            seen.add(t)
            out.append(t)
    return out


def _report_match_score(report_nm: str, fnd_nm: str, tokens: list[str]) -> int:
    rn = report_nm.replace(" ", "")
    if "TDF2050" in fnd_nm.upper() and "TDF2050" not in rn:
        return 0
    if "미래에셋" in fnd_nm and "미래에셋" not in report_nm:
        return 0
    core = "전략배분적격TDF2050"
    if core in fnd_nm.replace("-", "").replace(" ", "") and core not in rn:
        if "적격" in fnd_nm and "적격" not in report_nm:
            return 0
    score = sum(len(t) for t in tokens if t in rn)
    if core in rn:
        score += 80
    if "운용보고" in report_nm:
        score += 40
    if score == 0 and fnd_nm[:8] in report_nm:
        score = 8
    return score


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
    best_score = 0
    for page in range(1, 70):
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
            score = _report_match_score(report_nm, fnd_nm, tokens)
            if score <= 0:
                continue
            if score > best_score or (score == best_score and rcept_dt >= best_dt):
                best_score = score
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
    skip_gemini_if_fingerprint: str | None = None,
) -> tuple[list[dict[str, Any]], str]:
    """Return (holdings, status). Rule parse first; optional Gemini if empty or invalid."""
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

    source = f"dart:{rcept_no}"
    holdings = filter_valid_holdings(parse_holdings_html(text, source=source))

    need_gemini = use_gemini and not holdings
    if need_gemini and skip_gemini_if_fingerprint:
        if report_text_fingerprint(text) == skip_gemini_if_fingerprint:
            need_gemini = False

    if need_gemini:
        from gemini_extract import extract_holdings_from_report_text

        holdings = filter_valid_holdings(
            extract_holdings_from_report_text(
                text,
                srtn_cd=srtn_cd,
                bas_dt=bas_dt,
                source="dart:gemini",
            )
        )
        if holdings:
            return holdings, "dart"

    if holdings and holdings_look_valid(holdings):
        return holdings, "dart"
    return [], "unavailable"
