"""
GuardedContext -- independent research prototype.

Not affiliated with, and does not connect to, Saela or any other named
company or product. Built entirely from public research to demonstrate
an AI-safety/guardrail architecture pattern (typed schemas, multi-agent
orchestration, multi-provider fallback) relevant to that research.
"""
from pathlib import Path

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles

from .config import get_settings
from .db import init_db
from .routers import batch, evaluate, history, samples

BASE_DIR = Path(__file__).resolve().parent.parent.parent  # .../guardedcontext
FRONTEND_DIR = BASE_DIR / "frontend"

app = FastAPI(
    title="GuardedContext",
    description=(
        "Independent research prototype demonstrating a guardrail + "
        "multi-provider-routing evaluation layer for women's-health AI "
        "answers. Not medical advice. Not affiliated with any named company."
    ),
    version="0.1.0",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.on_event("startup")
def on_startup() -> None:
    init_db()


app.include_router(evaluate.router, tags=["evaluate"])
app.include_router(samples.router, tags=["samples"])
app.include_router(history.router, tags=["history"])
app.include_router(batch.router, tags=["batch"])


@app.get("/health")
def health() -> dict:
    settings = get_settings()
    return {"status": "ok", "auth_required": bool(settings.demo_access_code)}


if FRONTEND_DIR.exists():
    app.mount("/static", StaticFiles(directory=str(FRONTEND_DIR)), name="static")

    @app.get("/")
    def serve_index() -> FileResponse:
        return FileResponse(str(FRONTEND_DIR / "index.html"))
