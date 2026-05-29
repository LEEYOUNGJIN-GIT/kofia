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
from dis_reports import inquiry_report_periods, pick_report_period
from dis_grid import find_row_by_srtn_cd
from dis_std_price import (
    fetch_price_trend,
    fetch_std_price_latest_business,
    month_end_dates_back,
    month_end_series_from_trend,
    latest_month_end_snapshot,
)
from portfolio_report import write_portfolio_report

ROOT = Path(__file__).resolve().parents[1]
CONFIG_PATH = ROOT / "config" / "fund_list.yaml"
LOG_DIR = ROOT / "data" / "logs"
PARSER_VERSION = "0.9.0"
REQUEST_DELAY_SEC = 1.2


def verify_fetch_manifest(manifest: dict) -> dict:
    ok = manifest.get("ok") or []
    failed = manifest.get("failed") or []
    total = len(ok) + len(failed)
    return {
        "funds_total": total,
        "ok": len(ok),
        "failed": len(failed),
        "with_registry": sum(1 for f in ok if (f.get("registry") or {}).get("srtn_cd")),
        "with_price_trend": sum(1 for f in ok if f.get("price_trend")),
        "failure_rate": round(len(failed) / total, 4) if total else 0.0,
    }


def format_verify_report(stats: dict, gates: dict) -> str:
    return "\n".join(
        [
            "=== fetch verification ===",
            f"ok={stats['ok']} failed={stats['failed']} (failure_rate={stats['failure_rate']})",
            f"registry={stats['with_registry']} price_trend={stats['with_price_trend']}",
            f"gates={gates}",
        ]
    )


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
            srtn_cd = match.get("standardCd") or ""
            results.append(
                {
                    "alias": fund.get("alias"),
                    "fnd_nm": fnd_nm,
                    "srtn_cd_config": fund.get("srtn_cd"),
                    "srtn_cd_dis": srtn_cd,
                    "registry": registry_manifest(
                        srtn_cd=srtn_cd,
                        alias=str(fund.get("alias") or ""),
                        fnd_nm=fnd_nm,
                        match=match,
                        fund=fund,
                    ),
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
        },
    }


def registry_manifest(
    *,
    srtn_cd: str,
    alias: str,
    fnd_nm: str,
    match: dict,
    fund: dict,
) -> dict[str, str]:
    """DIS-resolved fund identity (embedded in portfolio JSON per fund)."""
    return {
        "srtn_cd": srtn_cd,
        "alias": alias,
        "fnd_nm": fnd_nm,
        "korean_fund_nm": str(match.get("koreanFundNm", "")),
        "company_cd": str(match.get("companyCd", "")),
        "fnd_tp": str(fund.get("fnd_tp", "")),
    }


def _price_trend_manifest(rows: list[dict]) -> list[dict]:
    return [
        {
            "bas_dt": p.get("bas_dt"),
            "std_price": p.get("std_price"),
            "chg_pct": p.get("chg_pct"),
        }
        for p in rows
    ]


def _fetch_one_fund(
    client: DisProframeClient,
    fund: dict,
    *,
    quarter: str | None,
    grid_cache: dict[tuple[str, str], list[dict[str, str]]],
    price_days: int = 365,
) -> tuple[dict | None, dict | None, list[str]]:
    fnd_nm = fund["fnd_nm"]
    fund_alias = fund.get("alias") or ""
    warnings: list[str] = []

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
        return None, {"alias": fund_alias, "error": "no_match"}, []

    srtn_cd = match.get("standardCd") or fund.get("srtn_cd") or ""
    if not srtn_cd:
        return None, {"alias": fund_alias, "error": "no_srtn_cd"}, []

    reg = registry_manifest(
        srtn_cd=srtn_cd,
        alias=fund_alias,
        fnd_nm=fnd_nm,
        match=match,
        fund=fund,
    )

    bas_hint = quarter_to_bas_dt_hint(quarter) if quarter else None

    time.sleep(REQUEST_DELAY_SEC)
    periods = inquiry_report_periods(client, srtn_cd)
    period = pick_report_period(periods, bas_dt_hint=bas_hint)
    if not period:
        return (
            None,
            {
                "alias": fund_alias,
                "srtn_cd": srtn_cd,
                "fnd_nm": fnd_nm,
                "registry": reg,
                "error": "no_report_period",
            },
            [],
        )

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
            from dis_std_price import grid_row_to_price_point  # noqa: PLC0415

            single = grid_row_to_price_point(grid_row, srtn_cd=srtn_cd, alias=fund_alias)
            if single:
                price_trend = [single]

    price_trend_month_end = month_end_series_from_trend(price_trend)
    std_price_month_end = latest_month_end_snapshot(price_trend)

    time.sleep(REQUEST_DELAY_SEC)
    std_price_latest = fetch_std_price_latest_business(
        client,
        query,
        srtn_cd,
        grid_cache=grid_cache,
        alias=fund_alias,
        delay_sec=REQUEST_DELAY_SEC,
    )

    bas_dt_fmt = period.get("standardDt", "")
    if len(bas_dt_fmt) == 8:
        bas_dt_fmt = f"{bas_dt_fmt[:4]}-{bas_dt_fmt[4:6]}-{bas_dt_fmt[6:8]}"

    ok_entry = {
        "status": "ok",
        "alias": fund_alias,
        "srtn_cd": srtn_cd,
        "fnd_nm": fnd_nm,
        "registry": reg,
        "quarter": quarter,
        "report_standard_dt": period.get("standardDt"),
        "bas_dt": bas_dt_fmt,
        "price_trend": _price_trend_manifest(price_trend_month_end or price_trend),
        "std_price_month_end": std_price_month_end,
        "std_price_latest": std_price_latest,
    }
    return ok_entry, None, warnings


def run_fetch(
    alias: str | None,
    fund_list_path: Path,
    *,
    quarter: str | None = None,
    quarters: list[str] | None = None,
    all_funds: bool = False,
    price_days: int = 365,
) -> dict:
    funds = load_fund_list(fund_list_path, all_enabled=all_funds)
    if alias:
        funds = [f for f in funds if f.get("alias") == alias]
    if not funds:
        raise SystemExit(f"No funds for alias={alias!r}")

    q_list = quarters or ([quarter] if quarter else [None])
    client = DisProframeClient()
    ok: list[dict] = []
    failed: list[dict] = []
    warnings: list[str] = []
    grid_cache: dict[tuple[str, str], list[dict[str, str]]] = {}

    for q in q_list:
        for fund in funds:
            try:
                o, f, w = _fetch_one_fund(
                    client,
                    fund,
                    quarter=q,
                    grid_cache=grid_cache,
                    price_days=price_days,
                )
                warnings.extend(w)
                if f:
                    f["quarter"] = q
                    failed.append(f)
                    continue
                if o:
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

    has_price_trend = any(f.get("price_trend") for f in ok)

    return {
        "parser_version": PARSER_VERSION,
        "mode": "fetch",
        "quarter": quarter,
        "quarters": q_list,
        "fetched_at": datetime.now(timezone.utc).isoformat(),
        "ok": ok,
        "failed": failed,
        "warnings": warnings,
        "verification": verify_fetch_manifest(
            {"ok": ok, "failed": failed, "mode": "fetch"}
        ),
        "gates": {
            "G1_proframe_reachable": len(ok) > 0,
            "G2_price_trend": has_price_trend,
            "G_portfolio_report": len(ok) > 0,
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
    parser.add_argument("--sync", action="store_true", help="Sync fund list md → fund_list.yaml first")
    parser.add_argument("--dry-run", action="store_true", help="ProFrame connectivity only (G1)")
    parser.add_argument("--fetch", action="store_true", help="Fetch registry and prices (G2)")
    parser.add_argument("--price-days", type=int, default=365, help="Max price history days in portfolio JSON")
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
            price_days=args.price_days,
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
        stats = manifest.get("verification") or verify_fetch_manifest(manifest)
        print(format_verify_report(stats, manifest.get("gates") or {}), file=sys.stderr)

    if args.dry_run:
        return 0 if manifest["gates"]["G1_proframe_reachable"] and not manifest["failed"] else 1

    if args.all_funds and not args.alias:
        ok_n = len(manifest.get("ok") or [])
        failed_n = len(manifest.get("failed") or [])
        if ok_n < 1:
            return 1
        if failed_n and failed_n > ok_n:
            return 1
        gates = manifest.get("gates") or {}
        if not gates.get("G2_price_trend"):
            return 1
        return 0

    gates = manifest["gates"]
    ok_fetch = gates.get("G2_price_trend") and not manifest["failed"]
    return 0 if ok_fetch else 1


if __name__ == "__main__":
    raise SystemExit(main())
