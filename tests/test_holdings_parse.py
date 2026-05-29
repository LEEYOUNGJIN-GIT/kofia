"""Tests for variable-length holdings parsing."""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from holdings_parse import parse_holdings_html, rows_to_holdings


def test_rows_to_holdings_not_capped_at_10():
    rows = [
        {"name": f"종목{i}", "weight_pct": str(20 - i)}
        for i in range(15)
    ]
    out = rows_to_holdings(rows, source="test")
    assert len(out) == 15
    assert out[0]["name"] == "종목0"


def test_parse_holdings_html_table():
    html = """
    <html><body>
    <p>주요 자산 보유 현황</p>
    <table>
      <tr><th>종목명</th><th>비중</th><th>비고</th></tr>
      <tr><td>삼성전자</td><td>8.5</td><td></td></tr>
      <tr><td>SK하이닉스</td><td>7.2</td><td>5%초과</td></tr>
      <tr><td>현금</td><td>1.1</td><td></td></tr>
    </table>
    </body></html>
    """
    out = parse_holdings_html(html, source="test:html")
    assert len(out) == 3
    assert out[0]["weight_pct"] == "8.5"
    assert any(r.get("note") for r in out)
