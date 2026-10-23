from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.api import (
    routes_admin,
    routes_agent_config,
    routes_auth,
    routes_conversations,
    routes_dashboard,
    routes_demo,
    routes_me,
    routes_me_actions,
    routes_public_conversations,
    routes_rag,
)
from app.config import get_settings


def create_app() -> FastAPI:
    settings = get_settings()
    app = FastAPI(title="Telco AI Agent Backend")

    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.cors_origins,
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    app.include_router(routes_auth.router)
    app.include_router(routes_admin.router)
    app.include_router(routes_dashboard.router)
    app.include_router(routes_agent_config.router)
    app.include_router(routes_conversations.router)
    app.include_router(routes_public_conversations.router)
    app.include_router(routes_rag.router)
    app.include_router(routes_demo.router)
    app.include_router(routes_me.router)
    app.include_router(routes_me_actions.router)

    @app.get("/health")
    def health() -> dict:
        return {"status": "ok"}

    return app


app = create_app()
