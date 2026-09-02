"""Renova a sessão: valida o refresh token, rotaciona-o (revoga o antigo,
emite novo — mitiga replay) e assina um novo access token.

Porta features/auth/application/refresh-session.ts.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime

from ....shared.audit.audit_recorder import AuditEvent, AuditRecorder
from ....shared.errors.app_error import UnauthorizedError
from ..domain.user_repository import UserRepository
from .ports import AccessTokenPayload, AccessTokenSigner, RefreshSessionMeta, RefreshTokenStore


@dataclass
class RefreshInput:
    refresh_token: str
    meta: RefreshSessionMeta
    correlation_id: str | None = None


@dataclass
class RefreshOutput:
    access_token: str
    refresh_token: str
    refresh_expires_at: datetime


class RefreshSession:
    def __init__(
        self,
        users: UserRepository,
        access_tokens: AccessTokenSigner,
        refresh_tokens: RefreshTokenStore,
        audit: AuditRecorder,
    ) -> None:
        self._users = users
        self._access_tokens = access_tokens
        self._refresh_tokens = refresh_tokens
        self._audit = audit

    def execute(self, input: RefreshInput) -> RefreshOutput:
        user_id, issued = self._refresh_tokens.rotate(input.refresh_token, input.meta)
        user = self._users.find_by_id(user_id)
        if not user or not user.can_authenticate():
            self._refresh_tokens.revoke(issued.token)
            raise UnauthorizedError("Sessão inválida.")

        access_token = self._access_tokens.sign(AccessTokenPayload(sub=user.id, role=user.role, email=user.email.value))

        self._audit.record(
            AuditEvent(
                actor_id=user.id,
                action="REFRESH",
                resource_type="auth",
                resource_id=user.id,
                correlation_id=input.correlation_id,
                ip=input.meta.ip,
                user_agent=input.meta.user_agent,
            )
        )

        return RefreshOutput(
            access_token=access_token, refresh_token=issued.token, refresh_expires_at=issued.expires_at
        )
