from collections.abc import Generator

from sqlalchemy import create_engine, inspect, text
from sqlalchemy.engine import Engine
from sqlalchemy.orm import Session, sessionmaker

from app.core.config import get_settings
from app.models.entities import Base, MappingCatalog, SecurityTheme

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
    """Add columns / rebuild tables introduced after the first SQLite file was created."""
    if engine.dialect.name != "sqlite":
        return
    _rebuild_mapping_catalog(engine)
    _rebuild_security_themes(engine)
    additions = {
        "themes": [
            ("mapping_version", "VARCHAR(32)"),
            ("mapping_source", "VARCHAR(255)"),
            ("effective_from", "DATE"),
            ("effective_to", "DATE"),
            ("theme_level", "INTEGER"),
            ("parent_theme_id", "VARCHAR(32)"),
            ("theme_category", "VARCHAR(32)"),
            ("concentrated_ok", "BOOLEAN DEFAULT 0 NOT NULL"),
        ],
        "sector_daily_metrics": [
            ("member_count", "INTEGER"),
            ("priced_member_count", "INTEGER"),
            ("flow_member_count", "INTEGER"),
            ("coverage_ratio", "NUMERIC(18, 8)"),
            ("low_coverage", "BOOLEAN DEFAULT 0 NOT NULL"),
            ("thin_membership", "BOOLEAN DEFAULT 0 NOT NULL"),
            ("rank_excluded", "BOOLEAN DEFAULT 0 NOT NULL"),
            ("mapping_version", "VARCHAR(32)"),
        ],
    }
    inspector = inspect(engine)
    tables = set(inspector.get_table_names())
    with engine.begin() as conn:
        for table, columns in additions.items():
            if table not in tables:
                continue
            existing = {c["name"] for c in inspect(engine).get_columns(table)}
            for name, ddl in columns:
                if name in existing:
                    continue
                conn.execute(text(f"ALTER TABLE {table} ADD COLUMN {name} {ddl}"))


def _rebuild_mapping_catalog(engine: Engine) -> None:
    inspector = inspect(engine)
    if "mapping_catalog" not in inspector.get_table_names():
        return
    cols = {c["name"] for c in inspector.get_columns("mapping_catalog")}
    pk = inspector.get_pk_constraint("mapping_catalog").get("constrained_columns") or []
    if "mapping_version" in cols and pk == ["mapping_version"]:
        return
    with engine.begin() as conn:
        conn.execute(text("ALTER TABLE mapping_catalog RENAME TO mapping_catalog_legacy"))
    MappingCatalog.__table__.create(engine)
    with engine.begin() as conn:
        if "mapping_version" in cols:
            conn.execute(
                text(
                    "INSERT OR IGNORE INTO mapping_catalog "
                    "(mapping_version, mapping_source, effective_from, effective_to, production_ready, notes) "
                    "SELECT mapping_version, mapping_source, effective_from, NULL, production_ready, notes "
                    "FROM mapping_catalog_legacy"
                )
            )
        conn.execute(text("DROP TABLE mapping_catalog_legacy"))


def _rebuild_security_themes(engine: Engine) -> None:
    inspector = inspect(engine)
    if "security_themes" not in inspector.get_table_names():
        return
    cols = {c["name"] for c in inspector.get_columns("security_themes")}
    pk = inspector.get_pk_constraint("security_themes").get("constrained_columns") or []
    if "mapping_version" in cols and set(pk) == {"security_id", "theme_id", "mapping_version"}:
        return
    with engine.begin() as conn:
        conn.execute(text("ALTER TABLE security_themes RENAME TO security_themes_legacy"))
    SecurityTheme.__table__.create(engine)
    with engine.begin() as conn:
        conn.execute(
            text(
                "INSERT OR IGNORE INTO security_themes "
                "(security_id, theme_id, mapping_version, inherited) "
                "SELECT security_id, theme_id, 'seed-v1', 0 FROM security_themes_legacy"
            )
        )
        conn.execute(text("DROP TABLE security_themes_legacy"))


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
