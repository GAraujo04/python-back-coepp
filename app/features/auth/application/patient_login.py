"""Login do paciente por CPF + data de nascimento (sem senha).

Porta features/auth/application/patient-login.ts. O CPF é localizado pelo
índice cego; a data de nascimento é o segundo fator. Mensagem genérica
para não permitir enumeração.
"""

from __future__ import annotations

import hashlib
import re
from dataclasses import dataclass
from datetime import datetime
from typing import Literal

from ....shared.audit.audit_recorder import AuditEvent, AuditRecorder
from ....shared.errors.app_error import TooManyRequestsError, UnauthorizedError
from .ports import (
    AccessTokenPayload,
    AccessTokenSigner,
    LoginAttemptTracker,
    PatientAuthLookup,
    RefreshSessionMeta,
    RefreshTokenStore,
)


def _attempt_key(cpf: str) -> str:
    """Chave de bloqueio derivada do CPF.

    Guardamos o hash, não os dígitos: o contador vive em memória por 15
    minutos e não há razão pra manter uma lista de CPFs em claro no
    processo — inclusive de quem só errou a data de nascimento e nem é
    paciente daqui.
    """
    digits = re.sub(r"\D", "", cpf)
    return "cpf:" + hashlib.sha256(digits.encode("utf-8")).hexdigest()


@dataclass
class PatientLoginInput:
    cpf: str
    birth_date: str  # yyyy-mm-dd
    meta: RefreshSessionMeta
    correlation_id: str | None = None


@dataclass
class PatientLoginUserPublic:
    id: str
    email: str
    full_name: str
    role: Literal["PATIENT"] = "PATIENT"


@dataclass
class PatientLoginOutput:
    access_token: str
    refresh_token: str
    refresh_expires_at: datetime
    user: PatientLoginUserPublic


class PatientLogin:
    def __init__(
        self,
        lookup: PatientAuthLookup,
        access_tokens: AccessTokenSigner,
        refresh_tokens: RefreshTokenStore,
        attempts: LoginAttemptTracker,
        audit: AuditRecorder,
    ) -> None:
        self._lookup = lookup
        self._access_tokens = access_tokens
        self._refresh_tokens = refresh_tokens
        self._attempts = attempts
        self._audit = audit

    def execute(self, input: PatientLoginInput) -> PatientLoginOutput:
        # Este é o login mais exposto do sistema: os dois fatores (CPF e
        # data de nascimento) não são segredos, e o espaço de busca da data
        # é pequeno o bastante pra ser varrido por completo. Sem bloqueio
        # por tentativa, quem tem o CPF entra — é só questão de quantas
        # requisições. O bloqueio por conta é o que torna a varredura
        # inviável; o rate limit por IP sozinho não fecha isso.
        attempt_key = _attempt_key(input.cpf)
        if self._attempts.is_locked(attempt_key):
            raise TooManyRequestsError("Muitas tentativas. Tente novamente mais tarde.")

        account = self._lookup.find_by_cpf(input.cpf)
        ok = account is not None and account.birth_date == input.birth_date

        if not account or not ok:
            self._attempts.record_failure(attempt_key)
            self._audit.record(
                AuditEvent(
                    actor_id=account.user_id if account else None,
                    action="LOGIN_FAILED",
                    resource_type="auth",
                    correlation_id=input.correlation_id,
                    ip=input.meta.ip,
                    user_agent=input.meta.user_agent,
                    diff={"method": "cpf"},
                )
            )
            raise UnauthorizedError("CPF ou data de nascimento inválidos.")

        self._attempts.record_success(attempt_key)
        access_token = self._access_tokens.sign(
            AccessTokenPayload(sub=account.user_id, role="PATIENT", email=account.email)
        )
        refresh = self._refresh_tokens.issue(account.user_id, input.meta)

        self._audit.record(
            AuditEvent(
                actor_id=account.user_id,
                action="LOGIN",
                resource_type="auth",
                resource_id=account.user_id,
                correlation_id=input.correlation_id,
                ip=input.meta.ip,
                user_agent=input.meta.user_agent,
                diff={"method": "cpf"},
            )
        )

        return PatientLoginOutput(
            access_token=access_token,
            refresh_token=refresh.token,
            refresh_expires_at=refresh.expires_at,
            user=PatientLoginUserPublic(id=account.user_id, email=account.email, full_name=account.full_name),
        )
