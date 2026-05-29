"""Optional Gemini extraction for top10 from report text (no Playwright)."""

from __future__ import annotations

import json
import os
import re
from typing import Any

import requests

GEMINI_URL = (
    "https://generativelanguage.googleapis.com/v1beta/models/"
    "gemini-2.0-flash:generateContent"
)


def extract_top10_from_report_text(
    text: str,
    *,
    srtn_cd: str,
    bas_dt: str = "",
    timeout: int = 60,
) -> list[dict[str, Any]]:
    """Return [{rank, name, weight_pct, code?}] or []."""
    api_key = os.environ.get("GEMINI_API_KEY", "").strip()
    if not api_key or not text.strip():
        return []

    prompt = (
        "Extract the fund's top 10 holdings from the disclosure text.\n"
        "Return ONLY a JSON array. Each item: "
        '{"rank":"1","name":"...","weight_pct":"12.34","code":""}\n'
        f"Fund standard code: {srtn_cd}. Report date: {bas_dt}.\n"
        "If no top-10 table, return [].\n\n"
        f"TEXT:\n{text[:80000]}"
    )
    body = {
        "contents": [{"parts": [{"text": prompt}]}],
        "generationConfig": {"temperature": 0.1, "maxOutputTokens": 2048},
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
        out: list[dict[str, Any]] = []
        for i, item in enumerate(parsed[:10], start=1):
            if not isinstance(item, dict):
                continue
            out.append(
                {
                    "rank": str(item.get("rank") or i),
                    "name": str(item.get("name") or ""),
                    "weight_pct": str(item.get("weight_pct") or ""),
                    "code": str(item.get("code") or ""),
                    "source": "gemini:report",
                }
            )
        return [r for r in out if r.get("name")]
    except Exception:
        return []
