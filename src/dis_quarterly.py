"""Quarterly / settlement allocation from dis ProFrame BS (+ optional PDF)."""

from __future__ import annotations

from pathlib import Path
from typing import Any

import yaml

from dis_client import DisProframeClient
from dis_reports import fetch_balance_sheet

ROOT = Path(__file__).resolve().parents[1]
ASSET_MAP_PATH = ROOT / "config" / "asset_class_map.yaml"


def load_asset_class_map(path: Path = ASSET_MAP_PATH) -> tuple[dict[str, str], dict[str, str]]:
    if not path.exists():
        return {}, {}
    data = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
    return data.get("fields") or {}, data.get("labels") or {}


def allocation_from_bs(
    bs: dict[str, str],
    *,
    srtn_cd: str,
    alias: str,
    field_map: dict[str, str] | None = None,
    report_type: str = "quarterly_bs",
) -> list[dict[str, Any]]:
    """Map balance-sheet line amounts to canonical asset_class rows."""
    fmap, _ = load_asset_class_map()
    if field_map:
        fmap = {**fmap, **field_map}

    total_raw = bs.get("assetsTotSum") or "0"
    try:
        total = float(total_raw)
    except ValueError:
        total = 0.0
    if total <= 0:
        return []

    bas_dt = _format_bas_dt(bs.get("standardDt") or "")
    tx_cd = bs.get("txCd") or ""
    source_doc = f"dis_proframe:DISFundSetRptBSSO:{tx_cd}"

    rows: list[dict[str, Any]] = []
    for field, asset_class in fmap.items():
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


def fetch_quarterly_allocation(
    client: DisProframeClient,
    *,
    srtn_cd: str,
    alias: str,
    standard_dt: str,
    tx_cd: str,
    tx_vsn: str = "1",
) -> list[dict[str, Any]]:
    bs = fetch_balance_sheet(
        client,
        srtn_cd=srtn_cd,
        standard_dt=standard_dt,
        tx_cd=tx_cd,
        tx_vsn=tx_vsn,
    )
    return allocation_from_bs(bs, srtn_cd=srtn_cd, alias=alias)


def validate_weight_sum(rows: list[dict[str, Any]], *, low: float = 95.0, high: float = 105.0) -> str | None:
    total = sum(float(r.get("weight_pct") or 0) for r in rows)
    if not rows:
        return "ERROR: no allocation rows"
    if total < low or total > high:
        return f"WARNING: weight_pct sum={total:.2f} not in [{low},{high}]"
    return None


def _format_bas_dt(raw: str) -> str:
    if len(raw) == 8 and raw.isdigit():
        return f"{raw[:4]}-{raw[4:6]}-{raw[6:8]}"
    return raw
