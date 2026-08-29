from __future__ import annotations

import argparse
import json
from datetime import date
from pathlib import Path

from app.db.session import get_engine, get_session_factory, init_db
from app.services.ingest import ingest_trade_date


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Ingest one Taiwan trading date from TWSE and TPEx.")
    parser.add_argument("--date", required=True, help="YYYY-MM-DD")
    parser.add_argument("--database-url", default=None)
    parser.add_argument("--payload-dir", default="data/raw_payloads")
    parser.add_argument("--mapping", default="data/theme_mapping/seed_themes.csv")
    args = parser.parse_args(argv)
    trade_date = date.fromisoformat(args.date)
    engine = get_engine(args.database_url) if args.database_url else get_engine()
    init_db(engine)
    factory = get_session_factory(engine)
    session = factory()
    try:
        result = ingest_trade_date(
            session,
            trade_date,
            payload_dir=Path(args.payload_dir),
            mapping_path=Path(args.mapping),
        )
        session.commit()
    except Exception:
        session.rollback()
        raise
    finally:
        session.close()
    payload = {
        "trade_date": result.trade_date.isoformat(),
        "skipped_holiday": result.skipped_holiday,
        "warmup_complete": result.warmup_complete,
        "sectors_scored": result.sectors_scored,
        "providers": {
            name: {
                "quotes": p.quotes,
                "flows": p.flows,
                "margins": p.margins,
                "holiday": p.holiday,
                "error": p.error,
            }
            for name, p in result.providers.items()
        },
        "issues": [
            {"code": i.code, "severity": i.severity, "message": i.message}
            for i in (result.validation.issues if result.validation else [])
        ],
    }
    print(json.dumps(payload, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
