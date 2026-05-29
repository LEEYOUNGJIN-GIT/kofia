"""Golden tests for allocation / top10 parsers (no network)."""

from __future__ import annotations

import json
from pathlib import Path

import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from dis_quarterly import allocation_from_bs, validate_weight_sum
from dis_top10 import top10_from_bs

FIXTURE = Path(__file__).parent / "fixtures" / "bs_tdf2050_sample.json"


def test_allocation_from_bs_fixture():
    bs = json.loads(FIXTURE.read_text(encoding="utf-8"))
    rows = allocation_from_bs(bs, srtn_cd="K55301D51271", alias="TDF2050_Ce")
    assert len(rows) >= 2
    classes = {r["asset_class"] for r in rows}
    assert "profit_bnd" in classes
    assert validate_weight_sum(rows) is None or "WARNING" in (validate_weight_sum(rows) or "")


def test_top10_from_bs_fixture():
    bs = json.loads(FIXTURE.read_text(encoding="utf-8"))
    rows = top10_from_bs(bs, srtn_cd="K55301D51271", alias="TDF2050_Ce")
    assert len(rows) >= 1
    assert rows[0]["rank"] == "1"
    assert float(rows[0]["weight_pct"]) > 0
