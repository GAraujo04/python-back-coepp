"""Estagiário edita a própria disponibilidade recorrente a qualquer
momento do semestre (diferente de CompleteInternProfile, que só grava uma
vez, no 1º acesso). Substitui o conjunto inteiro — mesma regra de
validação (shared/scheduling/availability_window.py) do autocadastro e do
completar-cadastro, pra não divergir.

Porta features/enrollment/application/update-availability-windows.ts.
"""

from __future__ import annotations

from dataclasses import dataclass

from ....shared.audit.audit_recorder import AuditEvent, AuditRecorder
from ....shared.scheduling.availability_window import AvailabilityWindowInput, validate_availability_windows
from ..infrastructure.sqlalchemy_enrollment_repository import SqlAlchemyEnrollmentRepository


@dataclass
class UpdateAvailabilityWindowsInput:
    user_id: str
    windows: list[AvailabilityWindowInput]
    correlation_id: str | None = None


class UpdateAvailabilityWindows:
    def __init__(self, repo: SqlAlchemyEnrollmentRepository, audit: AuditRecorder) -> None:
        self._repo = repo
        self._audit = audit

    def execute(self, input: UpdateAvailabilityWindowsInput) -> None:
        validate_availability_windows(input.windows, "estagiário")
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
