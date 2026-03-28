"""
FastAPI application factory for the Telegram Mini App API.
"""

import logging

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from interfaces.webapp.routes import oauth, settings, usage

logger = logging.getLogger(__name__)


def create_app() -> FastAPI:
    app = FastAPI(
        title="TG Bot Mini App API",
        version="1.0.0",
    )

    app.add_middleware(
        CORSMiddleware,
        allow_origins=["*"],  # Tighten via CORS_ORIGINS env var in production
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    app.include_router(settings.router, prefix="/api/v1")
    app.include_router(oauth.router, prefix="/api/v1")
    app.include_router(usage.router, prefix="/api/v1", tags=["usage"])

    return app


app = create_app()
