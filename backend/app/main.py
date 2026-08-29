from fastapi import FastAPI

from app.api.health import router as health_router
from app.api.radar import router as radar_router
from app.db.session import get_engine, init_db


def create_app() -> FastAPI:
    app = FastAPI(
        title="TW Market Radar",
        version="0.1.0",
        description="Taiwan sector rotation radar — institutional flow and scoring API.",
    )
    app.include_router(health_router)
    app.include_router(radar_router)

    @app.on_event("startup")
    def _startup() -> None:
        init_db(get_engine())

    return app


app = create_app()
