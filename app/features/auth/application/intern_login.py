"""Login do estagiário via TOTVS RM (duas chamadas encadeadas: token,
depois vínculo).

Porta features/auth/application/intern-login.ts. Só TIPO=aluno acessa
esta tela. Emite sessão própria (mesmo mecanismo do LoginUser/PatientLogin)
— o token do TOTVS nunca sai desta função, nunca é persistido nem
devolvido ao cliente.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from datetime import datetime
from typing import Literal

from ....shared.audit.audit_recorder import AuditEvent, AuditRecorder
from ....shared.errors.app_error import ForbiddenError, ServiceUnavailableError, UnauthorizedError, ValidationError
from ..domain.user_repository import UserRepository
from .ports import (
    AccessTokenPayload,
    AccessTokenSigner,
    LoginAttemptTracker,
    RefreshSessionMeta,
    RefreshTokenStore,
    TotvsAuthClient,
    TotvsInvalidCredentialsError,
    TotvsProtocolError,
    TotvsUnavailableError,
)

# Usuário RM: só dígitos, tamanho observado empiricamente (ver spec da
# integração). Allow-list estrita — o valor é interpolado numa consulta SQL
# no servidor TOTVS (consultaSQLServer/RealizaConsulta); rejeitar aqui,
# antes de qualquer chamada, é a defesa principal contra SQL injection
# nesse endpoint de terceiro.
_RM_USUARIO_LENGTH = 11
_RM_USUARIO_RE = re.compile(rf"^\d{{{_RM_USUARIO_LENGTH}}}$")

# TIPO=aluno vem de config (self._tipo_aluno). Funcionário/Professor são
# negados sempre nesta tela — só entram no conjunto "conhecido" (para
# diferenciar de um TIPO realmente desconhecido, que é logado à parte).
_TOTVS_TIPO_FUNCIONARIO = "F"
_TOTVS_TIPO_PROFESSOR = "P"


@dataclass
class InternLoginInput:
    usuario_rm: str
    senha_rm: str
    meta: RefreshSessionMeta
    link_email: str | None = None
    correlation_id: str | None = None


@dataclass
class InternLoginUserPublic:
    id: str
    email: str
    full_name: str
    profile_complete: bool
    role: Literal["INTERN"] = "INTERN"


@dataclass
class InternLoginOutput:
    access_token: str
    refresh_token: str
    refresh_expires_at: datetime
    user: InternLoginUserPublic


class InternLogin:
    def __init__(
        self,
        users: UserRepository,
        totvs: TotvsAuthClient,
        access_tokens: AccessTokenSigner,
        refresh_tokens: RefreshTokenStore,
        attempts: LoginAttemptTracker,
        audit: AuditRecorder,
        tipo_aluno: str,
    ) -> None:
        self._users = users
        self._totvs = totvs
        self._access_tokens = access_tokens
        self._refresh_tokens = refresh_tokens
        self._attempts = attempts
        self._audit = audit
        self._tipo_aluno = tipo_aluno

    def execute(self, input: InternLoginInput) -> InternLoginOutput:
        if not _RM_USUARIO_RE.match(input.usuario_rm):
            raise ValidationError("Usuário deve conter somente números.")

        user_key = f"rm:{input.usuario_rm}"
        ip_key = f"ip:{input.meta.ip or 'unknown'}"
        if self._attempts.is_locked(user_key) or self._attempts.is_locked(ip_key):
            raise UnauthorizedError("Muitas tentativas. Tente novamente mais tarde.")

        def record_failure(reason: str) -> None:
            self._attempts.record_failure(user_key)
            self._attempts.record_failure(ip_key)
            self._audit.record(
                AuditEvent(
                    actor_id=None,
                    action="LOGIN_FAILED",
                    resource_type="auth",
                    correlation_id=input.correlation_id,
                    ip=input.meta.ip,
                    user_agent=input.meta.user_agent,
                    diff={"method": "totvs", "reason": reason},
                )
            )

        try:
            access_token = self._totvs.authenticate(input.usuario_rm, input.senha_rm).access_token
        except TotvsInvalidCredentialsError as exc:
            record_failure("credenciais_invalidas")
            raise UnauthorizedError("Usuário ou senha inválidos.") from exc
        except (TotvsUnavailableError, TotvsProtocolError) as exc:
            raise ServiceUnavailableError(
                "Serviço de autenticação institucional indisponível. Tente novamente em instantes.",
                getattr(exc, "details", None),
            ) from exc

        try:
            vinculos = self._totvs.consultar_vinculo(input.usuario_rm, access_token)
        except (TotvsUnavailableError, TotvsProtocolError) as exc:
            raise ServiceUnavailableError(
                "Serviço de autenticação institucional indisponível. Tente novamente em instantes.",
                getattr(exc, "details", None),
            ) from exc
        # access_token do TOTVS não é mais necessário a partir daqui — só
        # existe nesta variável local, nunca persistido nem devolvido ao cliente.

        for v in vinculos:
            if v.tipo not in (self._tipo_aluno, _TOTVS_TIPO_FUNCIONARIO, _TOTVS_TIPO_PROFESSOR):
                # TIPO fora do conjunto conhecido: não derruba o login por si
                # só (o que decide é ter ou não um TIPO=aluno no array), mas
                # fica registrado pra investigação — sem dado sensível, só o código.
                self._audit.record(
                    AuditEvent(
                        actor_id=None,
                        action="LOGIN_FAILED",
                        resource_type="auth",
                        correlation_id=input.correlation_id,
                        diff={"method": "totvs", "reason": "tipo_desconhecido", "tipo": v.tipo},
                    )
                )

        # Uma pessoa pode ter mais de um vínculo — nunca pega o primeiro
        # item, filtra explicitamente pelo TIPO=aluno.
        aluno = next((v for v in vinculos if v.tipo == self._tipo_aluno), None)
        if not aluno:
            record_failure("perfil_sem_permissao")
            raise ForbiddenError("Perfil sem permissão para acessar esta tela.")

        outcome = self._users.resolve_intern_from_totvs(
            totvs_usuario=input.usuario_rm, full_name=aluno.nome, link_email=input.link_email
        )

        if outcome.kind == "link_failed":
            record_failure("vinculo_nao_encontrado")
            raise ValidationError(
                "Não encontramos um cadastro existente com esse e-mail. "
                "Deixe o campo em branco para criar um cadastro novo."
            )

        user = outcome.user
        assert user is not None  # garantido pelo contrato de TotvsResolveOutcome (kind != link_failed => user setado)
        if not user.can_authenticate():
            record_failure("conta_inativa")
            raise UnauthorizedError("Usuário ou senha inválidos.")

        own_access_token = self._access_tokens.sign(
            AccessTokenPayload(sub=user.id, role="INTERN", email=user.email.value)
        )
        refresh = self._refresh_tokens.issue(user.id, input.meta)
        profile_complete = self._users.is_intern_profile_complete(user.id)

        self._attempts.record_success(user_key)
        self._attempts.record_success(ip_key)
        self._audit.record(
            AuditEvent(
                actor_id=user.id,
                action="LOGIN",
                resource_type="auth",
                resource_id=user.id,
                correlation_id=input.correlation_id,
                ip=input.meta.ip,
                user_agent=input.meta.user_agent,
                diff={"method": "totvs", "outcome": outcome.kind},
            )
        )

        return InternLoginOutput(
            access_token=own_access_token,
            refresh_token=refresh.token,
            refresh_expires_at=refresh.expires_at,
            user=InternLoginUserPublic(
                id=user.id, email=user.email.value, full_name=user.full_name, profile_complete=profile_complete
            ),
        )
