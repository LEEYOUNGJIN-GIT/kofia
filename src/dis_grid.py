"""Parse DISCondFuncListDTO / selectMeta grid responses."""

from __future__ import annotations

import xml.etree.ElementTree as ET


def parse_select_meta_rows(root: ET.Element) -> list[dict[str, str]]:
    rows: list[dict[str, str]] = []
    for node in root.iter():
        if node.tag.split("}")[-1] != "selectMeta":
            continue
        row: dict[str, str] = {}
        for child in node:
            key = child.tag.split("}")[-1]
            if child.text and child.text.strip():
                row[key] = child.text.strip()
        if row:
            rows.append(row)
    return rows


def find_row_by_srtn_cd(rows: list[dict[str, str]], srtn_cd: str) -> dict[str, str] | None:
    for row in rows:
        if row.get("tmpV12") == srtn_cd:
            return row
    return None
