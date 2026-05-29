"""CSV upsert helpers for data/timeseries/."""

from __future__ import annotations

import csv
from datetime import datetime, timezone
from pathlib import Path
from typing import Iterable


def _read_csv(path: Path) -> tuple[list[str], list[dict[str, str]]]:
    if not path.exists():
        return [], []
    with path.open(encoding="utf-8", newline="") as fh:
        reader = csv.DictReader(fh)
        fieldnames = list(reader.fieldnames or [])
        return fieldnames, list(reader)


def upsert_rows(
    path: Path,
    new_rows: Iterable[dict[str, str]],
    key_fields: list[str],
    *,
    fieldnames: list[str] | None = None,
) -> int:
    """Upsert rows by composite key; returns number of rows written/updated."""
    path.parent.mkdir(parents=True, exist_ok=True)
    existing_fields, existing = _read_csv(path)
    merged: dict[tuple[str, ...], dict[str, str]] = {}
    now = datetime.now(timezone.utc).isoformat()

    cols = fieldnames or existing_fields
    for row in existing:
        key = tuple(row.get(k, "") for k in key_fields)
        merged[key] = dict(row)

    updated = 0
    for row in new_rows:
        key = tuple(str(row.get(k, "")) for k in key_fields)
        out = {k: str(row.get(k, "")) for k in (cols or row.keys())}
        out.setdefault("fetched_at", now)
        out["fetched_at"] = now
        if key not in merged or merged[key] != out:
            updated += 1
        merged[key] = out

    if not cols:
        if merged:
            cols = sorted({k for r in merged.values() for k in r})
        else:
            cols = list(key_fields) + ["fetched_at"]

    for k in key_fields:
        if k not in cols:
            cols.insert(0, k)
    if "fetched_at" not in cols:
        cols.append("fetched_at")

    with path.open("w", encoding="utf-8", newline="") as fh:
        writer = csv.DictWriter(fh, fieldnames=cols, extrasaction="ignore")
        writer.writeheader()
        for key in sorted(merged.keys()):
            writer.writerow(merged[key])
    return updated
