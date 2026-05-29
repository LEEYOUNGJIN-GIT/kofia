"""Parse fund standard-price history from DISFundStdPriceSO grid rows."""

from __future__ import annotations

import time
from calendar import monthrange
from datetime import datetime, timezone
from typing import Any


def month_end_dates_back(anchor_yyyymmdd: str, months: int) -> list[str]:
    """tmpV30 values for DISFundStdPriceSO (month-end per month, newest first)."""
    raw = (anchor_yyyymmdd or "").replace("-", "")[:8]
    if len(raw) != 8 or not raw.isdigit():
        raw = datetime.now(timezone.utc).strftime("%Y%m%d")
    y, m = int(raw[:4]), int(raw[4:6])
    out: list[str] = []
    for _ in range(max(1, months)):
        last = monthrange(y, m)[1]
        out.append(f"{y:04d}{m:02d}{last:02d}")
        m -= 1
        if m < 1:
            y, m = y - 1, 12
    return out


def months_for_max_days(max_days: int) -> int:
    return min(36, max(1, (max_days + 29) // 30))


def fetch_price_trend(
    client: Any,
    search_query: str,
    srtn_cd: str,
    *,
    anchor_standard_dt: str,
    alias: str = "",
    max_days: int = 365,
    delay_sec: float = 0.8,
    grid_cache: dict[tuple[str, str], list[dict[str, str]]] | None = None,
) -> list[dict[str, Any]]:
    """
    DISFundStdPriceSO requires tmpV30 (bas_dt); empty tmpV30 returns no rows.
    Fetches month-end snapshots back from anchor_standard_dt and merges history.
    """
    cache = grid_cache if grid_cache is not None else {}
    n_months = months_for_max_days(max_days)
    dates = month_end_dates_back(anchor_standard_dt, n_months)
    merged_rows: list[dict[str, str]] = []
    for bas_dt in dates:
        key = (search_query, bas_dt)
        if key not in cache:
            time.sleep(delay_sec)
            cache[key] = client.fetch_std_price_grid(search_query, bas_dt=bas_dt)
        merged_rows.extend(cache[key])
    return price_history_from_grid(
        merged_rows,
        srtn_cd=srtn_cd,
        alias=alias,
        max_days=max_days,
    )


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
