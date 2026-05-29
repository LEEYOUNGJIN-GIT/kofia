"""Holdings top10 via ProFrame SO and optional HTTP report + Gemini."""

from __future__ import annotations

import time
from io import BytesIO
from typing import Any
from xml.etree import ElementTree as ET

import requests

from dis_client import DisProframeClient

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


def _rows_to_top10(rows: list[dict[str, str]], *, source: str) -> list[dict[str, Any]]:
    name_keys = ("scrNm", "koreanScrNm", "itemNm", "fundNm", "bondNm", "name", "holdNm")
    weight_keys = ("weight", "weightPct", "holdRate", "rate", "ratio", "wt", "val2", "val1")
    code_keys = ("scrCd", "standardCd", "isin", "itemCd")

    candidates: list[tuple[float, dict[str, Any]]] = []
    for row in rows:
        name = next((row[k] for k in name_keys if row.get(k)), "")
        if not name or len(name) < 2:
            continue
        w_raw = next((row[k] for k in weight_keys if row.get(k)), "")
        try:
            w = float(str(w_raw).replace("%", "").replace(",", ""))
        except ValueError:
            w = 0.0
        code = next((row[k] for k in code_keys if row.get(k)), "")
        candidates.append((w, {"name": name, "weight_pct": w_raw or str(w), "code": code}))

    candidates.sort(key=lambda x: -x[0])
    out: list[dict[str, Any]] = []
    for rank, (_, item) in enumerate(candidates[:10], start=1):
        out.append(
            {
                "rank": str(rank),
                "name": item["name"],
                "weight_pct": item["weight_pct"],
                "code": item.get("code", ""),
                "source": source,
            }
        )
    return out


def _period_fields(period: dict[str, str], bs: dict[str, str]) -> dict[str, str]:
    return {
        "standardDt": period.get("standardDt") or bs.get("standardDt") or "",
        "standardCd": period.get("standardCd") or bs.get("standardCd") or "",
        "txCd": period.get("txCd") or bs.get("txCd") or "2RF0100",
        "txVsn": period.get("txVsn") or bs.get("txVsn") or "1",
        "companyCd": period.get("companyCd") or bs.get("companyCd") or "",
    }


def fetch_top10_so(
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
            top10 = _rows_to_top10(_parse_list_nodes(root), source=f"dis_proframe:{svc}")
            if top10:
                return top10, "so"
        except Exception:
            continue
        time.sleep(0.5)
    return [], "unavailable"


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


def fetch_top10_gemini(
    *,
    report_text: str,
    srtn_cd: str,
    bas_dt: str,
) -> tuple[list[dict[str, Any]], str]:
    from gemini_extract import extract_top10_from_report_text

    rows = extract_top10_from_report_text(report_text, srtn_cd=srtn_cd, bas_dt=bas_dt)
    return (rows, "gemini") if rows else ([], "unavailable")


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
