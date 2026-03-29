"""
FastAPI application factory for the Telegram Mini App API.
"""

import logging
import os
from pathlib import Path

from dotenv import load_dotenv
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from interfaces.webapp.routes import oauth, settings, usage

# Load .env from project root
project_root = Path(__file__).parent.parent.parent
load_dotenv(project_root / ".env")

logger = logging.getLogger(__name__)


def create_app() -> FastAPI:
    # Check if docs should be disabled (production security)
    disable_docs = os.getenv("DISABLE_SWAGGER", "").lower() == "true"

    app = FastAPI(
        title="TG Bot Mini App API",
        description="API for Telegram Mini App settings, OAuth, and usage monitoring",
        version="1.0.0",
        docs_url=None if disable_docs else "/docs",
        redoc_url=None if disable_docs else "/redoc",
        openapi_url=None if disable_docs else "/openapi.json",
    )

    app.add_middleware(
        CORSMiddleware,
        allow_origins=["*"],  # Tighten via CORS_ORIGINS env var in production
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    app.include_router(settings.router, prefix="/api/v1", tags=["settings"])
    app.include_router(oauth.router, prefix="/api/v1", tags=["oauth"])
    app.include_router(usage.router, prefix="/api/v1", tags=["usage"])

    # Add security scheme for Swagger UI
    if not disable_docs:
        app.openapi_schema = app.openapi()
        if app.openapi_schema:
            app.openapi_schema["components"]["securitySchemes"] = {
                "TelegramInitData": {
                    "type": "apiKey",
                    "in": "header",
                    "name": "X-Telegram-Init-Data",
                    "description": "Telegram WebApp initData for authentication",
                }
            }
            # Add security requirement globally (optional for most endpoints)
            for path in app.openapi_schema["paths"].values():
                for operation in path.values():
                    if "security" not in operation:
                        operation["security"] = [{"TelegramInitData": []}]

    return app


app = create_app()
