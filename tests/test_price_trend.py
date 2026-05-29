"""Tests for std-price history parsing."""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from dis_std_price import (
    apply_chg_pct_from_prices,
    business_days_back,
    is_calendar_month_end,
    month_end_dates_back,
    month_end_series_from_trend,
    months_for_max_days,
    price_history_from_grid,
)


def test_month_end_dates_back():
    dates = month_end_dates_back("20250719", 3)
    assert dates == ["20250731", "20250630", "20250531"]


def test_months_for_max_days():
    assert months_for_max_days(365) == 13
    assert months_for_max_days(60) == 2


def test_price_history_from_grid():
    grid = [
        {"tmpV12": "K55301D51271", "tmpV14": "20250528", "tmpV6": "1400.00", "tmpV7": "0.5"},
        {"tmpV12": "K55301D51271", "tmpV14": "20250428", "tmpV6": "1390.00", "tmpV7": "0.2"},
        {"tmpV12": "OTHER", "tmpV14": "20250528", "tmpV6": "999"},
    ]
    hist = price_history_from_grid(grid, srtn_cd="K55301D51271", alias="TDF2050_Ce", max_days=10)
    assert len(hist) == 2
    assert hist[0]["bas_dt"] == "2025-05-28"
    assert hist[0]["std_price"] == "1400.00"
    assert hist[0]["srtn_cd"] == "K55301D51271"


def test_is_calendar_month_end():
    assert is_calendar_month_end("2025-05-31")
    assert not is_calendar_month_end("2025-05-28")


def test_month_end_series_from_trend():
    trend = [
        {"bas_dt": "2025-05-31", "std_price": "100"},
        {"bas_dt": "2025-05-28", "std_price": "99"},
    ]
    me = month_end_series_from_trend(trend)
    assert len(me) == 1
    assert me[0]["bas_dt"] == "2025-05-31"


def test_business_days_back_skips_weekend():
    ref = __import__("datetime").datetime(2025, 5, 29, tzinfo=__import__("datetime").timezone.utc)
    days = business_days_back(ref, max_calendar_days=5)
    assert days[0] == "20250529"
    assert all(len(d) == 8 for d in days)


def test_chg_pct_from_price_series_not_tmpv7():
    grid = [
        {"tmpV12": "K55301D51271", "tmpV14": "20250531", "tmpV6": "1100.00", "tmpV7": "9999"},
        {"tmpV12": "K55301D51271", "tmpV14": "20250430", "tmpV6": "1000.00", "tmpV7": "8888"},
    ]
    hist = price_history_from_grid(grid, srtn_cd="K55301D51271", max_days=10)
    assert hist[0]["chg_pct"] == "10"
    assert hist[0].get("prior_std_price") == "9999"
    assert hist[1]["chg_pct"] == ""


def test_apply_chg_pct_empty_for_single_point():
    points = [{"bas_dt": "2025-05-31", "std_price": "1000"}]
    apply_chg_pct_from_prices(points)
    assert points[0]["chg_pct"] == ""
