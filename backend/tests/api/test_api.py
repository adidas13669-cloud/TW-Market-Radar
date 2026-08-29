from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.db.session import get_db
from app.main import create_app
from app.models.entities import Base
from app.services.persistence import recompute
from tests.fixtures.market import seed_snapshot, synthetic_snapshot


def _client():
    engine = create_engine(
        "sqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
        future=True,
    )
    Base.metadata.create_all(engine)
    factory = sessionmaker(bind=engine, autoflush=False, autocommit=False, future=True)
    session = factory()
    seed_snapshot(session, synthetic_snapshot(25))
    recompute(session)
    session.commit()

    def override_db():
        try:
            yield session
        finally:
            pass

    app = create_app()
    app.dependency_overrides[get_db] = override_db
    return TestClient(app), session


def test_health():
    client, _ = _client()
    response = client.get("/health")
    assert response.status_code == 200
    assert response.json()["status"] == "ok"


def test_latest_radar_and_emerging_and_history():
    client, _ = _client()
    latest = client.get("/api/v1/radar/sectors/latest")
    assert latest.status_code == 200
    body = latest.json()
    assert len(body) == 3
    assert {row["theme_id"] for row in body} == {"SEMI", "AI", "SHIP"}
    assert all(0 <= row["rotation_score"] <= 100 for row in body)

    emerging = client.get("/api/v1/radar/emerging")
    assert emerging.status_code == 200
    assert len(emerging.json()) == 3

    detail = client.get("/api/v1/radar/sectors/SEMI")
    assert detail.status_code == 200
    payload = detail.json()
    assert payload["sector"]["theme_id"] == "SEMI"
    ids = {c["security_id"] for c in payload["constituents"]}
    assert ids == {"2330", "2454"}

    history = client.get("/api/v1/radar/sectors/SEMI/history?sessions=20")
    assert history.status_code == 200
    sessions = history.json()["sessions"]
    assert len(sessions) == 20

    divergence = client.get("/api/v1/radar/divergence")
    assert divergence.status_code == 200
    assert isinstance(divergence.json(), list)

    meta = client.get("/api/v1/radar/meta")
    assert meta.status_code == 200
    assert meta.json()["session_dates"]
    assert meta.json()["themes"]

    latest_l3 = client.get("/api/v1/radar/sectors/latest?theme_level=3")
    assert latest_l3.status_code == 200
    assert {row["theme_id"] for row in latest_l3.json()} == {"SEMI", "AI", "SHIP"}
    assert all(row.get("theme_level") == 3 for row in latest_l3.json())
    assert "score_delta" in latest_l3.json()[0]

