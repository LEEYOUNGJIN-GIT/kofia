"""Sync config/fund_list.yaml from docs/holdings_fund_list.md (source of truth)."""

from __future__ import annotations

import argparse
import re
import sys
from datetime import datetime, timezone
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parents[1]
DEFAULT_HOLDINGS = ROOT / "docs" / "holdings_fund_list.md"
DEFAULT_YAML = ROOT / "config" / "fund_list.yaml"

TABLE_HEADER = ("펀드명", "유형", "srtn_cd", "alias", "enabled")


def _normalize_name(name: str) -> str:
    return "".join(name.split()).lower().replace("-", "").replace("_", "")


def _parse_enabled(raw: str) -> bool:
    v = (raw or "").strip().lower()
    if v in ("true", "yes", "y", "1", "o", "on"):
        return True
    if v in ("false", "no", "n", "0", "off"):
        return False
    return True


def _default_alias(row_num: int, fnd_nm: str, existing_alias: str | None) -> str:
    if existing_alias and existing_alias.strip():
        return existing_alias.strip()
    if "tdf2050" in fnd_nm.lower():
        return "TDF2050_Ce"
    slug = re.sub(r"[^A-Za-z0-9가-힣]+", "_", fnd_nm).strip("_")[:28]
    return f"F{row_num:02d}_{slug}"[:32]


def parse_holdings_table(text: str) -> list[dict]:
    """Parse the markdown table under '## 일반펀드'."""
    section_match = re.search(
        r"##\s*일반펀드[^\n]*\n+(.*?)(?=\n##\s|\Z)",
        text,
        re.DOTALL | re.IGNORECASE,
    )
    if not section_match:
        raise ValueError("Could not find '## 일반펀드' section with fund table")

    rows: list[dict] = []
    for line in section_match.group(1).splitlines():
        line = line.strip()
        if not line.startswith("|"):
            continue
        cells = [c.strip() for c in line.strip("|").split("|")]
        if len(cells) < 5:
            continue
        if cells[0] in ("#", "---", "") or "펀드명" in cells[0]:
            continue
        if all(set(c) <= set("-: ") for c in cells):
            continue

        # | # | 펀드명 | 유형 | srtn_cd | alias | enabled |
        try:
            row_num = int(cells[0])
        except ValueError:
            continue

        fnd_nm = cells[1]
        if not fnd_nm:
            continue

        fnd_tp = cells[2] if len(cells) > 2 else ""
        srtn_cd = cells[3] if len(cells) > 3 else ""
        alias_cell = cells[4] if len(cells) > 4 else ""
        enabled_cell = cells[5] if len(cells) > 5 else "true"

        rows.append(
            {
                "row_num": row_num,
                "fnd_nm": fnd_nm,
                "fnd_tp": fnd_tp,
                "srtn_cd": srtn_cd.strip(),
                "alias": alias_cell.strip(),
                "enabled": _parse_enabled(enabled_cell),
            }
        )
    return rows


def load_existing_yaml(path: Path) -> dict[str, dict]:
    if not path.exists():
        return {}
    data = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
    by_key: dict[str, dict] = {}
    for fund in data.get("funds") or []:
        key = _normalize_name(fund.get("fnd_nm", ""))
        if key:
            by_key[key] = fund
        alias = (fund.get("alias") or "").strip()
        if alias:
            by_key[f"alias:{alias}"] = fund
    return by_key


def merge_funds(
    parsed: list[dict],
    existing: dict[str, dict],
) -> tuple[list[dict], list[dict]]:
    """Build fund_list entries; return (active funds, retired/disabled from yaml)."""
    out: list[dict] = []
    seen_names: set[str] = set()

    for row in parsed:
        norm = _normalize_name(row["fnd_nm"])
        seen_names.add(norm)
        prev = existing.get(norm) or (
            existing.get(f"alias:{row['alias']}") if row["alias"] else None
        )

        srtn_cd = row["srtn_cd"] or (prev.get("srtn_cd") if prev else "") or ""
        alias = _default_alias(
            row["row_num"],
            row["fnd_nm"],
            row["alias"] or (prev.get("alias") if prev else None),
        )
        notes = prev.get("notes") if prev else None

        entry = {
            "srtn_cd": srtn_cd,
            "alias": alias,
            "fnd_nm": row["fnd_nm"],
            "fnd_tp": row["fnd_tp"] or (prev.get("fnd_tp") if prev else ""),
            "enabled": row["enabled"],
        }
        if notes:
            entry["notes"] = notes
        out.append(entry)

    retired: list[dict] = []
    for key, fund in existing.items():
        if key.startswith("alias:"):
            continue
        norm = _normalize_name(fund.get("fnd_nm", ""))
        if norm and norm not in seen_names:
            note = fund.get("notes") or ""
            if "retired from fund list" not in note:
                note = (note + " [retired from fund list]").strip()
            retired.append({**fund, "enabled": False, "notes": note})
    return out, retired


def sync_holdings_to_yaml(
    holdings_path: Path = DEFAULT_HOLDINGS,
    yaml_path: Path = DEFAULT_YAML,
    *,
    include_retired: bool = True,
) -> dict:
    text = holdings_path.read_text(encoding="utf-8")
    parsed = parse_holdings_table(text)
    existing = load_existing_yaml(yaml_path)
    active, retired = merge_funds(parsed, existing)

    funds = active + (retired if include_retired else [])
    payload = {
        "source": str(holdings_path.relative_to(ROOT)).replace("\\", "/"),
        "synced_at": datetime.now(timezone.utc).isoformat(),
        "funds": funds,
    }
    return {
        "payload": payload,
        "parsed_count": len(parsed),
        "active_count": sum(1 for f in active if f.get("enabled")),
        "retired_count": len(retired),
    }


def write_yaml(payload: dict, yaml_path: Path = DEFAULT_YAML) -> None:
    yaml_path.parent.mkdir(parents=True, exist_ok=True)
    body = {
        "source": payload.get("source"),
        "synced_at": payload.get("synced_at"),
        "funds": payload.get("funds"),
    }
    yaml_path.write_text(
        yaml.safe_dump(body, allow_unicode=True, sort_keys=False, default_flow_style=False),
        encoding="utf-8",
    )


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Sync fund_list.yaml from docs/holdings_fund_list.md"
    )
    parser.add_argument("--holdings", type=Path, default=DEFAULT_HOLDINGS)
    parser.add_argument("--output", type=Path, default=DEFAULT_YAML)
    parser.add_argument("--dry-run", action="store_true", help="Print summary only")
    parser.add_argument("--no-retired", action="store_true", help="Drop funds removed from doc")
    args = parser.parse_args(argv)

    result = sync_holdings_to_yaml(
        args.holdings,
        args.output,
        include_retired=not args.no_retired,
    )
    print(
        f"Parsed {result['parsed_count']} funds from holdings; "
        f"enabled={result['active_count']}; retired={result['retired_count']}",
        file=sys.stderr,
    )
    if args.dry_run:
        for f in result["payload"]["funds"]:
            if f.get("enabled"):
                print(f"  [on] {f.get('alias')}: {f.get('fnd_nm')[:40]}")
        return 0

    write_yaml(result["payload"], args.output)
    print(f"Wrote {args.output}", file=sys.stderr)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
