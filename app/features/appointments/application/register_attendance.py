"""Registra presença/falta de uma sessão.

Porta features/appointments/application/register-attendance.ts. A carga
do agendamento passa pela RLS: se o ator não tem vínculo, o banco não
retorna a linha → NotFound (não vaza).
"""

from __future__ import annotations

from dataclasses import dataclass

from ....shared.audit.audit_recorder import AuditEvent, AuditRecorder
from ....shared.errors.app_error import NotFoundError
from ..domain.appointment import Appointment, AttendanceOutcome
from ..domain.appointment_repository import AccessContext, AppointmentRepository


@dataclass
class RegisterAttendanceInput:
    actor: AccessContext
    appointment_id: str
    outcome: AttendanceOutcome
    correlation_id: str | None = None


class RegisterAttendance:
    def __init__(self, repo: AppointmentRepository, audit: AuditRecorder) -> None:
        self._repo = repo
        self._audit = audit

    def execute(self, input: RegisterAttendanceInput) -> Appointment:
        appointment = self._repo.find_by_id(input.actor, input.appointment_id)
        if not appointment:
            raise NotFoundError("Agendamento não encontrado.")

        previous = appointment.status
        appointment.register_attendance(input.outcome)  # invariante de domínio
        updated = self._repo.update_status(input.actor, appointment.id, appointment.status)

        self._audit.record(
            AuditEvent(
                actor_id=input.actor.user_id,
                action="TRANSITION",
                resource_type="appointment",
                resource_id=appointment.id,
                correlation_id=input.correlation_id,
                diff={"status": {"from": previous, "to": updated.status}},
            )
        )

        return updated
