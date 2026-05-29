"""Parse disclosed fund holdings tables (variable length) from rows or HTML."""

from __future__ import annotations

import hashlib
import re
from typing import Any

try:
    from bs4 import BeautifulSoup
except ImportError:
    BeautifulSoup = None  # type: ignore

DEFAULT_MAX_HOLDINGS = 80

HOLDING_MANIFEST_KEYS = ("rank", "name", "weight_pct", "code", "source", "note")


def rows_to_holdings(
    rows: list[dict[str, str]],
    *,
    source: str,
    max_items: int = DEFAULT_MAX_HOLDINGS,
) -> list[dict[str, Any]]:
    """Map ProFrame/list rows to holdings; keep all rows up to max_items (not fixed 10)."""
    name_keys = ("scrNm", "koreanScrNm", "itemNm", "fundNm", "bondNm", "name", "holdNm", "종목명")
    weight_keys = (
        "weight",
        "weightPct",
        "holdRate",
        "rate",
        "ratio",
        "wt",
        "val2",
        "val1",
        "비중",
    )
    code_keys = ("scrCd", "standardCd", "isin", "itemCd")

    candidates: list[tuple[float, dict[str, Any]]] = []
    for row in rows:
        name = next((row[k] for k in name_keys if row.get(k)), "")
        if not name or len(name) < 2:
            continue
        if name in ("종목명", "합계", "계", "소계"):
            continue
        w_raw = next((row[k] for k in weight_keys if row.get(k)), "")
        try:
            w = float(str(w_raw).replace("%", "").replace(",", ""))
        except ValueError:
            w = 0.0
        code = next((row[k] for k in code_keys if row.get(k)), "")
        note = str(row.get("note") or row.get("비고") or "")
        candidates.append(
            (
                w,
                {
                    "name": name,
                    "weight_pct": w_raw or (str(w) if w else ""),
                    "code": code,
                    "note": note,
                },
            )
        )

    candidates.sort(key=lambda x: -x[0])
    out: list[dict[str, Any]] = []
    for rank, (_, item) in enumerate(candidates[:max_items], start=1):
        out.append(
            {
                "rank": str(rank),
                "name": item["name"],
                "weight_pct": item["weight_pct"],
                "code": item.get("code", ""),
                "note": item.get("note", ""),
                "source": source,
            }
        )
    return out


def _normalize_holdings_list(
    items: list[dict[str, Any]],
    *,
    source: str,
    max_items: int = DEFAULT_MAX_HOLDINGS,
) -> list[dict[str, Any]]:
    out: list[dict[str, Any]] = []
    for i, item in enumerate(items[:max_items], start=1):
        if not isinstance(item, dict):
            continue
        name = str(item.get("name") or "").strip()
        if not name or len(name) < 2:
            continue
        out.append(
            {
                "rank": str(item.get("rank") or i),
                "name": name,
                "weight_pct": str(item.get("weight_pct") or ""),
                "code": str(item.get("code") or ""),
                "note": str(item.get("note") or ""),
                "source": str(item.get("source") or source),
            }
        )
    return out


def parse_holdings_html(
    html: str,
    *,
    source: str,
    max_items: int = DEFAULT_MAX_HOLDINGS,
) -> list[dict[str, Any]]:
    """
    Best-effort: tables under '주요 자산 보유' / '상위' sections.
    """
    if not html.strip():
        return []
    if not BeautifulSoup:
        return _parse_holdings_plaintext(html, source=source, max_items=max_items)

    soup = BeautifulSoup(html, "lxml")
    section_text = soup.get_text("\n", strip=True)
    if "보유" not in section_text and "종목" not in section_text:
        return _parse_holdings_plaintext(section_text, source=source, max_items=max_items)

    candidates: list[tuple[float, dict[str, Any]]] = []
    for table in soup.find_all("table"):
        headers = [th.get_text(strip=True) for th in table.find_all("th")]
        if not headers:
            first = table.find("tr")
            if first:
                headers = [td.get_text(strip=True) for td in first.find_all(["td", "th"])]
        name_idx = _col_index(headers, ("종목", "종목명", "명칭", "issuer", "name"))
        wt_idx = _col_index(headers, ("비중", "비율", "weight", "%"))
        note_idx = _col_index(headers, ("비고", "note", "remark"))
        if name_idx < 0:
            continue
        for tr in table.find_all("tr"):
            cells = [td.get_text(strip=True) for td in tr.find_all(["td", "th"])]
            if len(cells) <= name_idx:
                continue
            name = cells[name_idx]
            if not name or len(name) < 2 or name in ("종목명", "합계", "계"):
                continue
            w_raw = cells[wt_idx] if wt_idx >= 0 and wt_idx < len(cells) else ""
            if w_raw and not re.search(r"[\d.]", w_raw):
                w_raw = ""
            try:
                w = float(str(w_raw).replace("%", "").replace(",", "")) if w_raw else 0.0
            except ValueError:
                w = 0.0
            if not w_raw and w == 0.0:
                continue
            note = cells[note_idx] if note_idx >= 0 and note_idx < len(cells) else ""
            candidates.append(
                (
                    w,
                    {
                        "name": name,
                        "weight_pct": w_raw or str(w),
                        "code": "",
                        "note": note,
                    },
                )
            )

    if not candidates:
        return _parse_holdings_plaintext(section_text, source=source, max_items=max_items)

    candidates.sort(key=lambda x: -x[0])
    out: list[dict[str, Any]] = []
    for rank, (_, item) in enumerate(candidates[:max_items], start=1):
        out.append({**item, "rank": str(rank), "source": source})
    return out


def _col_index(headers: list[str], needles: tuple[str, ...]) -> int:
    for i, h in enumerate(headers):
        hlo = h.lower()
        if any(n in h or n in hlo for n in needles):
            return i
    return -1


def _parse_holdings_plaintext(
    text: str,
    *,
    source: str,
    max_items: int,
) -> list[dict[str, Any]]:
    """Lines like '종목명 ... 12.34' or 'name  7.43 %'."""
    rows: list[dict[str, str]] = []
    for line in text.splitlines():
        line = line.strip()
        if len(line) < 4:
            continue
        m = re.search(r"([\d,]+\.?\d*)\s*%?\s*$", line)
        if not m:
            continue
        w_raw = m.group(1)
        name = line[: m.start()].strip()
        if len(name) < 2:
            continue
        rows.append({"name": name, "weight_pct": w_raw, "비중": w_raw})
    return rows_to_holdings(rows, source=source, max_items=max_items)


def holdings_manifest(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    return [{k: r.get(k, "") for k in HOLDING_MANIFEST_KEYS} for r in rows]


def report_text_fingerprint(text: str, *, sample_len: int = 12000) -> str:
    """Stable id for disclosure body — skip duplicate Gemini on same document."""
    normalized = re.sub(r"\s+", " ", (text or "").strip())[:sample_len]
    return hashlib.sha256(normalized.encode("utf-8", errors="replace")).hexdigest()[:16]


def _parse_weight_pct(raw: str) -> float | None:
    try:
        return float(str(raw).replace("%", "").replace(",", "").strip())
    except ValueError:
        return None


_NOISE_NAME_RE = re.compile(
    r"^(\d{4}\.|\(전\s*화\)|\[?\d+[_\]]\d*[_\]]?|originalamt|issuecnt)",
    re.IGNORECASE,
)
_PHONE_RE = re.compile(r"02[-\s]?\d{3,4}|1577|3774|8235")


def is_plausible_holding_row(name: str, weight_pct: str) -> bool:
    name = (name or "").strip()
    if len(name) < 2 or name in ("종목명", "합계", "계", "소계"):
        return False
    if _NOISE_NAME_RE.search(name) or _PHONE_RE.search(name):
        return False
    if re.fullmatch(r"[\d.\s\[\]_\-]+", name):
        return False
    if not re.search(r"[가-힣A-Za-z]{2}", name):
        return False
    w = _parse_weight_pct(weight_pct)
    if w is None or w <= 0 or w > 100:
        return False
    return True


def holdings_look_valid(holdings: list[dict[str, Any]]) -> bool:
    """
    Reject parser noise (phone numbers, dates, weights >100%).
    Used to trigger Gemini fallback when HTML rules return garbage rows.
    """
    if not holdings:
        return False
    plausible = [
        h
        for h in holdings
        if is_plausible_holding_row(str(h.get("name", "")), str(h.get("weight_pct", "")))
    ]
    if not plausible:
        return False
    if len(plausible) < max(1, len(holdings) // 2):
        return False
    weights = [_parse_weight_pct(str(h.get("weight_pct", ""))) for h in plausible]
    weights = [w for w in weights if w is not None]
    if weights and sum(weights) > 150:
        return False
    return True


def filter_valid_holdings(holdings: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Keep rows only if the list passes holdings_look_valid; else []."""
    return holdings if holdings_look_valid(holdings) else []


# Back-compat alias
rows_to_top10 = rows_to_holdings
