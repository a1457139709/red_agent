from __future__ import annotations

import json
import logging
import time

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from starlette.middleware.base import RequestResponseEndpoint
from starlette.requests import Request
from starlette.responses import Response

from .lifecycle import lifespan
from .routes.agent import router as agent_router
from .routes.auth import router as auth_router
from .routes.health import router as health_router
from .routes.projects import router as projects_router
from .routes.reports import router as reports_router
from .routes.tasks import router as tasks_router
from .routes.terminal import router as terminal_router
from .routes.tools import router as tools_router
from .routes.workspace import router as workspace_router
from .ws import router as ws_router


LOCAL_DEV_ORIGINS = (
    "http://localhost:5173",
    "http://127.0.0.1:5173",
    "tauri://localhost",
)

AUTH_EXEMPT_PATHS = {
    "/api/health",
    "/api/auth/session",
    "/api/auth/login",
}
logger = logging.getLogger("red_code.control_center")


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
    app.middleware("http")(_request_auth_and_logging_middleware)
    app.include_router(health_router)
    app.include_router(auth_router)
    app.include_router(projects_router)
    app.include_router(reports_router)
    app.include_router(tasks_router)
    app.include_router(agent_router)
    app.include_router(tools_router)
    app.include_router(terminal_router)
    app.include_router(workspace_router)
    app.include_router(ws_router)
    return app


async def _request_auth_and_logging_middleware(request: Request, call_next: RequestResponseEndpoint) -> Response:
    started_at = time.perf_counter()
    status_code = 500
    error: str | None = None
    try:
        auth_response = _authorize_api_request(request)
        if auth_response is not None:
            status_code = auth_response.status_code
            return auth_response
        response = await call_next(request)
        status_code = response.status_code
        return response
    except Exception as exc:
        error = exc.__class__.__name__
        raise
    finally:
        route = getattr(request.scope.get("route"), "path", request.url.path)
        logger.info(
            json.dumps(
                {
                    "event": "http.request",
                    "method": request.method,
                    "route": route,
                    "path": request.url.path,
                    "status": status_code,
                    "duration_ms": round((time.perf_counter() - started_at) * 1000, 2),
                    "error": error,
                },
                ensure_ascii=False,
            )
        )


def _authorize_api_request(request: Request) -> Response | None:
    if request.method == "OPTIONS" or not request.url.path.startswith("/api/"):
        return None
    if request.url.path in AUTH_EXEMPT_PATHS:
        return None
    service = getattr(request.app.state, "auth_service", None)
    if service is None or not service.enabled:
        return None
    header = request.headers.get("authorization")
    scheme, _, token = (header or "").partition(" ")
    if scheme.lower() == "bearer" and service.is_authorized(token.strip()):
        return None
    return JSONResponse({"detail": "Authentication required."}, status_code=401)
