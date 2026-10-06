"""Estagiário edita a própria disponibilidade recorrente (diferente de
CompleteInternProfile, que só grava uma vez, no 1º acesso). Substitui o
conjunto inteiro — mesma regra de validação
(shared/scheduling/availability_window.py) do autocadastro e do
completar-cadastro, pra não divergir.

Só com a edição liberada pelo supervisor, e a liberação é gasta neste
salvamento (ver availability_lock.py).

Porta features/enrollment/application/update-availability-windows.ts.
"""

from __future__ import annotations

from dataclasses import dataclass

from ....shared.audit.audit_recorder import AuditEvent, AuditRecorder
from ....shared.errors.app_error import ForbiddenError
from ....shared.scheduling.availability_window import AvailabilityWindowInput, validate_availability_windows
from ..infrastructure.sqlalchemy_enrollment_repository import SqlAlchemyEnrollmentRepository
from .availability_lock import AvailabilityLockRepository, utcnow


@dataclass
class UpdateAvailabilityWindowsInput:
    user_id: str
    windows: list[AvailabilityWindowInput]
    correlation_id: str | None = None


class UpdateAvailabilityWindows:
    def __init__(
        self, repo: SqlAlchemyEnrollmentRepository, lock: AvailabilityLockRepository, audit: AuditRecorder
    ) -> None:
        self._repo = repo
        self._lock = lock
        self._audit = audit

    def execute(self, input: UpdateAvailabilityWindowsInput) -> None:
        validate_availability_windows(input.windows, "estagiário")
        # Valida antes de gastar a liberação: um formulário com erro não
        # deve custar ao estagiário um novo pedido ao supervisor. (Se a
        # gravação falhar depois daqui, o rollback devolve a liberação.)
        if not self._lock.consume_unlock(input.user_id, utcnow()):
            raise ForbiddenError("Sua disponibilidade está travada. Peça a liberação ao seu supervisor para alterá-la.")
        self._repo.update_availability_windows(input.user_id, input.windows)
        self._audit.record(
            AuditEvent(
                actor_id=input.user_id,
                action="UPDATE",
                resource_type="user",
                resource_id=input.user_id,
                correlation_id=input.correlation_id,
                diff={"event": "update_availability_windows", "count": len(input.windows)},
            )
        )
