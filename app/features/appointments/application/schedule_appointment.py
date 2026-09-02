"""Agenda uma sessão vinculando paciente↔estagiário (executado pelo
Administrativo).

Porta features/appointments/application/schedule-appointment.ts. Se
room_id for informado, valida conflito de sala (mesma regra do pareamento
automático — ver shared/scheduling/room_conflict.py).
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime

from ....shared.audit.audit_recorder import AuditEvent, AuditRecorder
from ....shared.errors.app_error import ValidationError
from ..domain.appointment import Appointment
from ..domain.appointment_repository import AccessContext, AppointmentRepository, NewAppointment


@dataclass
class ScheduleInput:
    actor: AccessContext
    patient_id: str
    intern_id: str
    scheduled_at: str  # ISO
    notes: str | None = None
    room_id: str | None = None  # opcional — retrocompatível com agendamentos sem sala
    correlation_id: str | None = None


class ScheduleAppointment:
    def __init__(self, repo: AppointmentRepository, audit: AuditRecorder) -> None:
        self._repo = repo
        self._audit = audit

    def execute(self, input: ScheduleInput) -> Appointment:
        try:
            scheduled_at = datetime.fromisoformat(input.scheduled_at)
        except ValueError as exc:
            # Equivalente ao "Invalid Date" (NaN) do `new Date(string)` do
            # JS — aqui `fromisoformat` já rejeita a entrada malformada
            # sozinho (ver nota em Appointment.assert_future_or_today).
            raise ValidationError("Data/hora do agendamento inválida.") from exc
        Appointment.assert_future_or_today(scheduled_at)

        appointment = self._repo.create(
            input.actor,
            NewAppointment(
                patient_id=input.patient_id,
                intern_id=input.intern_id,
                scheduled_at=scheduled_at,
                notes=input.notes,
                room_id=input.room_id,
            ),
        )

        self._audit.record(
            AuditEvent(
                actor_id=input.actor.user_id,
                action="CREATE",
                resource_type="appointment",
                resource_id=appointment.id,
                correlation_id=input.correlation_id,
            )
        )

        return appointment
