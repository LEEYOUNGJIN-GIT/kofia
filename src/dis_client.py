"""KOFIA dis.kofia ProFrame HTTP client (Playwright 없음)."""

from __future__ import annotations

import time
import xml.etree.ElementTree as ET
from typing import Any

import requests

PROFRAME_URL = "https://dis.kofia.or.kr/proframeWeb/XMLSERVICES/"
DEFAULT_HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
    ),
    "Accept-Language": "ko-KR,ko;q=0.9,en;q=0.8",
    "Referer": "https://dis.kofia.or.kr/",
    "Content-Type": "text/xml; charset=UTF-8",
}


def _escape_xml(value: str) -> str:
    return (
        value.replace("&", "&amp;")
        .replace("<", "&lt;")
        .replace(">", "&gt;")
        .replace('"', "&quot;")
    )


def build_proframe_message(
    app_name: str,
    svc_name: str,
    fn_name: str,
    dto_name: str,
    fields: dict[str, str],
) -> str:
    """Build ProFrame XML message (callProframe.js setProframeMsgXml compatible)."""
    lines = [
        '<?xml version="1.0" encoding="utf-8"?>',
        "<message>",
        "  <proframeHeader>",
        f"    <pfmAppName>{_escape_xml(app_name)}</pfmAppName>",
        f"    <pfmSvcName>{_escape_xml(svc_name)}</pfmSvcName>",
        f"    <pfmFnName>{_escape_xml(fn_name)}</pfmFnName>",
        "  </proframeHeader>",
        "  <systemHeader></systemHeader>",
        f"  <{dto_name}>",
    ]
    for key, value in fields.items():
        lines.append(f"    <{key}>{_escape_xml(str(value))}</{key}>")
    lines.extend([f"  </{dto_name}>", "</message>"])
    return "\n".join(lines)


class DisProframeClient:
    def __init__(self, session: requests.Session | None = None, timeout: int = 30):
        self.session = session or requests.Session()
        self.timeout = timeout

    def call(
        self,
        app_name: str,
        svc_name: str,
        fn_name: str,
        dto_name: str,
        fields: dict[str, str],
        *,
        retries: int = 3,
    ) -> ET.Element:
        body = build_proframe_message(app_name, svc_name, fn_name, dto_name, fields)
        last_err: Exception | None = None
        for attempt in range(retries):
            resp = self.session.post(
                PROFRAME_URL,
                data=body.encode("utf-8"),
                headers=DEFAULT_HEADERS,
                timeout=self.timeout,
            )
            resp.raise_for_status()
            text = resp.text
            if "firewall" in text.lower() or "blocked" in text.lower():
                last_err = RuntimeError("WAF blocked response from dis.kofia")
            elif "오류가 발생" in text or (
                "<title>" in text[:500] and "message" not in text[:800]
            ):
                last_err = RuntimeError(f"Unexpected HTML response (len={len(text)})")
            elif len(text) < 2000 and (
                "MODULE ERROR" in text or "COMS9009" in text or "COMS9002" in text
            ):
                last_err = RuntimeError(f"ProFrame error response (len={len(text)})")
            else:
                return ET.fromstring(resp.content)
            if attempt < retries - 1:
                time.sleep(1.5 * (attempt + 1))
        raise last_err or RuntimeError("ProFrame call failed")

    def fetch_std_price_grid(
        self,
        search_keyword: str,
        *,
        bas_dt: str = "",
    ) -> list[dict[str, str]]:
        """DISFundStdPriceSO — 펀드 기준가 목록 (selectMeta rows). tmpV30 required."""
        from dis_grid import parse_select_meta_rows
        from dis_std_price import month_end_dates_back

        bas = bas_dt.replace("-", "") if bas_dt else ""
        if not bas:
            bas = month_end_dates_back("", 1)[0]

        root = self.call(
            "FS-DIS2",
            "DISFundStdPriceSO",
            "select",
            "DISCondFuncDTO",
            {
                "tmpV30": bas,
                "tmpV12": search_keyword,
                "tmpV3": "",
                "tmpV4": "",
                "tmpV5": "",
                "tmpV7": "",
                "tmpV11": "",
                "tmpV50": "",
                "tmpV51": "",
            },
        )
        return parse_select_meta_rows(root)

    def search_funds_by_name(
        self,
        fund_name: str,
        manage_stt: str = "2",
        search_gb: str = "1",
    ) -> list[dict[str, str]]:
        """
        DISComFundSrchSO.search — 펀드명 검색.
        manage_stt: 2=운용중 (site default for radioGb)
        uTotCnt: 1=펀드명, 2=단축코드
        """
        root = self.call(
            "FS-DIS2",
            "DISComFundSrchSO",
            "search",
            "DISComFundSrchListDTO",
            {
                "uFundNm": fund_name,
                "manageCompCd": "",
                "manageStt": manage_stt,
                "uTotCnt": search_gb,
            },
        )
        return _parse_fund_search_rows(root)


def _parse_fund_search_rows(root: ET.Element) -> list[dict[str, str]]:
    rows: list[dict[str, str]] = []
    for list_node in root.iter():
        tag = list_node.tag.split("}")[-1]
        if tag != "list":
            continue
        row: dict[str, str] = {}
        for child in list_node:
            key = child.tag.split("}")[-1]
            if child.text and child.text.strip():
                row[key] = child.text.strip()
        if row:
            rows.append(row)
    return rows


def pick_fund_row(
    rows: list[dict[str, str]],
    fnd_nm: str,
    *,
    srtn_cd_hint: str | None = None,
    alias: str | None = None,
) -> dict[str, str] | None:
    """Pick best match: config srtn_cd > exact name > alias tokens > first row."""
    if not rows:
        return None
    if srtn_cd_hint and not alias:
        for row in rows:
            if row.get("standardCd") == srtn_cd_hint:
                return row
    target = _normalize_name(fnd_nm)
    exact = [r for r in rows if _normalize_name(r.get("koreanFundNm", "")) == target]
    if exact:
        return exact[0]
    partial = [r for r in rows if target and target in _normalize_name(r.get("koreanFundNm", ""))]
    if partial:
        return partial[0]
    if alias:
        tokens = _alias_search_tokens(alias, fnd_nm)
        scored = []
        for row in rows:
            nm = _normalize_name(row.get("koreanFundNm", ""))
            score = sum(1 for t in tokens if t in nm)
            if score:
                scored.append((score, row))
        if scored:
            scored.sort(key=lambda x: -x[0])
            return scored[0][1]
    return rows[0]


def _alias_search_tokens(alias: str, fnd_nm: str) -> list[str]:
    tokens = []
    if "tdf" in alias.lower() or "tdf" in fnd_nm.lower():
        tokens.append("tdf2050")
    if "ce" in alias.lower():
        tokens.extend(["classc-e", "c-e", "ce"])
    if "미래" in fnd_nm:
        tokens.append("미래에셋")
    return tokens


def search_query_for_fund(fnd_nm: str, alias: str | None = None) -> str:
    """ProFrame search keyword — full name often returns 0 rows; use short token."""
    alias_l = (alias or "").lower()
    if alias_l == "tdf2050_ce" or "tdf2050" in alias_l:
        return "TDF2050"
    if "TDF" in fnd_nm.upper() or (alias and "TDF" in alias.upper()):
        if "미래" in fnd_nm or "미래에셋" in fnd_nm:
            return "미래에셋 TDF2050"
        return "TDF2050"
    return fnd_nm[:30] if len(fnd_nm) > 30 else fnd_nm


def _normalize_name(name: str) -> str:
    return "".join(name.split()).lower().replace("-", "").replace("_", "")
