"""Trava de alteração da disponibilidade do estagiário.

A disponibilidade recorrente é o insumo do pareamento: mudá-la livremente
no meio do semestre desfaz horários já combinados com pacientes. Por isso:

1. Ela fica TRAVADA por padrão.
2. O estagiário pede a mudança, com justificativa (RequestAvailabilityChange).
3. O supervisor responsável por ele — ou o administrativo — libera por um
   prazo (GrantAvailabilityUnlock) ou recusa/revoga (RevokeAvailabilityUnlock).
4. A liberação vale para UM salvamento: ao gravar a nova disponibilidade a
   edição volta a travar (UpdateAvailabilityWindows chama `consume_unlock`).
   Sem isso, uma liberação de 48h viraria 48h de edição livre.

"Supervisor responsável" = supervisor acadêmico do aluno OU supervisor de
algum vínculo ativo dele: são os dois caminhos pelos quais um supervisor
responde pelo estagiário no sistema.

O 1º preenchimento (completar cadastro) não passa por esta trava: é o
cadastro inicial, não uma mudança.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta

from ....shared.audit.audit_recorder import AuditEvent, AuditRecorder
from ....shared.errors.app_error import ForbiddenError, NotFoundError, ValidationError

DEFAULT_UNLOCK_HOURS = 48
MAX_UNLOCK_HOURS = 7 * 24
REASON_MAX = 500


def utcnow() -> datetime:
    return datetime.now(UTC).replace(tzinfo=None)


@dataclass
class AvailabilityLockState:
    unlocked_until: datetime | None
    requested_at: datetime | None
    request_reason: str | None

    def editable(self, now: datetime) -> bool:
        return self.unlocked_until is not None and self.unlocked_until > now


@dataclass
class PendingAvailabilityRequest:
    intern_id: str
    intern_name: str
    ra: str | None
    requested_at: datetime | None
    reason: str | None
    unlocked_until: datetime | None


class AvailabilityLockRepository(ABC):
    @abstractmethod
    def get_state(self, intern_id: str) -> AvailabilityLockState | None:
        """None se o usuário não existe ou não é estagiário."""

    @abstractmethod
    def save_request(self, intern_id: str, reason: str, at: datetime) -> None: ...

    @abstractmethod
    def unlock(self, intern_id: str, until: datetime) -> None:
        """Libera até `until` e dá o pedido pendente por atendido."""

    @abstractmethod
    def relock(self, intern_id: str) -> None:
        """Trava e descarta o pedido pendente (recusa ou revogação)."""

    @abstractmethod
    def consume_unlock(self, intern_id: str, now: datetime) -> bool:
        """Se a edição está liberada, trava de novo e devolve True — numa
        operação só, com a linha bloqueada, para dois salvamentos
        simultâneos não aproveitarem a mesma liberação."""

    @abstractmethod
    def is_responsible(self, supervisor_id: str, intern_id: str) -> bool: ...

    @abstractmethod
    def list_open(self, supervisor_id: str | None, now: datetime) -> list[PendingAvailabilityRequest]:
        """Pedidos pendentes e liberações em vigor. `supervisor_id` None =
        todos (administrativo); senão, só os estagiários pelos quais ele
        responde."""


@dataclass
class Actor:
    user_id: str
    role: str


def _assert_can_manage(repo: AvailabilityLockRepository, actor: Actor, intern_id: str) -> None:
    if repo.get_state(intern_id) is None:
        raise NotFoundError("Estagiário não encontrado.", {"internId": intern_id})
    if actor.role == "ADMIN":
        return
    if actor.role == "SUPERVISOR" and repo.is_responsible(actor.user_id, intern_id):
        return
    raise ForbiddenError("Só o supervisor responsável pelo estagiário pode liberar a disponibilidade dele.")


class RequestAvailabilityChange:
    def __init__(self, repo: AvailabilityLockRepository, audit: AuditRecorder) -> None:
        self._repo = repo
        self._audit = audit

    def execute(self, intern_id: str, reason: str, correlation_id: str | None = None) -> None:
        reason = " ".join(reason.split())
        if not reason or len(reason) > REASON_MAX:
            raise ValidationError(f"Explique o motivo da mudança (até {REASON_MAX} caracteres).")
        self._repo.save_request(intern_id, reason, utcnow())
        self._audit.record(
            AuditEvent(
                actor_id=intern_id,
                action="UPDATE",
                resource_type="user",
                resource_id=intern_id,
                correlation_id=correlation_id,
                diff={"event": "availability_change_requested"},
            )
        )


class GrantAvailabilityUnlock:
    def __init__(self, repo: AvailabilityLockRepository, audit: AuditRecorder) -> None:
        self._repo = repo
        self._audit = audit

    def execute(
        self, actor: Actor, intern_id: str, hours: int = DEFAULT_UNLOCK_HOURS, correlation_id: str | None = None
    ) -> datetime:
        if not 1 <= hours <= MAX_UNLOCK_HOURS:
            raise ValidationError(f"O prazo de liberação deve ser de 1 a {MAX_UNLOCK_HOURS} horas.")
        _assert_can_manage(self._repo, actor, intern_id)
        until = utcnow() + timedelta(hours=hours)
        self._repo.unlock(intern_id, until)
        self._audit.record(
            AuditEvent(
                actor_id=actor.user_id,
                action="UPDATE",
                resource_type="user",
                resource_id=intern_id,
                correlation_id=correlation_id,
                diff={"event": "availability_unlocked", "hours": hours},
            )
        )
        return until


class RevokeAvailabilityUnlock:
    def __init__(self, repo: AvailabilityLockRepository, audit: AuditRecorder) -> None:
        self._repo = repo
        self._audit = audit

    def execute(self, actor: Actor, intern_id: str, correlation_id: str | None = None) -> None:
        _assert_can_manage(self._repo, actor, intern_id)
        self._repo.relock(intern_id)
        self._audit.record(
            AuditEvent(
                actor_id=actor.user_id,
                action="UPDATE",
                resource_type="user",
                resource_id=intern_id,
                correlation_id=correlation_id,
                diff={"event": "availability_relocked"},
            )
        )
