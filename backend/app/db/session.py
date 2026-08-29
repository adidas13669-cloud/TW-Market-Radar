from collections.abc import Generator

from sqlalchemy import create_engine, inspect, text
from sqlalchemy.engine import Engine
from sqlalchemy.orm import Session, sessionmaker

from app.core.config import get_settings
from app.models.entities import Base

_engine: Engine | None = None
_SessionLocal: sessionmaker[Session] | None = None


def get_engine(url: str | None = None) -> Engine:
    global _engine
    db_url = url or get_settings().database_url
    if _engine is None or str(_engine.url) != db_url.replace("sqlite:///", "sqlite:///"):
        connect_args = {"check_same_thread": False} if db_url.startswith("sqlite") else {}
        _engine = create_engine(db_url, future=True, connect_args=connect_args)
    return _engine


def get_session_factory(engine: Engine | None = None) -> sessionmaker[Session]:
    global _SessionLocal
    eng = engine or get_engine()
    _SessionLocal = sessionmaker(bind=eng, autoflush=False, autocommit=False, future=True)
    return _SessionLocal


def init_db(engine: Engine | None = None) -> None:
    eng = engine or get_engine()
    Base.metadata.create_all(bind=eng)
    migrate_sqlite_columns(eng)


def migrate_sqlite_columns(engine: Engine) -> None:
    """Add columns introduced after the first SQLite file was created."""
    if engine.dialect.name != "sqlite":
        return
    additions = {
        "themes": [
            ("mapping_version", "VARCHAR(32)"),
            ("mapping_source", "VARCHAR(255)"),
            ("effective_from", "DATE"),
        ],
        "sector_daily_metrics": [
            ("member_count", "INTEGER"),
            ("priced_member_count", "INTEGER"),
            ("flow_member_count", "INTEGER"),
            ("coverage_ratio", "NUMERIC(18, 8)"),
            ("low_coverage", "BOOLEAN DEFAULT 0 NOT NULL"),
        ],
    }
    inspector = inspect(engine)
    tables = set(inspector.get_table_names())
    with engine.begin() as conn:
        for table, columns in additions.items():
            if table not in tables:
                continue
            existing = {c["name"] for c in inspector.get_columns(table)}
            for name, ddl in columns:
                if name in existing:
                    continue
                conn.execute(text(f"ALTER TABLE {table} ADD COLUMN {name} {ddl}"))


def get_db() -> Generator[Session, None, None]:
    factory = get_session_factory()
    session = factory()
    try:
        yield session
        session.commit()
    except Exception:
        session.rollback()
        raise
    finally:
        session.close()
