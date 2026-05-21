from __future__ import annotations

from dataclasses import dataclass
import hmac
import json
import secrets
from pathlib import Path
from typing import Any

from fastapi import Request

from agent.settings import Settings


AUTH_CONFIG_FILENAME = "control-center-auth.json"


@dataclass(frozen=True, slots=True)
class AuthConfig:
    enabled: bool = False
    username: str = "admin"
    password: str = "change-me"

    @classmethod
    def from_file(cls, path: Path) -> "AuthConfig":
        if not path.exists():
            return cls(enabled=False)
        payload = json.loads(path.read_text(encoding="utf-8"))
        if not isinstance(payload, dict):
            raise ValueError("auth config must be a JSON object.")
        return cls(
            enabled=bool(payload.get("enabled", False)),
            username=_required_text(payload.get("username"), field_name="username"),
            password=_required_text(payload.get("password"), field_name="password"),
        )


@dataclass(frozen=True, slots=True)
class AuthSession:
    enabled: bool
    authenticated: bool
    username: str | None = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "enabled": self.enabled,
            "authenticated": self.authenticated,
            "username": self.username,
        }


class AuthService:
    def __init__(self, *, config: AuthConfig) -> None:
        self.config = config
        self._tokens: dict[str, str] = {}

    @classmethod
    def from_settings(cls, settings: Settings) -> "AuthService":
        return cls(config=AuthConfig.from_file(settings.config_dir / AUTH_CONFIG_FILENAME))

    @property
    def enabled(self) -> bool:
        return self.config.enabled

    def session_for_token(self, token: str | None) -> AuthSession:
        if not self.enabled:
            return AuthSession(enabled=False, authenticated=True)
        username = self._tokens.get(token or "")
        return AuthSession(enabled=True, authenticated=username is not None, username=username)

    def login(self, *, username: str, password: str) -> tuple[str | None, AuthSession]:
        if not self.enabled:
            return None, AuthSession(enabled=False, authenticated=True)
        if not (
            hmac.compare_digest(username, self.config.username)
            and hmac.compare_digest(password, self.config.password)
        ):
            raise ValueError("Invalid username or password.")
        token = secrets.token_urlsafe(32)
        self._tokens[token] = self.config.username
        return token, AuthSession(enabled=True, authenticated=True, username=self.config.username)

    def logout(self, token: str | None) -> AuthSession:
        if token:
            self._tokens.pop(token, None)
        return self.session_for_token(None)

    def is_authorized(self, token: str | None) -> bool:
        return self.session_for_token(token).authenticated


def bearer_token_from_request(request: Request) -> str | None:
    header = request.headers.get("authorization")
    return bearer_token_from_header(header)


def bearer_token_from_header(header: str | None) -> str | None:
    if not header:
        return None
    scheme, _, token = header.partition(" ")
    if scheme.lower() != "bearer" or not token.strip():
        return None
    return token.strip()


def _required_text(value: object, *, field_name: str) -> str:
    if not isinstance(value, str) or not value:
        raise ValueError(f"{field_name} must be a non-empty string.")
    return value
