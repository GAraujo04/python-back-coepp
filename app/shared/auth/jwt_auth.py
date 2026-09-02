"""Dependências de autenticação/autorização (RBAC) no boundary HTTP.

Porta shared/auth/jwt-plugin.ts. No Fastify isso era um plugin que
decorava `app.authenticate`/`app.authorize(roles)` como preHandlers; no
FastAPI o equivalente idiomático é *dependency injection*:
`Depends(get_current_user)` no lugar de `preHandler: [app.authenticate]`,
`Depends(require_role([...]))` no lugar de `preHandler: [app.authorize([...])]`.

Esta é a camada de RBAC no boundary HTTP. A verificação de VÍNCULO
(estagiário↔paciente) e a RLS do banco são camadas adicionais (defesa em
profundidade) — inalteradas por esta migração.
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass

import jwt
from fastapi import Depends
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer

from ..config.env import load_env
from ..errors.app_error import ForbiddenError, UnauthorizedError

_bearer_scheme = HTTPBearer(auto_error=False)


@dataclass(frozen=True)
class CurrentUser:
    sub: str
    role: str
    email: str


def get_current_user(
    credentials: HTTPAuthorizationCredentials | None = Depends(_bearer_scheme),
) -> CurrentUser:
    if credentials is None:
        raise UnauthorizedError("Token de acesso ausente ou inválido.")
    try:
        payload = jwt.decode(credentials.credentials, load_env().JWT_SECRET, algorithms=["HS256"])
    except jwt.PyJWTError as exc:
        raise UnauthorizedError("Token de acesso ausente ou inválido.") from exc
    return CurrentUser(sub=payload["sub"], role=payload["role"], email=payload["email"])


def require_role(roles: list[str]) -> Callable[[CurrentUser], CurrentUser]:
    """Fábrica de dependência — equivalente a `app.authorize(roles)`."""

    def _check(user: CurrentUser = Depends(get_current_user)) -> CurrentUser:
        if user.role not in roles:
            raise ForbiddenError("Permissão insuficiente para este recurso.")
        return user

    return _check
