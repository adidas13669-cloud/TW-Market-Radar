from __future__ import annotations

import argparse
import json
from datetime import date
from pathlib import Path

from app.db.session import get_engine, get_session_factory, init_db
from app.services.audit import build_audit_report, format_audit_report, write_audit


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Audit ingested TW-Market-Radar snapshots.")
    parser.add_argument("--date", default=None, help="YYYY-MM-DD as-of date (default: latest session)")
    parser.add_argument("--database-url", default=None)
    parser.add_argument("--json", action="store_true", help="Print JSON instead of the text report")
    parser.add_argument("--out", default=None, help="Optional JSON output path")
    args = parser.parse_args(argv)
    asof = date.fromisoformat(args.date) if args.date else None
    engine = get_engine(args.database_url) if args.database_url else get_engine()
    init_db(engine)
    factory = get_session_factory(engine)
    session = factory()
    try:
        report = build_audit_report(session, asof=asof)
    finally:
        session.close()
    if args.out:
        write_audit(Path(args.out), report)
    if args.json:
        print(json.dumps(report, ensure_ascii=False, indent=2, default=str))
    else:
        print(format_audit_report(report))
    return 0 if report.get("invariants_ok", True) else 1


if __name__ == "__main__":
    raise SystemExit(main())
