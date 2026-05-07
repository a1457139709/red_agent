from __future__ import annotations

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from .lifecycle import lifespan
from .routes.agent import router as agent_router
from .routes.health import router as health_router
from .routes.projects import router as projects_router
from .routes.tasks import router as tasks_router
from .routes.tools import router as tools_router
from .ws import router as ws_router


LOCAL_DEV_ORIGINS = (
    "http://localhost:5173",
    "http://127.0.0.1:5173",
    "tauri://localhost",
)


def create_app() -> FastAPI:
    app = FastAPI(
        title="red-code Control Center",
        version="0.1.0",
        lifespan=lifespan,
    )
    app.add_middleware(
        CORSMiddleware,
        allow_origins=list(LOCAL_DEV_ORIGINS),
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )
    app.include_router(health_router)
    app.include_router(projects_router)
    app.include_router(tasks_router)
    app.include_router(agent_router)
    app.include_router(tools_router)
    app.include_router(ws_router)
    return app
