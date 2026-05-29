"""Disclosed fund holdings: ProFrame SO + fallback chain (Gemini → DART → funddoctor)."""

from __future__ import annotations

import time
from io import BytesIO
from typing import Any
from xml.etree import ElementTree as ET

import requests

from dis_client import DisProframeClient
from holdings_parse import rows_to_holdings

try:
    import pdfplumber
except ImportError:
    pdfplumber = None  # type: ignore

try:
    from bs4 import BeautifulSoup
except ImportError:
    BeautifulSoup = None  # type: ignore


def _parse_list_nodes(root: ET.Element) -> list[dict[str, str]]:
    rows: list[dict[str, str]] = []
    for el in root.iter():
        if el.tag.split("}")[-1] != "list":
            continue
        row = {
            c.tag.split("}")[-1]: (c.text or "").strip()
            for c in el
            if (c.text or "").strip()
        }
        if row:
            rows.append(row)
    return rows


def _period_fields(period: dict[str, str], bs: dict[str, str]) -> dict[str, str]:
    return {
        "standardDt": period.get("standardDt") or bs.get("standardDt") or "",
        "standardCd": period.get("standardCd") or bs.get("standardCd") or "",
        "txCd": period.get("txCd") or bs.get("txCd") or "2RF0100",
        "txVsn": period.get("txVsn") or bs.get("txVsn") or "1",
        "companyCd": period.get("companyCd") or bs.get("companyCd") or "",
    }


def fetch_holdings_so(
    client: DisProframeClient,
    *,
    period: dict[str, str],
    bs: dict[str, str],
    srtn_cd: str,
) -> tuple[list[dict[str, Any]], str]:
    fields = _period_fields(period, bs)
    if not fields["standardDt"] or not srtn_cd:
        return [], "unavailable"

    probes = [
        ("FS-DIS", "DISStandValInqSO", "inquiryStandVal", "DISStandValDTO"),
        ("FS-DIS", "DISTradeInqSO", "inquiryTrade", "DISTradeDTO"),
        ("FS-DIS", "DISmetaRowDynm10SO", "select", "DISmetaRowInputListDTO"),
    ]
    for app, svc, fn, dto in probes:
        try:
            root = client.call(app, svc, fn, dto, {**fields, "standardCd": srtn_cd})
            code = root.find(".//{*}pfmResponseCode")
            if code is not None and code.text and code.text not in ("", "0"):
                continue
            holdings = rows_to_holdings(
                _parse_list_nodes(root),
                source=f"dis_proframe:{svc}",
            )
            if holdings:
                return holdings, "so"
        except Exception:
            continue
        time.sleep(0.5)
    return [], "unavailable"


# Back-compat aliases
fetch_top10_so = fetch_holdings_so


def _download_report_text(url: str, timeout: int = 45) -> str:
    if not url.startswith("http"):
        return ""
    resp = requests.get(
        url,
        timeout=timeout,
        headers={"User-Agent": "Mozilla/5.0 (compatible; KofiaDisBot/1.0)"},
    )
    resp.raise_for_status()
    ctype = (resp.headers.get("Content-Type") or "").lower()
    if "pdf" in ctype or url.lower().endswith(".pdf"):
        if not pdfplumber:
            return ""
        with pdfplumber.open(BytesIO(resp.content)) as pdf:
            return "\n".join((p.extract_text() or "") for p in pdf.pages[:30])
    if BeautifulSoup:
        return BeautifulSoup(resp.text, "lxml").get_text("\n", strip=True)
    return resp.text[:80000]


def fetch_holdings_gemini(
    *,
    report_text: str,
    srtn_cd: str,
    bas_dt: str,
) -> tuple[list[dict[str, Any]], str]:
    from gemini_extract import extract_holdings_from_report_text

    rows = extract_holdings_from_report_text(
        report_text,
        srtn_cd=srtn_cd,
        bas_dt=bas_dt,
        source="kofia:gemini",
    )
    return (rows, "gemini") if rows else ([], "unavailable")


fetch_top10_gemini = fetch_holdings_gemini


def resolve_report_text_from_ann(
    client: DisProframeClient,
    *,
    srtn_cd: str,
    standard_dt: str,
) -> str:
    try:
        root = client.call(
            "FS-DIS2",
            "DISFTimeAnnSO",
            "select",
            "DISFTimeAnnInsDTO",
            {"standardCd": srtn_cd, "standardDt": standard_dt, "uFundNm": ""},
        )
    except Exception:
        return ""

    url = ""
    for el in root.iter():
        tag = el.tag.split("}")[-1].lower()
        if tag in ("atchfileurl", "docurl", "fileurl", "pdfurl") and el.text:
            url = el.text.strip()
            break
        if "url" in tag and el.text and "dis.kofia" in el.text:
            url = el.text.strip()
            break

    if not url:
        return ""
    try:
        return _download_report_text(url)
    except Exception:
        return ""


def resolve_holdings(
    client: DisProframeClient,
    *,
    period: dict[str, str],
    bs: dict[str, str],
    srtn_cd: str,
    fnd_nm: str,
    fund: dict[str, Any],
    use_gemini: bool = False,
    use_dart: bool = False,
    use_funddoctor: bool = False,
) -> tuple[list[dict[str, Any]], str, str]:
    """
    Fallback: KOFIA SO → KOFIA report+Gemini → DART → funddoctor.
    Returns (holdings, status, source_label).
    """
    holdings, status = fetch_holdings_so(
        client,
        period=period,
        bs=bs,
        srtn_cd=srtn_cd,
    )
    if holdings:
        src = holdings[0].get("source", "dis_proframe")
        return holdings, status, src

    bas_dt = period.get("standardDt", "")

    if use_gemini:
        report_text = resolve_report_text_from_ann(
            client,
            srtn_cd=srtn_cd,
            standard_dt=bas_dt,
        )
        if report_text:
            holdings, status = fetch_holdings_gemini(
                report_text=report_text,
                srtn_cd=srtn_cd,
                bas_dt=bas_dt,
            )
            if holdings:
                return holdings, status, "kofia:gemini"

    if use_dart:
        from dart_holdings import fetch_holdings_dart

        holdings, status = fetch_holdings_dart(
            fnd_nm=fnd_nm,
            srtn_cd=srtn_cd,
            bas_dt=bas_dt,
            corp_code=str(fund.get("dart_corp_code") or ""),
            use_gemini=use_gemini,
        )
        if holdings:
            src = holdings[0].get("source", "dart")
            return holdings, status, src

    if use_funddoctor:
        from funddoctor_holdings import fetch_holdings_funddoctor

        fd = fund.get("funddoctor") or {}
        if isinstance(fd, dict):
            memb_cd = str(fd.get("memb_cd") or "")
            pfund_cd = str(fd.get("pfund_cd") or "")
        else:
            memb_cd = pfund_cd = ""
        holdings, status = fetch_holdings_funddoctor(
            memb_cd=memb_cd,
            pfund_cd=pfund_cd,
            use_gemini=use_gemini,
            srtn_cd=srtn_cd,
            bas_dt=bas_dt,
        )
        if holdings:
            src = holdings[0].get("source", "funddoctor")
            return holdings, status, src

    return [], "unavailable", ""
