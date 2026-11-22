"""Verifica se já existe outro agendamento (não cancelado) na mesma sala
cujo intervalo colide com o horário candidato.

Porta shared/scheduling/room-conflict.ts. Como toda sessão ocupa a sala
pelo MESMO bloco fixo (SLOT_MINUTES: consulta + intervalo para organizar a
sala), dois intervalos de duração D só se
sobrepõem quando a diferença entre os horários de início é menor que D —
não precisa de SQL cru para checar isso. Usado tanto pelo pareamento
automático quanto pelo agendamento manual — por isso vive em shared/.
"""

from __future__ import annotations

from datetime import datetime, timedelta

from sqlalchemy import select
from sqlalchemy.orm import Session

from ..db.models import Appointment
from .session_duration import SLOT_MINUTES


def find_room_conflict(
    session: Session, room_id: str, scheduled_at: datetime, exclude_appointment_id: str | None = None
) -> str | None:
    """Retorna o id do agendamento conflitante, se houver, senão None."""
    duration = timedelta(minutes=SLOT_MINUTES)
    lower_bound = scheduled_at - duration
    upper_bound = scheduled_at + duration

    stmt = select(Appointment.id).where(
        Appointment.room_id == room_id,
        Appointment.status != "CANCELLED",
        Appointment.scheduled_at > lower_bound,
        Appointment.scheduled_at < upper_bound,
    )
    if exclude_appointment_id:
        stmt = stmt.where(Appointment.id != exclude_appointment_id)
    return session.scalar(stmt)
