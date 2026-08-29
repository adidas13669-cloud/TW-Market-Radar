from __future__ import annotations

import argparse
import json
from datetime import date
from pathlib import Path

from app.db.session import get_engine, get_session_factory, init_db
from app.services.ingest import backfill


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Backfill TWSE/TPEx sessions over a date range.")
    parser.add_argument("--start", required=True, help="YYYY-MM-DD")
    parser.add_argument("--end", required=True, help="YYYY-MM-DD")
    parser.add_argument("--database-url", default=None)
    parser.add_argument("--payload-dir", default="data/raw_payloads")
    parser.add_argument("--mapping", default="data/theme_mapping/seed_themes.csv")
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
        )
        session.commit()
    except Exception:
        session.rollback()
        raise
    finally:
        session.close()
    summary = [
        {
            "trade_date": r.trade_date.isoformat(),
            "holiday": r.skipped_holiday,
            "twse_quotes": r.providers.get("TWSE").quotes if r.providers.get("TWSE") else 0,
            "tpex_quotes": r.providers.get("TPEX").quotes if r.providers.get("TPEX") else 0,
            "sectors_scored": r.sectors_scored,
            "warmup_complete": r.warmup_complete,
        }
        for r in results
    ]
    print(json.dumps({"sessions": len(summary), "results": summary}, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
