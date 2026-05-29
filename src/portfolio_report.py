"""Build portfolio-wide analysis JSON from fetch manifest."""

from __future__ import annotations

import json
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
REPORTS_DIR = ROOT / "data" / "reports"


def _error_summary(failed: list[dict]) -> dict[str, int]:
    c: Counter[str] = Counter()
    for f in failed:
        c[str(f.get("error", "unknown"))] += 1
    return dict(c)


def build_portfolio_report(
    manifest: dict[str, Any],
    *,
    fund_list_path: Path,
    funds_meta: list[dict] | None = None,
) -> dict[str, Any]:
    ok_list = manifest.get("ok") or []
    failed = manifest.get("failed") or []
    fund_count = len(funds_meta) if funds_meta else len(ok_list) + len(failed)

    return {
        "meta": {
            "source": str(fund_list_path.relative_to(ROOT)).replace("\\", "/"),
            "fund_count": fund_count,
            "fetched_at": manifest.get("fetched_at"),
            "parser_version": manifest.get("parser_version"),
            "mode": manifest.get("mode"),
        },
        "summary": {
            "ok": len(ok_list),
            "failed": len(failed),
            "errors": _error_summary(failed),
            "warnings": manifest.get("warnings") or [],
        },
        "funds": ok_list,
        "failed_funds": failed,
        "verification": manifest.get("verification") or {},
        "gates": manifest.get("gates") or {},
    }


def write_portfolio_report(
    manifest: dict[str, Any],
    *,
    fund_list_path: Path,
    funds_meta: list[dict] | None = None,
) -> Path:
    REPORTS_DIR.mkdir(parents=True, exist_ok=True)
    report = build_portfolio_report(manifest, fund_list_path=fund_list_path, funds_meta=funds_meta)
    stamp = datetime.now(timezone.utc).strftime("%Y%m%d")
    out = REPORTS_DIR / f"fund_portfolio_analysis_{stamp}.json"
    out.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    return out
