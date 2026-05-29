"""dis.kofia 결산보고서 ProFrame (FS-DIS / FS-DIS2) — HTTP only."""

from __future__ import annotations

import xml.etree.ElementTree as ET
from typing import Any

from dis_client import DisProframeClient

# Balance-sheet line items mapped to allocation asset_class (M1 proxy until quarterly PDF parser).
BS_ASSET_FIELDS: list[tuple[str, str]] = [
    ("stock", "equity"),
    ("bond", "bond"),
    ("profitBnd", "profit_bnd"),
    ("depositAmt", "cash"),
    ("bill", "cash"),
    ("callLoan", "cash"),
    ("otherAss", "other"),
]


def _dto_child_text(root: ET.Element, dto_name: str, field: str) -> str:
    for el in root.iter():
        if el.tag.split("}")[-1] == dto_name:
            for child in el:
                if child.tag.split("}")[-1] == field and child.text:
                    return child.text.strip()
    return ""


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


def fetch_balance_sheet(
    client: DisProframeClient,
    *,
    srtn_cd: str,
    standard_dt: str,
    tx_cd: str,
    tx_vsn: str = "1",
) -> dict[str, str]:
    root = client.call(
        "FS-DIS",
        "DISFundSetRptBSSO",
        "selectBS",
        "DISFundSetRptBSDTO",
        {
            "standardDt": standard_dt,
            "standardCd": srtn_cd,
            "txCd": tx_cd,
            "txVsn": tx_vsn,
        },
    )
    out: dict[str, str] = {}
    for el in root.iter():
        if el.tag.split("}")[-1] != "DISFundSetRptBSDTO":
            continue
        for child in el:
            key = child.tag.split("}")[-1]
            if child.text is not None:
                out[key] = child.text.strip()
    return out


def balance_sheet_to_allocation_rows(
    bs: dict[str, str],
    *,
    srtn_cd: str,
    alias: str,
    report_type: str = "settlement_bs",
) -> list[dict[str, Any]]:
    total_raw = bs.get("assetsTotSum") or "0"
    try:
        total = float(total_raw)
    except ValueError:
        total = 0.0
    if total <= 0:
        return []

    bas_dt = bs.get("standardDt") or ""
    if len(bas_dt) == 8:
        bas_dt = f"{bas_dt[:4]}-{bas_dt[4:6]}-{bas_dt[6:8]}"

    tx_cd = bs.get("txCd") or ""
    source_doc = f"dis_proframe:DISFundSetRptBSSO:{tx_cd}"
    rows: list[dict[str, Any]] = []

    for field, asset_class in BS_ASSET_FIELDS:
        raw = bs.get(field) or "0"
        try:
            amount = float(raw)
        except ValueError:
            amount = 0.0
        if amount <= 0:
            continue
        rows.append(
            {
                "srtn_cd": srtn_cd,
                "alias": alias,
                "bas_dt": bas_dt,
                "report_type": report_type,
                "asset_class": asset_class,
                "weight_pct": round(amount / total * 100.0, 4),
                "amount_mkrw": int(amount),
                "source_doc": source_doc,
            }
        )
    return rows
