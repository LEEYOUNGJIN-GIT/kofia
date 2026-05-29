"""Tests for holdings markdown → YAML sync."""

from __future__ import annotations

from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from fund_list_sync import merge_funds, parse_holdings_table

SAMPLE = """
## 일반펀드 (2)

| # | 펀드명 | 유형(추정) | srtn_cd | alias | enabled |
|---|--------|------------|---------|-------|---------|
| 1 | 펀드A | 주식 | K11111111111 | FundA | true |
| 2 | 펀드B | 채권 | | | false |
"""


def test_parse_holdings_table():
    rows = parse_holdings_table(SAMPLE)
    assert len(rows) == 2
    assert rows[0]["fnd_nm"] == "펀드A"
    assert rows[0]["enabled"] is True
    assert rows[1]["enabled"] is False


def test_merge_preserves_srtn_cd():
    from fund_list_sync import _normalize_name

    parsed = parse_holdings_table(SAMPLE)
    existing = {
        _normalize_name("펀드B"): {"fnd_nm": "펀드B", "srtn_cd": "K22222222222", "alias": "FundB"},
    }
    active, retired = merge_funds(parsed, existing)

    b = next(f for f in active if f["fnd_nm"] == "펀드B")
    assert b["srtn_cd"] == "K22222222222"
    assert b["enabled"] is False
