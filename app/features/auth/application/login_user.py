"""Caso de uso de login (e-mail+senha — admin/supervisor).

Porta features/auth/application/login-user.ts.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime

from ....shared.audit.audit_recorder import AuditEvent, AuditRecorder
from ....shared.errors.app_error import UnauthorizedError
from ..domain.user import Email, Role
from ..domain.user_repository import UserRepository
from .ports import AccessTokenPayload, AccessTokenSigner, PasswordHasher, RefreshSessionMeta, RefreshTokenStore


@dataclass
class LoginInput:
    email: str
    password: str
    meta: RefreshSessionMeta
    correlation_id: str | None = None


@dataclass
class LoginUserPublic:
    id: str
    email: str
    full_name: str
    role: Role


@dataclass
class LoginOutput:
    access_token: str
    refresh_token: str
    refresh_expires_at: datetime
    user: LoginUserPublic


class LoginUser:
    """Verifica credenciais, emite access token (JWT curto) e refresh token
    (opaco, rotativo), e registra o evento na trilha de auditoria. Mensagens
    de erro são genéricas para não permitir enumeração de usuários."""

    def __init__(
        self,
        users: UserRepository,
        hasher: PasswordHasher,
        access_tokens: AccessTokenSigner,
        refresh_tokens: RefreshTokenStore,
        audit: AuditRecorder,
    ) -> None:
        self._users = users
        self._hasher = hasher
        self._access_tokens = access_tokens
        self._refresh_tokens = refresh_tokens
        self._audit = audit

    def execute(self, input: LoginInput) -> LoginOutput:
        email = Email.create(input.email)
        user = self._users.find_by_email(email.value)

        password_ok = self._hasher.verify(user.password_hash, input.password) if user and user.password_hash else False
        # Estagiário migrou para login via TOTVS (ver InternLogin) — este
        # caso de uso não aceita mais senha local para esse papel. Checado
        # junto com a senha (não antes) para não vazar, pela resposta, que
        # o e-mail pertence a uma conta INTERN.
        if not user or user.role == "INTERN" or not password_ok or not user.can_authenticate():
            self._audit.record(
                AuditEvent(
                    actor_id=user.id if user else None,
                    action="LOGIN_FAILED",
                    resource_type="auth",
                    correlation_id=input.correlation_id,
                    ip=input.meta.ip,
                    user_agent=input.meta.user_agent,
                )
            )
            raise UnauthorizedError("E-mail ou senha inválidos.")

        access_token = self._access_tokens.sign(AccessTokenPayload(sub=user.id, role=user.role, email=email.value))
        refresh = self._refresh_tokens.issue(user.id, input.meta)

        self._audit.record(
            AuditEvent(
                actor_id=user.id,
                action="LOGIN",
                resource_type="auth",
                resource_id=user.id,
                correlation_id=input.correlation_id,
                ip=input.meta.ip,
                user_agent=input.meta.user_agent,
            )
        )

        return LoginOutput(
            access_token=access_token,
            refresh_token=refresh.token,
            refresh_expires_at=refresh.expires_at,
            user=LoginUserPublic(id=user.id, email=email.value, full_name=user.full_name, role=user.role),
        )
