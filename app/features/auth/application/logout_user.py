"""Encerra a sessão revogando o refresh token e registrando o evento.

Porta features/auth/application/logout-user.ts.
"""

from __future__ import annotations

from dataclasses import dataclass

from ....shared.audit.audit_recorder import AuditEvent, AuditRecorder
from .ports import RefreshTokenStore


@dataclass
class LogoutInput:
    refresh_token: str | None = None
    actor_id: str | None = None
    correlation_id: str | None = None
    ip: str | None = None
    user_agent: str | None = None


class LogoutUser:
    def __init__(self, refresh_tokens: RefreshTokenStore, audit: AuditRecorder) -> None:
        self._refresh_tokens = refresh_tokens
        self._audit = audit

    def execute(self, input: LogoutInput) -> None:
        if input.refresh_token:
            self._refresh_tokens.revoke(input.refresh_token)
        self._audit.record(
            AuditEvent(
                actor_id=input.actor_id,
                action="LOGOUT",
                resource_type="auth",
                resource_id=input.actor_id,
                correlation_id=input.correlation_id,
                ip=input.ip,
                user_agent=input.user_agent,
            )
        )
