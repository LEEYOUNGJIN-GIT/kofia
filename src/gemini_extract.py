"""Optional Gemini extraction for disclosed holdings from report text (no Playwright)."""

from __future__ import annotations

import json
import os
import re
from typing import Any

import requests

from holdings_parse import DEFAULT_MAX_HOLDINGS, _normalize_holdings_list

GEMINI_URL = (
    "https://generativelanguage.googleapis.com/v1beta/models/"
    "gemini-2.0-flash:generateContent"
)


def extract_holdings_from_report_text(
    text: str,
    *,
    srtn_cd: str,
    bas_dt: str = "",
    source: str = "gemini:report",
    timeout: int = 60,
    max_items: int = DEFAULT_MAX_HOLDINGS,
) -> list[dict[str, Any]]:
    """
    Extract all disclosed holdings rows from report text (not capped at 10).
    Includes main table + material holdings footnotes when present.
    """
    api_key = os.environ.get("GEMINI_API_KEY", "").strip()
    if not api_key or not text.strip():
        return []

    prompt = (
        "Extract ALL fund holdings listed in the disclosure text "
        "(main holdings table, top holdings, and footnotes for 5%+ or 1%+ positions).\n"
        "Return ONLY a JSON array. Each item: "
        '{"rank":"1","name":"...","weight_pct":"12.34","code":"","note":""}\n'
        "Include every row with a name and weight; do not limit to 10.\n"
        f"Fund standard code: {srtn_cd}. Report date: {bas_dt}.\n"
        "If no holdings table, return [].\n\n"
        f"TEXT:\n{text[:80000]}"
    )
    body = {
        "contents": [{"parts": [{"text": prompt}]}],
        "generationConfig": {"temperature": 0.1, "maxOutputTokens": 4096},
    }
    try:
        resp = requests.post(
            GEMINI_URL,
            params={"key": api_key},
            json=body,
            timeout=timeout,
        )
        resp.raise_for_status()
        data = resp.json()
        parts = data["candidates"][0]["content"]["parts"]
        raw = parts[0].get("text", "").strip()
        raw = re.sub(r"^```json\s*|\s*```$", "", raw, flags=re.IGNORECASE)
        parsed = json.loads(raw)
        if not isinstance(parsed, list):
            return []
        return _normalize_holdings_list(parsed, source=source, max_items=max_items)
    except Exception:
        return []


def extract_top10_from_report_text(
    text: str,
    *,
    srtn_cd: str,
    bas_dt: str = "",
    timeout: int = 60,
) -> list[dict[str, Any]]:
    """Back-compat alias."""
    return extract_holdings_from_report_text(
        text,
        srtn_cd=srtn_cd,
        bas_dt=bas_dt,
        timeout=timeout,
    )
