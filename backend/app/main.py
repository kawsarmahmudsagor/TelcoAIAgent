from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.api import (
    routes_agent_config,
    routes_auth,
    routes_bookings,
    routes_conversations,
    routes_dashboard,
    routes_import,
    routes_leads,
    routes_offers,
    routes_properties,
    routes_public,
    routes_public_conversations,
    routes_rag,
    routes_schedule,
)
from app.config import get_settings


def create_app() -> FastAPI:
    settings = get_settings()
    app = FastAPI(title="Real Estate Agent Backend")

    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.cors_origins,
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    app.include_router(routes_auth.router)
    app.include_router(routes_leads.router)
    app.include_router(routes_properties.router)
    app.include_router(routes_offers.router)
    app.include_router(routes_schedule.router)
    app.include_router(routes_bookings.router)
    app.include_router(routes_dashboard.router)
    app.include_router(routes_import.router)
    app.include_router(routes_agent_config.router)
    app.include_router(routes_conversations.router)
    app.include_router(routes_public.router)
    app.include_router(routes_public_conversations.router)
    app.include_router(routes_rag.router)

    @app.get("/health")
    def health() -> dict:
        return {"status": "ok"}

    return app


app = create_app()
