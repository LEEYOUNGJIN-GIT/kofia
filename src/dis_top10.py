"""Top holdings proxy from BS line items (until quarterly PDF parser)."""

from __future__ import annotations

from typing import Any

from dis_quarterly import load_asset_class_map


def top10_bs_from_bs(
    bs: dict[str, str],
    *,
    srtn_cd: str,
    alias: str,
    report_type: str = "settlement_bs_top10_proxy",
) -> list[dict[str, Any]]:
    """Alias for BS account-line top10."""
    return top10_from_bs(bs, srtn_cd=srtn_cd, alias=alias, report_type=report_type)


def top10_from_bs(
    bs: dict[str, str],
    *,
    srtn_cd: str,
    alias: str,
    report_type: str = "settlement_bs_top10_proxy",
) -> list[dict[str, Any]]:
    """
    Rank non-zero BS asset-side accounts by amount (proxy for 보유 top10).
    Not individual securities — BS account lines only (proxy).
    """
    _, labels = load_asset_class_map()
    bas_dt = bs.get("standardDt") or ""
    if len(bas_dt) == 8:
        bas_dt = f"{bas_dt[:4]}-{bas_dt[4:6]}-{bas_dt[6:8]}"

    total_raw = bs.get("assetsTotSum") or "0"
    try:
        total = float(total_raw)
    except ValueError:
        total = 0.0
    if total <= 0:
        return []

    candidates: list[tuple[float, str, str]] = []
    skip = {"assetsTotSum", "debtTotSum", "standardDt", "standardCd", "txCd", "txVsn", "companyCd"}
    for key, raw in bs.items():
        if key in skip or key.endswith("TotSum"):
            continue
        try:
            amount = float(raw or "0")
        except ValueError:
            continue
        if amount <= 0:
            continue
        name = labels.get(key, key)
        candidates.append((amount, name, key))

    candidates.sort(key=lambda x: -x[0])
    rows: list[dict[str, Any]] = []
    for rank, (amount, name, key) in enumerate(candidates[:10], start=1):
        rows.append(
            {
                "srtn_cd": srtn_cd,
                "alias": alias,
                "bas_dt": bas_dt,
                "rank": str(rank),
                "name": name,
                "asset_type": key,
                "weight_pct": str(round(amount / total * 100.0, 4)),
                "source_doc": f"dis_proframe:DISFundSetRptBSSO:top10_proxy",
            }
        )
    return rows
