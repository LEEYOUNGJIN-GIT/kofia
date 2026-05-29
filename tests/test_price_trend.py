"""Tests for std-price history parsing."""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from dis_std_price import price_history_from_grid, std_price_csv_rows


def test_price_history_from_grid():
    grid = [
        {"tmpV12": "K55301D51271", "tmpV14": "20250528", "tmpV6": "1400.00", "tmpV7": "0.5"},
        {"tmpV12": "K55301D51271", "tmpV14": "20250428", "tmpV6": "1390.00", "tmpV7": "0.2"},
        {"tmpV12": "OTHER", "tmpV14": "20250528", "tmpV6": "999"},
    ]
    hist = price_history_from_grid(grid, srtn_cd="K55301D51271", alias="TDF2050_Ce", max_days=10)
    assert len(hist) == 2
    assert hist[0]["bas_dt"] == "2025-05-28"
    csv_rows = std_price_csv_rows(hist)
    assert csv_rows[0]["srtn_cd"] == "K55301D51271"
    assert csv_rows[0]["std_price"] == "1400.00"
