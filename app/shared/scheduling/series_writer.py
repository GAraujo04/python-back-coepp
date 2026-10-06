"""Grava a série semanal de consultas de um par paciente↔estagiário dentro
do período de atendimentos vigente. Usado pelo pareamento (automático e
manual, ao criar o par) e pela geração em lote do administrativo (pares
que já existiam) — por isso em shared/, como room_conflict.py.

Precisa rodar dentro de with_rls_context(..., "ADMIN", ...): só o
administrativo insere em `appointments` (BLOCK PREDICATE).

Idempotente: uma data em que o paciente já tem consulta (não cancelada)
é pulada, então rodar duas vezes não duplica nada.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime, timedelta

from sqlalchemy import select
from sqlalchemy.orm import Session

from ..db.models import Appointment, AttendancePeriod
from .room_conflict import find_room_conflict
from .session_duration import SESSION_DURATION_MINUTES
from .weekly_series import weekly_occurrences


@dataclass
class PeriodRange:
    start: date
    end: date


def current_period(session: Session) -> PeriodRange | None:
    row = session.scalar(
        select(AttendancePeriod).order_by(AttendancePeriod.created_at.desc(), AttendancePeriod.id.desc())
    )
    return PeriodRange(start=row.start_date, end=row.end_date) if row else None


def _patient_busy(session: Session, patient_id: str, at: datetime) -> bool:
    window = timedelta(minutes=SESSION_DURATION_MINUTES)
    return (
        session.scalar(
            select(Appointment.id).where(
                Appointment.patient_id == patient_id,
                Appointment.status != "CANCELLED",
                Appointment.scheduled_at > at - window,
                Appointment.scheduled_at < at + window,
            )
        )
        is not None
    )


def schedule_weekly_series(
    session: Session,
    *,
    patient_id: str,
    intern_id: str,
    room_id: str | None,
    anchor: datetime,
    period: PeriodRange,
    not_before: datetime,
) -> int:
    """Cria as consultas semanais depois de `not_before`, no dia/horário de
    `anchor`, até o fim do período. Mantém a sala do par quando livre;
    ocupada naquela semana, a consulta é criada sem sala (o
    administrativo realoca) — mesma regra do match manual. Devolve quantas
    criou."""
    created = 0
    for at in weekly_occurrences(anchor, period.start, period.end, not_before):
        if _patient_busy(session, patient_id, at):
            continue
        room = room_id if room_id and not find_room_conflict(session, room_id, at) else None
        session.add(
            Appointment(patient_id=patient_id, intern_id=intern_id, room_id=room, scheduled_at=at, status="SCHEDULED")
        )
        # flush a cada uma: a checagem de conflito da semana seguinte
        # precisa enxergar a que acabou de entrar.
        session.flush()
        created += 1
    return created
