"""dis.kofia 수집 CLI — dry-run(G1) / fetch(GHA)."""

from __future__ import annotations

import argparse
import json
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

import yaml

sys.path.insert(0, str(Path(__file__).resolve().parent))
from dis_client import DisProframeClient, pick_fund_row, search_query_for_fund
from dis_grid import find_row_by_srtn_cd
from dis_quarterly import allocation_from_bs, fetch_quarterly_allocation, validate_weight_sum
from dis_reports import balance_sheet_to_allocation_rows, inquiry_report_periods, pick_report_period
from dis_top10 import top10_from_bs
from timeseries_io import upsert_rows

ROOT = Path(__file__).resolve().parents[1]
CONFIG_PATH = ROOT / "config" / "fund_list.yaml"
LOG_DIR = ROOT / "data" / "logs"
TS_DIR = ROOT / "data" / "timeseries"
PARSER_VERSION = "0.3.0"
REQUEST_DELAY_SEC = 1.2

ALLOCATION_FIELDS = [
    "srtn_cd",
    "alias",
    "bas_dt",
    "report_type",
    "asset_class",
    "weight_pct",
    "amount_mkrw",
    "source_doc",
    "fetched_at",
]
REGISTRY_FIELDS = [
    "srtn_cd",
    "alias",
    "fnd_nm",
    "korean_fund_nm",
    "company_cd",
    "fnd_tp",
    "fetched_at",
]
STD_PRICE_FIELDS = [
    "srtn_cd",
    "alias",
    "bas_dt",
    "std_price",
    "setup_dt",
    "company_nm",
    "korean_fund_nm",
    "fetched_at",
]
TOP10_FIELDS = [
    "srtn_cd",
    "alias",
    "bas_dt",
    "rank",
    "name",
    "asset_type",
    "weight_pct",
    "source_doc",
    "fetched_at",
]


def load_fund_list(path: Path, *, all_enabled: bool = False) -> list[dict]:
    data = yaml.safe_load(path.read_text(encoding="utf-8"))
    funds = data.get("funds") or []
    if all_enabled:
        return list(funds)
    return [f for f in funds if f.get("enabled", True)]


def quarter_to_bas_dt_hint(quarter: str) -> str | None:
    q = quarter.strip().upper()
    if len(q) != 6 or q[4] != "Q":
        return None
    year, qn = int(q[:4]), int(q[5])
    ends = {1: "0331", 2: "0630", 3: "0930", 4: "1231"}
    if qn not in ends:
        return None
    return f"{year}{ends[qn]}"


def iter_quarters(from_q: str, to_q: str) -> list[str]:
    """Yield quarters from 2024Q1 style strings inclusive."""
    def parse(q: str) -> tuple[int, int]:
        q = q.strip().upper()
        return int(q[:4]), int(q[5])

    y1, n1 = parse(from_q)
    y2, n2 = parse(to_q)
    out: list[str] = []
    y, n = y1, n1
    while (y, n) <= (y2, n2):
        out.append(f"{y}Q{n}")
        n += 1
        if n > 4:
            n = 1
            y += 1
    return out


def backfill_quarters(count: int, *, end: str | None = None) -> list[str]:
    if end:
        ey, en = int(end[:4]), int(end[5])
    else:
        now = datetime.now(timezone.utc)
        en = (now.month - 1) // 3 + 1
        ey = now.year
    quarters: list[str] = []
    y, n = ey, en
    for _ in range(count):
        quarters.append(f"{y}Q{n}")
        n -= 1
        if n < 1:
            n = 4
            y -= 1
    return list(reversed(quarters))


def run_dry_run(alias: str | None, fund_list_path: Path, *, all_funds: bool = False) -> dict:
    funds = load_fund_list(fund_list_path, all_enabled=all_funds)
    if alias:
        funds = [f for f in funds if f.get("alias") == alias]
    if not funds:
        raise SystemExit(f"No funds for alias={alias!r}")

    client = DisProframeClient()
    results: list[dict] = []
    failed: list[dict] = []

    for fund in funds:
        fnd_nm = fund["fnd_nm"]
        try:
            time.sleep(REQUEST_DELAY_SEC)
            query = search_query_for_fund(fnd_nm, fund.get("alias"))
            rows = client.search_funds_by_name(query)
            match = pick_fund_row(
                rows,
                fnd_nm,
                srtn_cd_hint=fund.get("srtn_cd"),
                alias=fund.get("alias"),
            )
            if not match:
                failed.append({"alias": fund.get("alias"), "error": "no_match", "candidates": len(rows)})
                continue
            results.append(
                {
                    "alias": fund.get("alias"),
                    "fnd_nm": fnd_nm,
                    "srtn_cd_config": fund.get("srtn_cd"),
                    "srtn_cd_dis": match.get("standardCd"),
                    "koreanFundNm": match.get("koreanFundNm"),
                    "proframe_endpoint": "https://dis.kofia.or.kr/proframeWeb/XMLSERVICES/",
                    "search_query": query,
                }
            )
        except Exception as exc:  # noqa: BLE001
            failed.append({"alias": fund.get("alias"), "fnd_nm": fnd_nm, "error": str(exc)})

    return {
        "parser_version": PARSER_VERSION,
        "mode": "dry_run",
        "fetched_at": datetime.now(timezone.utc).isoformat(),
        "ok": results,
        "failed": failed,
        "gates": {
            "G1_proframe_reachable": len(results) > 0,
            "playwright_used": False,
        },
    }


def _fetch_one_fund(
    client: DisProframeClient,
    fund: dict,
    *,
    quarter: str | None,
    use_gemini: bool,
    grid_cache: dict[str, list[dict[str, str]]],
) -> tuple[dict | None, dict | None, list[dict], list[dict], list[dict], list[dict], list[str]]:
    """Returns (ok_entry, fail_entry, registry, allocation, std_price, top10, warnings)."""
    fnd_nm = fund["fnd_nm"]
    fund_alias = fund.get("alias") or ""
    warnings: list[str] = []
    registry_rows: list[dict[str, str]] = []
    allocation_rows: list[dict[str, str]] = []
    std_price_rows: list[dict[str, str]] = []
    top10_rows: list[dict[str, str]] = []

    query = search_query_for_fund(fnd_nm, fund_alias)
    time.sleep(REQUEST_DELAY_SEC)
    search_rows = client.search_funds_by_name(query)
    match = pick_fund_row(
        search_rows,
        fnd_nm,
        srtn_cd_hint=fund.get("srtn_cd"),
        alias=fund_alias,
    )
    if not match:
        return None, {"alias": fund_alias, "error": "no_match"}, [], [], [], [], []

    srtn_cd = match.get("standardCd") or fund.get("srtn_cd") or ""
    if not srtn_cd:
        return None, {"alias": fund_alias, "error": "no_srtn_cd"}, [], [], [], [], []

    registry_rows.append(
        {
            "srtn_cd": srtn_cd,
            "alias": fund_alias,
            "fnd_nm": fnd_nm,
            "korean_fund_nm": match.get("koreanFundNm", ""),
            "company_cd": match.get("companyCd", ""),
            "fnd_tp": fund.get("fnd_tp", ""),
        }
    )

    bas_hint = quarter_to_bas_dt_hint(quarter) if quarter else None
    if query not in grid_cache:
        time.sleep(REQUEST_DELAY_SEC)
        grid_cache[query] = client.fetch_std_price_grid(query, bas_dt=bas_hint or "")
    grid_row = find_row_by_srtn_cd(grid_cache[query], srtn_cd)
    if grid_row:
        bas_dt_raw = grid_row.get("tmpV14") or ""
        bas_dt = (
            f"{bas_dt_raw[:4]}-{bas_dt_raw[4:6]}-{bas_dt_raw[6:8]}"
            if len(bas_dt_raw) == 8
            else bas_dt_raw
        )
        std_price_rows.append(
            {
                "srtn_cd": srtn_cd,
                "alias": fund_alias,
                "bas_dt": bas_dt,
                "std_price": grid_row.get("tmpV6", ""),
                "setup_dt": grid_row.get("tmpV4", ""),
                "company_nm": grid_row.get("tmpV1", ""),
                "korean_fund_nm": grid_row.get("tmpV2", ""),
            }
        )

    time.sleep(REQUEST_DELAY_SEC)
    periods = inquiry_report_periods(client, srtn_cd)
    period = pick_report_period(periods, bas_dt_hint=bas_hint)
    if not period:
        return None, {"alias": fund_alias, "error": "no_report_period"}, registry_rows, [], [], [], []

    time.sleep(REQUEST_DELAY_SEC)
    q_rows = fetch_quarterly_allocation(
        client,
        srtn_cd=srtn_cd,
        alias=fund_alias,
        standard_dt=period["standardDt"],
        tx_cd=period.get("txCd", "2RF0100"),
        tx_vsn=period.get("txVsn", "1"),
    )
    if not q_rows:
        from dis_reports import fetch_balance_sheet

        bs = fetch_balance_sheet(
            client,
            srtn_cd=srtn_cd,
            standard_dt=period["standardDt"],
            tx_cd=period.get("txCd", "2RF0100"),
            tx_vsn=period.get("txVsn", "1"),
        )
        q_rows = balance_sheet_to_allocation_rows(bs, srtn_cd=srtn_cd, alias=fund_alias)
        if not q_rows:
            q_rows = allocation_from_bs(bs, srtn_cd=srtn_cd, alias=fund_alias)
        bs_for_top10 = bs
    else:
        from dis_reports import fetch_balance_sheet

        time.sleep(REQUEST_DELAY_SEC)
        bs_for_top10 = fetch_balance_sheet(
            client,
            srtn_cd=srtn_cd,
            standard_dt=period["standardDt"],
            tx_cd=period.get("txCd", "2RF0100"),
            tx_vsn=period.get("txVsn", "1"),
        )

    for row in q_rows:
        allocation_rows.append({k: str(v) for k, v in row.items()})

    w = validate_weight_sum(q_rows)
    if w:
        warnings.append(f"{fund_alias}:{w}")

    for row in top10_from_bs(bs_for_top10, srtn_cd=srtn_cd, alias=fund_alias):
        top10_rows.append({k: str(v) for k, v in row.items()})

    if use_gemini:
        import os

        if os.environ.get("GEMINI_API_KEY"):
            from gemini_extract import extract_allocation_from_text

            gemini_rows = extract_allocation_from_text(
                json.dumps(bs_for_top10, ensure_ascii=False),
                srtn_cd=srtn_cd,
                bas_dt=bs_for_top10.get("standardDt", ""),
            )
            for gr in gemini_rows:
                allocation_rows.append(
                    {
                        "srtn_cd": srtn_cd,
                        "alias": fund_alias,
                        "bas_dt": _format_bas_dt(bs_for_top10.get("standardDt", "")),
                        "report_type": "gemini",
                        "asset_class": gr["asset_class"],
                        "weight_pct": str(gr["weight_pct"]),
                        "amount_mkrw": "",
                        "source_doc": gr.get("source_doc", "gemini"),
                    }
                )

    ok_entry = {
        "alias": fund_alias,
        "srtn_cd": srtn_cd,
        "quarter": quarter,
        "report_standard_dt": period.get("standardDt"),
        "allocation_rows": len([r for r in allocation_rows if r["srtn_cd"] == srtn_cd]),
        "top10_rows": len(top10_rows),
    }
    return ok_entry, None, registry_rows, allocation_rows, std_price_rows, top10_rows, warnings


def _format_bas_dt(raw: str) -> str:
    if len(raw) == 8 and raw.isdigit():
        return f"{raw[:4]}-{raw[4:6]}-{raw[6:8]}"
    return raw


def run_fetch(
    alias: str | None,
    fund_list_path: Path,
    *,
    quarter: str | None = None,
    quarters: list[str] | None = None,
    use_gemini: bool = False,
    all_funds: bool = False,
) -> dict:
    funds = load_fund_list(fund_list_path, all_enabled=all_funds)
    if alias:
        funds = [f for f in funds if f.get("alias") == alias]
    if not funds:
        raise SystemExit(f"No funds for alias={alias!r}")

    q_list = quarters or ([quarter] if quarter else [None])
    client = DisProframeClient()
    registry_rows: list[dict[str, str]] = []
    allocation_rows: list[dict[str, str]] = []
    std_price_rows: list[dict[str, str]] = []
    top10_rows: list[dict[str, str]] = []
    ok: list[dict] = []
    failed: list[dict] = []
    warnings: list[str] = []
    grid_cache: dict[str, list[dict[str, str]]] = {}

    for q in q_list:
        for fund in funds:
            try:
                o, f, reg, alloc, std, t10, w = _fetch_one_fund(
                    client,
                    fund,
                    quarter=q,
                    use_gemini=use_gemini,
                    grid_cache=grid_cache,
                )
                warnings.extend(w)
                if f:
                    f["quarter"] = q
                    failed.append(f)
                    continue
                if o:
                    registry_rows.extend(reg)
                    allocation_rows.extend(alloc)
                    std_price_rows.extend(std)
                    top10_rows.extend(t10)
                    ok.append(o)
            except Exception as exc:  # noqa: BLE001
                failed.append(
                    {
                        "alias": fund.get("alias"),
                        "fnd_nm": fund.get("fnd_nm"),
                        "quarter": q,
                        "error": str(exc),
                    }
                )

    n_alloc = upsert_rows(
        TS_DIR / "fund_allocation.csv",
        allocation_rows,
        ["srtn_cd", "bas_dt", "asset_class"],
        fieldnames=ALLOCATION_FIELDS,
    )
    n_reg = upsert_rows(
        TS_DIR / "fund_registry.csv",
        registry_rows,
        ["srtn_cd"],
        fieldnames=REGISTRY_FIELDS,
    )
    n_std = upsert_rows(
        TS_DIR / "fund_std_price.csv",
        std_price_rows,
        ["srtn_cd", "bas_dt"],
        fieldnames=STD_PRICE_FIELDS,
    )
    n_top10 = upsert_rows(
        TS_DIR / "fund_holdings_top10.csv",
        top10_rows,
        ["srtn_cd", "bas_dt", "rank"],
        fieldnames=TOP10_FIELDS,
    )

    unique_classes = len({r["asset_class"] for r in allocation_rows}) if allocation_rows else 0

    return {
        "parser_version": PARSER_VERSION,
        "mode": "fetch",
        "quarter": quarter,
        "quarters": q_list,
        "fetched_at": datetime.now(timezone.utc).isoformat(),
        "ok": ok,
        "failed": failed,
        "warnings": warnings,
        "writes": {
            "fund_allocation.csv": n_alloc,
            "fund_registry.csv": n_reg,
            "fund_std_price.csv": n_std,
            "fund_holdings_top10.csv": n_top10,
        },
        "gates": {
            "G1_proframe_reachable": len(ok) > 0,
            "G2_allocation_csv": n_alloc > 0,
            "G5_top10_csv": n_top10 > 0,
            "G2_multi_asset_class": unique_classes >= 1,
            "playwright_used": False,
            "gemini_used": use_gemini and bool(__import__("os").environ.get("GEMINI_API_KEY")),
        },
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="KOFIA dis parser (HTTP / GHA)")
    parser.add_argument("--quarter", help="Target quarter e.g. 2025Q3")
    parser.add_argument("--from", dest="from_quarter", help="Backfill from quarter")
    parser.add_argument("--to", dest="to_quarter", help="Backfill to quarter")
    parser.add_argument("--backfill", type=int, help="Backfill last N quarters")
    parser.add_argument("--alias", help="Single fund alias")
    parser.add_argument("--all-funds", action="store_true", help="Process all funds in yaml (not only enabled)")
    parser.add_argument("--dry-run", action="store_true", help="ProFrame connectivity only (G1)")
    parser.add_argument("--fetch", action="store_true", help="Fetch registry, allocation, top10 (G2)")
    parser.add_argument("--gemini", action="store_true", help="Optional Gemini pass (needs GEMINI_API_KEY)")
    parser.add_argument("--config", type=Path, default=CONFIG_PATH)
    args = parser.parse_args(argv)

    quarters: list[str] | None = None
    if args.from_quarter and args.to_quarter:
        quarters = iter_quarters(args.from_quarter, args.to_quarter)
    elif args.backfill:
        quarters = backfill_quarters(args.backfill, end=args.quarter)

    if args.dry_run:
        manifest = run_dry_run(args.alias, args.config, all_funds=args.all_funds)
        suffix = "dryrun"
    elif args.fetch:
        manifest = run_fetch(
            args.alias,
            args.config,
            quarter=args.quarter if not quarters else None,
            quarters=quarters,
            use_gemini=args.gemini,
            all_funds=args.all_funds,
        )
        suffix = "fetch"
    else:
        print("Specify --dry-run or --fetch", file=sys.stderr)
        return 2

    LOG_DIR.mkdir(parents=True, exist_ok=True)
    out = LOG_DIR / f"run_{datetime.now(timezone.utc).strftime('%Y%m%d')}_{suffix}.json"
    out.write_text(json.dumps(manifest, ensure_ascii=False, indent=2), encoding="utf-8")

    print(json.dumps(manifest, ensure_ascii=False, indent=2))
    print(f"\nWrote {out}", file=sys.stderr)

    if args.dry_run:
        return 0 if manifest["gates"]["G1_proframe_reachable"] and not manifest["failed"] else 1
    gates = manifest["gates"]
    ok_fetch = gates.get("G2_allocation_csv") and gates.get("G5_top10_csv") and not manifest["failed"]
    return 0 if ok_fetch else 1


if __name__ == "__main__":
    raise SystemExit(main())
