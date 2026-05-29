"""Parse fund standard-price history from DISFundStdPriceSO grid rows."""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any


def _format_bas_dt(raw: str) -> str:
    raw = (raw or "").strip()
    if len(raw) == 8 and raw.isdigit():
        return f"{raw[:4]}-{raw[4:6]}-{raw[6:8]}"
    return raw


def price_history_from_grid(
    grid_rows: list[dict[str, str]],
    *,
    srtn_cd: str,
    alias: str = "",
    max_days: int | None = 365,
) -> list[dict[str, Any]]:
    """All selectMeta rows for one fund (tmpV12 = srtn_cd)."""
    out: list[dict[str, Any]] = []
    fetched_at = datetime.now(timezone.utc).isoformat()

    for row in grid_rows:
        if row.get("tmpV12") != srtn_cd:
            continue
        bas_dt = _format_bas_dt(row.get("tmpV14") or row.get("tmpV4") or "")
        std_price = row.get("tmpV6") or ""
        if not bas_dt and not std_price:
            continue
        out.append(
            {
                "bas_dt": bas_dt,
                "std_price": std_price,
                "chg_pct": row.get("tmpV7") or "",
                "setup_dt": _format_bas_dt(row.get("tmpV4") or ""),
                "company_nm": row.get("tmpV1") or "",
                "korean_fund_nm": row.get("tmpV2") or "",
            }
        )

    out.sort(key=lambda x: x.get("bas_dt") or "", reverse=True)
    if max_days and len(out) > max_days:
        out = out[:max_days]

    for row in out:
        row["srtn_cd"] = srtn_cd
        row["alias"] = alias
        row["fetched_at"] = fetched_at

    return out


def std_price_csv_rows(price_trend: list[dict[str, Any]]) -> list[dict[str, str]]:
    rows: list[dict[str, str]] = []
    for pt in price_trend:
        rows.append(
            {
                "srtn_cd": str(pt.get("srtn_cd", "")),
                "alias": str(pt.get("alias", "")),
                "bas_dt": str(pt.get("bas_dt", "")),
                "std_price": str(pt.get("std_price", "")),
                "setup_dt": str(pt.get("setup_dt", "")),
                "company_nm": str(pt.get("company_nm", "")),
                "korean_fund_nm": str(pt.get("korean_fund_nm", "")),
                "fetched_at": str(pt.get("fetched_at", "")),
            }
        )
    return rows
