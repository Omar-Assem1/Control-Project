"""
app/__init__.py
---------------
Creates and configures the FastAPI application instance.
"""

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.api import graph_router


def create_app() -> FastAPI:
    app = FastAPI(
        title="Signal Flow Graph Analyzer",
        description=(
            "REST API that applies Mason's Gain Formula to a directed "
            "Signal Flow Graph and returns forward paths, loops, the "
            "graph determinant Δ, cofactors Δₖ, and the transfer function T(s)."
        ),
        version="1.0.0",
        docs_url="/docs",
        redoc_url="/redoc",
    )

    # ── CORS ──────────────────────────────────────────────────────────────
    # Allow the Angular dev-server (port 4200) and any other local origin.
    app.add_middleware(
        CORSMiddleware,
        allow_origins=[
            "http://localhost:4200",
            "http://127.0.0.1:4200",
            "http://localhost:4201",
        ],
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    # ── Routers ───────────────────────────────────────────────────────────
    app.include_router(graph_router)

    # ── Health check ──────────────────────────────────────────────────────
    @app.get("/health", tags=["Health"], summary="Health check")
    def health() -> dict:
        return {"status": "ok", "service": "sfg-analyzer"}

    return app


# Module-level app instance (used by uvicorn)
app = create_app()
