"""Modelos Pydantic do slice appointments (validação + OpenAPI nativo).

Porta features/appointments/presentation/schemas.ts.
"""

from __future__ import annotations

from typing import Literal

from ....shared.http.camel_model import CamelModel
from ....shared.http.utc_datetime import UtcDatetime


class AppointmentOut(CamelModel):
    id: str
    patient_id: str
    intern_id: str
    scheduled_at: UtcDatetime
    status: str
    notes: str | None
    room_id: str | None
    room_name: str | None
    # Código, não nome: é como o estagiário identifica o paciente nas
    # listas (o nome ele vê no prontuário).
    patient_code: str | None = None


class ScheduleRequest(CamelModel):
    patient_id: str
    intern_id: str
    scheduled_at: str
    notes: str | None = None
    room_id: str | None = None


class AttendanceRequest(CamelModel):
    outcome: Literal["ATTENDED", "NO_SHOW"]


class CancelRequest(CamelModel):
    # True: cancela também as consultas seguintes ainda marcadas do mesmo par.
    following: bool = False


class CancelResponse(CamelModel):
    cancelled: int


class RescheduleRequest(CamelModel):
    scheduled_at: str
    room_id: str | None = None
