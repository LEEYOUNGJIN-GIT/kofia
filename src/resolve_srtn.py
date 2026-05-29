"""Resolve srtn_cd for funds in fund_list.yaml via DISComFundSrchSO."""

from __future__ import annotations

import argparse
import sys
import time
from pathlib import Path

import yaml

sys.path.insert(0, str(Path(__file__).resolve().parent))
from dis_client import DisProframeClient, pick_fund_row, search_query_for_fund

ROOT = Path(__file__).resolve().parents[1]
CONFIG_PATH = ROOT / "config" / "fund_list.yaml"


def resolve_fund_list(path: Path, *, delay: float = 1.2, only_missing: bool = True) -> list[dict]:
    data = yaml.safe_load(path.read_text(encoding="utf-8"))
    funds = data.get("funds") or []
    client = DisProframeClient()
    results: list[dict] = []

    for fund in funds:
        if only_missing and fund.get("srtn_cd"):
            continue
        fnd_nm = fund.get("fnd_nm") or ""
        alias = fund.get("alias") or ""
        try:
            query = search_query_for_fund(fnd_nm, alias)
            rows = client.search_funds_by_name(query)
            match = pick_fund_row(rows, fnd_nm, srtn_cd_hint=fund.get("srtn_cd"), alias=alias)
            results.append(
                {
                    "alias": alias,
                    "fnd_nm": fnd_nm,
                    "search_query": query,
                    "srtn_cd": match.get("standardCd") if match else None,
                    "koreanFundNm": match.get("koreanFundNm") if match else None,
                    "candidates": len(rows),
                }
            )
        except Exception as exc:  # noqa: BLE001
            results.append({"alias": alias, "fnd_nm": fnd_nm, "error": str(exc)})
        time.sleep(delay)
    return results


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Resolve srtn_cd for fund_list.yaml")
    parser.add_argument("--config", type=Path, default=CONFIG_PATH)
    parser.add_argument("--all", action="store_true", help="Re-resolve even if srtn_cd set")
    args = parser.parse_args(argv)

    results = resolve_fund_list(args.config, only_missing=not args.all)
    for row in results:
        print(yaml.safe_dump(row, allow_unicode=True).strip())
    ok = sum(1 for r in results if r.get("srtn_cd"))
    print(f"\nResolved {ok}/{len(results)}", file=sys.stderr)
    return 0 if ok == len(results) and results else 1


if __name__ == "__main__":
    raise SystemExit(main())
