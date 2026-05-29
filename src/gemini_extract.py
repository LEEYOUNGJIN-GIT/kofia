"""Optional Gemini helper for unstructured disclosure text (PDF/HTML)."""

from __future__ import annotations

import json
import os
from typing import Any

import requests

GEMINI_URL = (
    "https://generativelanguage.googleapis.com/v1beta/models/"
    "gemini-2.0-flash:generateContent"
)


def extract_allocation_from_text(
    text: str,
    *,
    srtn_cd: str,
    bas_dt: str,
) -> list[dict[str, Any]]:
    """
    Parse asset-class weights from raw disclosure text via Gemini.
    Returns rows compatible with fund_allocation.csv when API key is set.
    """
    api_key = os.environ.get("GEMINI_API_KEY", "").strip()
    if not api_key:
        return []

    prompt = (
        "Extract fund asset allocation as JSON array. Each item: "
        '{"asset_class": string, "weight_pct": number}. '
        f"Fund srtn_cd={srtn_cd}, bas_dt={bas_dt}. Text:\n{text[:120000]}"
    )
    resp = requests.post(
        f"{GEMINI_URL}?key={api_key}",
        json={"contents": [{"parts": [{"text": prompt}]}]},
        timeout=120,
    )
    resp.raise_for_status()
    body = resp.json()
    parts = body.get("candidates", [{}])[0].get("content", {}).get("parts", [])
    raw = parts[0].get("text", "") if parts else ""
    start = raw.find("[")
    end = raw.rfind("]")
    if start < 0 or end <= start:
        return []
    items = json.loads(raw[start : end + 1])
    rows: list[dict[str, Any]] = []
    for item in items:
        if not isinstance(item, dict):
            continue
        ac = item.get("asset_class")
        wp = item.get("weight_pct")
        if ac is None or wp is None:
            continue
        rows.append(
            {
                "asset_class": str(ac),
                "weight_pct": float(wp),
                "source_doc": "gemini:extract",
            }
        )
    return rows
