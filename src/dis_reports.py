"""dis.kofia 결산보고서 기간 조회 (FS-DIS2)."""

from __future__ import annotations

import xml.etree.ElementTree as ET

from dis_client import DisProframeClient


def _parse_bs_inquiry_lists(root: ET.Element) -> list[dict[str, str]]:
    rows: list[dict[str, str]] = []
    for el in root.iter():
        if el.tag.split("}")[-1] != "list":
            continue
        row = {
            c.tag.split("}")[-1]: (c.text or "").strip()
            for c in el
            if (c.text or "").strip()
        }
        if row.get("standardDt"):
            rows.append(row)
    return rows


def inquiry_report_periods(client: DisProframeClient, srtn_cd: str) -> list[dict[str, str]]:
    root = client.call(
        "FS-DIS2",
        "DISBsInq2SO",
        "inquiryBs",
        "DISBsListDTO",
        {"standardCd": srtn_cd},
    )
    return _parse_bs_inquiry_lists(root)


def pick_report_period(
    periods: list[dict[str, str]],
    *,
    bas_dt_hint: str | None = None,
) -> dict[str, str] | None:
    if not periods:
        return None
    if bas_dt_hint:
        eligible = [p for p in periods if p.get("standardDt", "") <= bas_dt_hint.replace("-", "")]
        if eligible:
            return max(eligible, key=lambda p: p["standardDt"])
    return max(periods, key=lambda p: p.get("standardDt", ""))
