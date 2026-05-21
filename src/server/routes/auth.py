from __future__ import annotations

from typing import Any

from fastapi import APIRouter, HTTPException, Request
from pydantic import BaseModel, Field

from server.auth import AuthService, bearer_token_from_request


router = APIRouter(prefix="/api/auth", tags=["auth"])


class LoginRequest(BaseModel):
    username: str = Field(min_length=1)
    password: str = Field(min_length=1)


def get_auth_service(request: Request) -> AuthService:
    service = getattr(request.app.state, "auth_service", None)
    if service is None:
        raise RuntimeError("Auth service is not initialized.")
    return service


@router.get("/session")
async def get_auth_session(request: Request) -> dict[str, Any]:
    service = get_auth_service(request)
    return {"auth": service.session_for_token(bearer_token_from_request(request)).to_dict()}


@router.post("/login")
async def login(request: Request, payload: LoginRequest) -> dict[str, Any]:
    service = get_auth_service(request)
    try:
        token, session = service.login(username=payload.username, password=payload.password)
    except ValueError as exc:
        raise HTTPException(status_code=401, detail=str(exc)) from exc
    return {"token": token, "auth": session.to_dict()}


@router.post("/logout")
async def logout(request: Request) -> dict[str, Any]:
    service = get_auth_service(request)
    return {"auth": service.logout(bearer_token_from_request(request)).to_dict()}
