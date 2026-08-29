from __future__ import annotations

import argparse
import json
from datetime import date
from pathlib import Path

from app.db.session import get_engine, get_session_factory, init_db
from app.services.ingest import backfill
from app.services.persistence import recompute


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Backfill TWSE/TPEx sessions over a date range.")
    parser.add_argument("--start", required=True, help="YYYY-MM-DD")
    parser.add_argument("--end", required=True, help="YYYY-MM-DD")
    parser.add_argument("--database-url", default=None)
    parser.add_argument("--payload-dir", default="data/raw_payloads")
    parser.add_argument("--mapping", default="data/theme_mapping/seed_themes.csv")
    parser.add_argument("--force", action="store_true", help="Re-fetch dates already marked SUCCESS")
    args = parser.parse_args(argv)
    start = date.fromisoformat(args.start)
    end = date.fromisoformat(args.end)
    engine = get_engine(args.database_url) if args.database_url else get_engine()
    init_db(engine)
    factory = get_session_factory(engine)
    session = factory()
    try:
        results = backfill(
            session,
            start,
            end,
            payload_dir=Path(args.payload_dir),
            mapping_path=Path(args.mapping),
            continue_on_provider_error=True,
            recompute_metrics=False,
            skip_if_success=not args.force,
            force=args.force,
            commit_each=True,
        )
        recompute(session)
        session.commit()
    except Exception:
        session.rollback()
        raise
    finally:
        session.close()
    summary = [
        {
            "trade_date": r.trade_date.isoformat(),
            "status": r.status.value,
            "holiday": r.skipped_holiday,
            "twse_quotes": r.providers.get("TWSE").quotes if r.providers.get("TWSE") else 0,
            "tpex_quotes": r.providers.get("TPEX").quotes if r.providers.get("TPEX") else 0,
            "twse_error": r.providers.get("TWSE").error if r.providers.get("TWSE") else None,
            "tpex_error": r.providers.get("TPEX").error if r.providers.get("TPEX") else None,
            "sectors_scored": r.sectors_scored,
            "warmup_complete": r.warmup_complete,
        }
        for r in results
    ]
    counts: dict[str, int] = {}
    for row in summary:
        counts[row["status"]] = counts.get(row["status"], 0) + 1
    print(json.dumps({"weekdays_visited": len(summary), "status_counts": counts, "results": summary}, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
