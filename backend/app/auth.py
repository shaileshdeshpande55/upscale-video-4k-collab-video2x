"""Bearer-token authentication for the backend."""

from __future__ import annotations

import secrets
from typing import Callable

from fastapi import Depends, HTTPException, Request, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer

_bearer = HTTPBearer(auto_error=False)


def make_auth(settings) -> Callable:
    async def _auth(request: Request, credentials: HTTPAuthorizationCredentials | None = Depends(_bearer)):
        if not settings.api_token:
            if settings.allow_insecure:
                return
            raise HTTPException(
                status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                detail="API token not configured",
            )
        if credentials is None or not secrets.compare_digest(credentials.credentials, settings.api_token):
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Invalid or missing bearer token",
                headers={"WWW-Authenticate": "Bearer"},
            )
    return _auth
