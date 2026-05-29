"""PDF/HTML table extraction for dis quarterly reports."""

from __future__ import annotations

import io
import re
from typing import Any

try:
    import pdfplumber
except ImportError:  # pragma: no cover
    pdfplumber = None  # type: ignore


def parse_allocation_tables_from_pdf(
    pdf_bytes: bytes,
    *,
    asset_keywords: tuple[str, ...] = ("주식", "채권", "현금", "수익증권", "합계", "자산"),
) -> list[dict[str, Any]]:
    """Extract rows that look like asset-allocation tables from PDF bytes."""
    if not pdfplumber:
        return []
    rows: list[dict[str, Any]] = []
    with pdfplumber.open(io.BytesIO(pdf_bytes)) as pdf:
        for page in pdf.pages:
            for table in page.extract_tables() or []:
                if not table or len(table) < 2:
                    continue
                header = " ".join(str(c or "") for c in table[0])
                if not any(kw in header for kw in asset_keywords):
                    continue
                for line in table[1:]:
                    if not line or len(line) < 2:
                        continue
                    name = str(line[0] or "").strip()
                    if not name or "합계" in name:
                        continue
                    pct = _parse_pct(line[-1] if len(line) > 1 else "")
                    if pct is None:
                        continue
                    rows.append({"asset_class": name, "weight_pct": pct})
    return rows


def parse_top10_tables_from_pdf(pdf_bytes: bytes) -> list[dict[str, Any]]:
    """Extract top-holdings style tables (종목명 + 비중)."""
    if not pdfplumber:
        return []
    rows: list[dict[str, Any]] = []
    with pdfplumber.open(io.BytesIO(pdf_bytes)) as pdf:
        for page in pdf.pages:
            for table in page.extract_tables() or []:
                if not table or len(table) < 2:
                    continue
                header = " ".join(str(c or "") for c in table[0])
                if not any(k in header for k in ("종목", "발행", "보유", "명칭")):
                    continue
                rank = 0
                for line in table[1:]:
                    if not line or len(line) < 2:
                        continue
                    name = str(line[0] or "").strip()
                    if not name or "합계" in name:
                        continue
                    pct = _parse_pct(line[-1] if len(line) > 1 else "")
                    if pct is None:
                        continue
                    rank += 1
                    rows.append(
                        {
                            "rank": str(rank),
                            "name": name,
                            "weight_pct": pct,
                            "asset_type": "unknown",
                        }
                    )
                    if rank >= 10:
                        break
    return rows


def _parse_pct(cell: Any) -> float | None:
    text = str(cell or "").strip().replace(",", "")
    m = re.search(r"([\d.]+)\s*%?", text)
    if not m:
        return None
    try:
        val = float(m.group(1))
    except ValueError:
        return None
    if val > 1000:
        return None
    return val
