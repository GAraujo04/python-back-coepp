"""Cancelar e remarcar consultas (Administrativo).

Com o agendamento semanal automático (período de atendimentos), a agenda
precisa de ajuste fino: feriado, falta avisada, troca de horário. Cancelar
aceita "só esta" ou "esta e as seguintes" do mesmo par (ex.: paciente que
desistiu). Remarcar muda data/hora e sala de UMA consulta; sala ocupada no
novo horário é recusada (409) — diferente da série automática, aqui quem
escolhe está vendo a tela e pode escolher outra.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime

from ....shared.audit.audit_recorder import AuditEvent, AuditRecorder
from ....shared.errors.app_error import NotFoundError, ValidationError
from ..domain.appointment import Appointment
from ..domain.appointment_repository import AccessContext, AppointmentRepository


@dataclass
class CancelInput:
    actor: AccessContext
    appointment_id: str
    following: bool = False
    correlation_id: str | None = None


@dataclass
class RescheduleInput:
    actor: AccessContext
    appointment_id: str
    scheduled_at: str  # ISO
    room_id: str | None = None
    correlation_id: str | None = None


def _load(repo: AppointmentRepository, actor: AccessContext, id: str) -> Appointment:
    appointment = repo.find_by_id(actor, id)
    if not appointment:
        raise NotFoundError("Agendamento não encontrado.")
    appointment.assert_changeable()
    return appointment


class CancelAppointment:
    def __init__(self, repo: AppointmentRepository, audit: AuditRecorder) -> None:
        self._repo = repo
        self._audit = audit

    def execute(self, input: CancelInput) -> int:
        _load(self._repo, input.actor, input.appointment_id)
        count = self._repo.cancel(input.actor, input.appointment_id, input.following)
        self._audit.record(
            AuditEvent(
                actor_id=input.actor.user_id,
                action="TRANSITION",
                resource_type="appointment",
                resource_id=input.appointment_id,
                correlation_id=input.correlation_id,
                diff={"status": {"to": "CANCELLED"}, "following": input.following, "count": count},
            )
        )
        return count


class RescheduleAppointment:
    def __init__(self, repo: AppointmentRepository, audit: AuditRecorder) -> None:
        self._repo = repo
        self._audit = audit

    def execute(self, input: RescheduleInput) -> Appointment:
        before = _load(self._repo, input.actor, input.appointment_id)
        try:
            parsed = datetime.fromisoformat(input.scheduled_at.replace("Z", "+00:00"))
        except ValueError as exc:
            raise ValidationError("Data/hora inválida.") from exc
        # Mesma convenção do match manual: naive-UTC para o banco.
        scheduled_at = parsed.astimezone(UTC).replace(tzinfo=None)
        if scheduled_at <= datetime.now(UTC).replace(tzinfo=None):
            raise ValidationError("A nova data/hora precisa estar no futuro.")
        updated = self._repo.reschedule(input.actor, input.appointment_id, scheduled_at, input.room_id)
        self._audit.record(
            AuditEvent(
                actor_id=input.actor.user_id,
                action="UPDATE",
                resource_type="appointment",
                resource_id=input.appointment_id,
                correlation_id=input.correlation_id,
                diff={
                    "scheduledAt": {"from": before.scheduled_at.isoformat(), "to": scheduled_at.isoformat()},
                    "roomId": {"from": before.room_id, "to": input.room_id},
                },
            )
        )
        return updated
