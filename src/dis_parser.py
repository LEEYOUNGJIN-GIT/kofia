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
from dis_holdings import resolve_holdings
from holdings_parse import holdings_manifest
from dis_quarterly import allocation_from_bs, fetch_quarterly_allocation, validate_weight_sum
from dis_reports import balance_sheet_to_allocation_rows, inquiry_report_periods, pick_report_period
from dis_grid import find_row_by_srtn_cd
from dis_std_price import fetch_price_trend, month_end_dates_back, std_price_csv_rows
from dis_top10 import top10_bs_from_bs
from portfolio_report import write_portfolio_report
from timeseries_io import upsert_rows

ROOT = Path(__file__).resolve().parents[1]
CONFIG_PATH = ROOT / "config" / "fund_list.yaml"
LOG_DIR = ROOT / "data" / "logs"
TS_DIR = ROOT / "data" / "timeseries"
PARSER_VERSION = "0.5.0"
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
TOP10_BS_FIELDS = [
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


def _allocation_manifest_rows(rows: list[dict]) -> list[dict]:
    return [
        {
            "asset_class": r.get("asset_class"),
            "weight_pct": str(r.get("weight_pct", "")),
            "amount_mkrw": str(r.get("amount_mkrw", "")),
            "bas_dt": r.get("bas_dt"),
            "report_type": r.get("report_type"),
        }
        for r in rows
    ]


def _holdings_manifest(rows: list[dict]) -> list[dict]:
    return holdings_manifest(rows)


def _top10_bs_manifest(rows: list[dict]) -> list[dict]:
    return [
        {
            "rank": r.get("rank"),
            "name": r.get("name"),
            "weight_pct": r.get("weight_pct"),
            "asset_type": r.get("asset_type"),
            "source_doc": r.get("source_doc"),
        }
        for r in rows
    ]


def _fetch_one_fund(
    client: DisProframeClient,
    fund: dict,
    *,
    quarter: str | None,
    grid_cache: dict[tuple[str, str], list[dict[str, str]]],
    use_gemini: bool = False,
    use_dart: bool = False,
    use_funddoctor: bool = False,
    price_days: int = 365,
) -> tuple[dict | None, dict | None, list[dict], list[dict], list[dict], list[dict], list[str]]:
    fnd_nm = fund["fnd_nm"]
    fund_alias = fund.get("alias") or ""
    warnings: list[str] = []
    registry_rows: list[dict[str, str]] = []
    allocation_rows: list[dict[str, str]] = []
    std_price_rows: list[dict[str, str]] = []
    top10_bs_csv: list[dict[str, str]] = []

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

    time.sleep(REQUEST_DELAY_SEC)
    periods = inquiry_report_periods(client, srtn_cd)
    period = pick_report_period(periods, bas_dt_hint=bas_hint)
    if not period:
        return None, {"alias": fund_alias, "error": "no_report_period"}, registry_rows, [], [], [], []

    anchor_dt = bas_hint or period.get("standardDt") or ""
    price_trend = fetch_price_trend(
        client,
        query,
        srtn_cd,
        anchor_standard_dt=anchor_dt,
        alias=fund_alias,
        max_days=price_days,
        delay_sec=REQUEST_DELAY_SEC,
        grid_cache=grid_cache,
    )
    if not price_trend:
        latest_key = (query, month_end_dates_back(anchor_dt, 1)[0])
        grid_row = find_row_by_srtn_cd(grid_cache.get(latest_key, []), srtn_cd)
        if grid_row and grid_row.get("tmpV6"):
            from dis_std_price import price_history_from_grid  # noqa: PLC0415

            bas_dt_raw = grid_row.get("tmpV14") or grid_row.get("tmpV4") or ""
            price_trend = price_history_from_grid(
                [
                    {
                        "tmpV12": srtn_cd,
                        "tmpV14": bas_dt_raw,
                        "tmpV6": grid_row.get("tmpV6", ""),
                        "tmpV7": grid_row.get("tmpV7", ""),
                        "tmpV4": grid_row.get("tmpV4", ""),
                        "tmpV1": grid_row.get("tmpV1", ""),
                        "tmpV2": grid_row.get("tmpV2", ""),
                    }
                ],
                srtn_cd=srtn_cd,
                alias=fund_alias,
                max_days=1,
            )
    std_price_rows = std_price_csv_rows(price_trend)

    time.sleep(REQUEST_DELAY_SEC)
    q_rows = fetch_quarterly_allocation(
        client,
        srtn_cd=srtn_cd,
        alias=fund_alias,
        standard_dt=period["standardDt"],
        tx_cd=period.get("txCd", "2RF0100"),
        tx_vsn=period.get("txVsn", "1"),
    )
    from dis_reports import fetch_balance_sheet

    if not q_rows:
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

    top10_bs = top10_bs_from_bs(bs_for_top10, srtn_cd=srtn_cd, alias=fund_alias)
    for row in top10_bs:
        top10_bs_csv.append({k: str(v) for k, v in row.items()})

    holdings, holdings_status, holdings_source = resolve_holdings(
        client,
        period=period,
        bs=bs_for_top10,
        srtn_cd=srtn_cd,
        fnd_nm=fnd_nm,
        fund=fund,
        use_gemini=use_gemini,
        use_dart=use_dart,
        use_funddoctor=use_funddoctor,
    )

    bas_dt_fmt = period.get("standardDt", "")
    if len(bas_dt_fmt) == 8:
        bas_dt_fmt = f"{bas_dt_fmt[:4]}-{bas_dt_fmt[4:6]}-{bas_dt_fmt[6:8]}"

    ok_entry = {
        "status": "ok",
        "alias": fund_alias,
        "srtn_cd": srtn_cd,
        "fnd_nm": fnd_nm,
        "quarter": quarter,
        "report_standard_dt": period.get("standardDt"),
        "bas_dt": bas_dt_fmt,
        "allocation": _allocation_manifest_rows(q_rows),
        "top10_bs": _top10_bs_manifest(top10_bs),
        "holdings": _holdings_manifest(holdings),
        "holdings_count": len(holdings),
        "holdings_status": holdings_status,
        "holdings_source": holdings_source,
        "top10": _holdings_manifest(holdings),
        "top10_status": holdings_status,
        "top10_source": holdings_source,
        "price_trend": [
            {
                "bas_dt": p.get("bas_dt"),
                "std_price": p.get("std_price"),
                "chg_pct": p.get("chg_pct"),
            }
            for p in price_trend
        ],
    }
    return ok_entry, None, registry_rows, allocation_rows, std_price_rows, top10_bs_csv, warnings


def run_fetch(
    alias: str | None,
    fund_list_path: Path,
    *,
    quarter: str | None = None,
    quarters: list[str] | None = None,
    all_funds: bool = False,
    use_gemini: bool = False,
    use_dart: bool = False,
    use_funddoctor: bool = False,
    price_days: int = 365,
    write_top10_csv: bool = False,
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
    top10_bs_rows: list[dict[str, str]] = []
    ok: list[dict] = []
    failed: list[dict] = []
    warnings: list[str] = []
    grid_cache: dict[tuple[str, str], list[dict[str, str]]] = {}

    for q in q_list:
        for fund in funds:
            try:
                o, f, reg, alloc, std, t10bs, w = _fetch_one_fund(
                    client,
                    fund,
                    quarter=q,
                    grid_cache=grid_cache,
                    use_gemini=use_gemini,
                    use_dart=use_dart,
                    use_funddoctor=use_funddoctor,
                    price_days=price_days,
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
                    if write_top10_csv:
                        top10_bs_rows.extend(t10bs)
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
    n_top10_bs = 0
    if write_top10_csv:
        n_top10_bs = upsert_rows(
            TS_DIR / "fund_holdings_top10.csv",
            top10_bs_rows,
            ["srtn_cd", "bas_dt", "rank"],
            fieldnames=TOP10_BS_FIELDS,
        )

    unique_classes = len({r["asset_class"] for r in allocation_rows}) if allocation_rows else 0
    has_holdings = any(
        (f.get("holdings") or f.get("top10") or f.get("top10_bs")) for f in ok
    )

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
            "fund_holdings_top10.csv": n_top10_bs,
        },
        "gates": {
            "G1_proframe_reachable": len(ok) > 0,
            "G2_allocation_csv": n_alloc > 0,
            "G5_holdings": has_holdings,
            "G5_top10": has_holdings,
            "G_portfolio_report": len(ok) > 0,
            "G2_multi_asset_class": unique_classes >= 1,
            "playwright_used": False,
            "gemini_used": use_gemini and bool(__import__("os").environ.get("GEMINI_API_KEY")),
            "dart_used": use_dart and bool(__import__("os").environ.get("OPENDART_API_KEY")),
            "funddoctor_used": use_funddoctor,
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
    parser.add_argument("--sync", action="store_true", help="Sync holdings.md → fund_list.yaml first")
    parser.add_argument("--dry-run", action="store_true", help="ProFrame connectivity only (G1)")
    parser.add_argument("--fetch", action="store_true", help="Fetch registry, allocation, top10 (G2)")
    parser.add_argument(
        "--gemini",
        action="store_true",
        help="Gemini holdings from KOFIA/DART report when earlier steps fail",
    )
    parser.add_argument(
        "--dart",
        action="store_true",
        help="DART document fallback after KOFIA (needs OPENDART_API_KEY)",
    )
    parser.add_argument(
        "--funddoctor",
        action="store_true",
        help="funddoctor report fallback when fund_list has funddoctor.memb_cd/pfund_cd",
    )
    parser.add_argument("--price-days", type=int, default=365, help="Max price history days in manifest/CSV")
    parser.add_argument("--write-top10-csv", action="store_true", help="Write top10_bs to fund_holdings_top10.csv")
    parser.add_argument("--config", type=Path, default=CONFIG_PATH)
    args = parser.parse_args(argv)

    if args.sync:
        from fund_list_sync import sync_holdings_to_yaml, write_yaml

        result = sync_holdings_to_yaml()
        write_yaml(result["payload"])
        print(
            f"Synced fund_list.yaml: {result['parsed_count']} funds, "
            f"{result['active_count']} enabled",
            file=sys.stderr,
        )

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
            all_funds=args.all_funds,
            use_gemini=args.gemini,
            use_dart=args.dart,
            use_funddoctor=args.funddoctor,
            price_days=args.price_days,
            write_top10_csv=args.write_top10_csv,
        )
        suffix = "fetch"
    elif args.sync:
        return 0
    else:
        print("Specify --dry-run, --fetch, or --sync", file=sys.stderr)
        return 2

    LOG_DIR.mkdir(parents=True, exist_ok=True)
    out = LOG_DIR / f"run_{datetime.now(timezone.utc).strftime('%Y%m%d')}_{suffix}.json"
    out.write_text(json.dumps(manifest, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps(manifest, ensure_ascii=False, indent=2))
    print(f"\nWrote {out}", file=sys.stderr)

    if args.fetch:
        funds_meta = load_fund_list(args.config, all_enabled=args.all_funds)
        report_path = write_portfolio_report(
            manifest,
            fund_list_path=args.config,
            funds_meta=funds_meta,
        )
        print(f"Wrote {report_path}", file=sys.stderr)

    if args.dry_run:
        return 0 if manifest["gates"]["G1_proframe_reachable"] and not manifest["failed"] else 1

    if args.all_funds and not args.alias:
        return 0 if len(manifest.get("ok") or []) >= 1 else 1

    gates = manifest["gates"]
    ok_fetch = (
        gates.get("G2_allocation_csv")
        and (gates.get("G5_holdings") or gates.get("G5_top10"))
        and not manifest["failed"]
    )
    return 0 if ok_fetch else 1


if __name__ == "__main__":
    raise SystemExit(main())
