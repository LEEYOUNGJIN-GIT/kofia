"""Parse fund standard-price history from DISFundStdPriceSO grid rows."""

from __future__ import annotations

import time
from calendar import monthrange
from datetime import date, datetime, timedelta, timezone
from typing import Any

from dis_grid import find_row_by_srtn_cd


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


def _parse_price(raw: str) -> float | None:
    try:
        return float(str(raw).replace(",", "").strip())
    except ValueError:
        return None


def _format_chg_pct(pct: float) -> str:
    return f"{pct:.4f}".rstrip("0").rstrip(".")


def apply_chg_pct_from_prices(points: list[dict[str, Any]]) -> None:
    """chg_pct = % change vs next-older point (tmpV7 is prior price on DIS grid, not %)."""
    for i, row in enumerate(points):
        cur = _parse_price(str(row.get("std_price", "")))
        older = _parse_price(str(points[i + 1].get("std_price", ""))) if i + 1 < len(points) else None
        if cur is not None and older is not None and older != 0:
            row["chg_pct"] = _format_chg_pct((cur - older) / older * 100.0)
        else:
            row["chg_pct"] = ""


def price_history_from_grid(
    grid_rows: list[dict[str, str]],
    *,
    srtn_cd: str,
    alias: str = "",
    max_days: int | None = 365,
) -> list[dict[str, Any]]:
    """All selectMeta rows for one fund (tmpV12 = srtn_cd)."""
    by_date: dict[str, dict[str, Any]] = {}
    fetched_at = datetime.now(timezone.utc).isoformat()

    for row in grid_rows:
        if row.get("tmpV12") != srtn_cd:
            continue
        bas_dt = _format_bas_dt(row.get("tmpV14") or row.get("tmpV4") or "")
        std_price = row.get("tmpV6") or ""
        if not bas_dt and not std_price:
            continue
        prior_price = row.get("tmpV7") or ""
        by_date[bas_dt] = {
            "bas_dt": bas_dt,
            "std_price": std_price,
            "prior_std_price": prior_price,
            "setup_dt": _format_bas_dt(row.get("tmpV4") or ""),
            "company_nm": row.get("tmpV1") or "",
            "korean_fund_nm": row.get("tmpV2") or "",
        }

    out = sorted(by_date.values(), key=lambda x: x.get("bas_dt") or "", reverse=True)
    if max_days and len(out) > max_days:
        out = out[:max_days]

    apply_chg_pct_from_prices(out)

    for row in out:
        row["srtn_cd"] = srtn_cd
        row["alias"] = alias
        row["fetched_at"] = fetched_at

    return out


def _parse_iso_date(bas_dt: str) -> date | None:
    raw = (bas_dt or "").strip()
    if len(raw) == 10 and raw[4] == "-":
        try:
            return date(int(raw[:4]), int(raw[5:7]), int(raw[8:10]))
        except ValueError:
            return None
    if len(raw) == 8 and raw.isdigit():
        try:
            return date(int(raw[:4]), int(raw[4:6]), int(raw[6:8]))
        except ValueError:
            return None
    return None


def is_calendar_month_end(bas_dt: str) -> bool:
    d = _parse_iso_date(bas_dt)
    if not d:
        return False
    return d.day == monthrange(d.year, d.month)[1]


def business_days_back(
    from_dt: datetime | None = None,
    *,
    max_calendar_days: int = 15,
) -> list[str]:
    """Recent weekdays (YYYYMMDD), newest first — KOFIA grid uses tmpV30 as as-of date."""
    d = (from_dt or datetime.now(timezone.utc)).date()
    out: list[str] = []
    for _ in range(max_calendar_days):
        if d.weekday() < 5:
            out.append(d.strftime("%Y%m%d"))
        d -= timedelta(days=1)
    return out


def price_snapshot_manifest(
    row: dict[str, Any] | None,
    *,
    kind: str,
    query_dt: str = "",
) -> dict[str, str]:
    if not row:
        return {}
    return {
        "kind": kind,
        "bas_dt": str(row.get("bas_dt", "")),
        "std_price": str(row.get("std_price", "")),
        "query_dt": query_dt,
        "chg_pct": str(row.get("chg_pct", "")),
    }


def month_end_series_from_trend(price_trend: list[dict[str, Any]]) -> list[dict[str, Any]]:
    return [p for p in price_trend if is_calendar_month_end(str(p.get("bas_dt", "")))]


def latest_month_end_snapshot(price_trend: list[dict[str, Any]]) -> dict[str, str]:
    series = month_end_series_from_trend(price_trend)
    if not series:
        return {}
    return price_snapshot_manifest(series[0], kind="month_end")


def grid_row_to_price_point(
    grid_row: dict[str, str],
    *,
    srtn_cd: str,
    alias: str = "",
) -> dict[str, Any]:
    bas_dt_raw = grid_row.get("tmpV14") or grid_row.get("tmpV4") or ""
    points = price_history_from_grid(
        [
            {
                "tmpV12": srtn_cd,
                "tmpV14": bas_dt_raw,
                "tmpV6": grid_row.get("tmpV6", ""),
                "tmpV7": grid_row.get("tmpV7", ""),
                "tmpV4": grid_row.get("tmpV4", ""),
                "tmpV1": grid_row.get("tmpV1", ""),
                "tmpV2": grid_row.get("tmpV2", ""),
            }
        ],
        srtn_cd=srtn_cd,
        alias=alias,
        max_days=1,
    )
    return points[0] if points else {}


def fetch_std_price_as_of(
    client: Any,
    search_query: str,
    srtn_cd: str,
    tmpV30_yyyymmdd: str,
    *,
    grid_cache: dict[tuple[str, str], list[dict[str, str]]],
    alias: str = "",
    delay_sec: float = 0.0,
) -> dict[str, Any]:
    key = (search_query, tmpV30_yyyymmdd)
    if key not in grid_cache:
        if delay_sec:
            time.sleep(delay_sec)
        grid_cache[key] = client.fetch_std_price_grid(search_query, bas_dt=tmpV30_yyyymmdd)
    row = find_row_by_srtn_cd(grid_cache[key], srtn_cd)
    if not row or not row.get("tmpV6"):
        return {}
    return grid_row_to_price_point(row, srtn_cd=srtn_cd, alias=alias)


def fetch_std_price_latest_business(
    client: Any,
    search_query: str,
    srtn_cd: str,
    *,
    grid_cache: dict[tuple[str, str], list[dict[str, str]]],
    alias: str = "",
    delay_sec: float = 0.8,
    from_dt: datetime | None = None,
) -> dict[str, str]:
    """Latest weekday std price near fetch time (tmpV30 = that business day)."""
    for query_dt in business_days_back(from_dt):
        point = fetch_std_price_as_of(
            client,
            search_query,
            srtn_cd,
            query_dt,
            grid_cache=grid_cache,
            alias=alias,
            delay_sec=delay_sec,
        )
        if point:
            return price_snapshot_manifest(point, kind="latest_business", query_dt=query_dt)
    return {}


