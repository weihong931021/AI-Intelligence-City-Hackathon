"""LandLens API（dev.md §6.1 單一 FastAPI）。本機：uvicorn app.main:app --reload --port 8000"""

from __future__ import annotations

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.api.chat import router as chat_router
from app.api.extraction import router as extraction_router
from app.extraction import Extractor, make_extractor
from app.llm.bedrock import Streamer, make_bedrock_streamer
from app.settings import get_settings


def create_app(streamer: Streamer | None = None, extractor: Extractor | None = None) -> FastAPI:
    settings = get_settings()
    app = FastAPI(title="LandLens API")
    app.add_middleware(
        CORSMiddleware, allow_origins=settings.cors_origins, allow_methods=["*"], allow_headers=["*"]
    )
    app.state.settings = settings
    app.state.streamer = streamer or make_bedrock_streamer(settings.model_id, settings.region, settings.max_tokens)
    app.state.extractor = extractor or make_extractor(settings.model_id, settings.region)
    app.include_router(chat_router)
    app.include_router(extraction_router)

    @app.get("/api/health")
    def health() -> dict:
        return {"ok": True, "model": settings.model_id, "region": settings.region}

    return app


app = create_app()
