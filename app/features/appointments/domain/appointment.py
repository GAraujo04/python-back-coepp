"""Agregado Appointment (sessão agendada). Vincula paciente↔estagiário e é
a origem da vinculação ao prontuário. Invariantes de ciclo de vida vivem
aqui.

Porta features/appointments/domain/appointment.ts.
"""

from __future__ import annotations

from datetime import datetime
from typing import Literal

from ....shared.errors.app_error import ConflictError

AppointmentStatus = Literal["SCHEDULED", "ATTENDED", "NO_SHOW", "CANCELLED"]

# Presenças registráveis a partir de um agendamento SCHEDULED.
AttendanceOutcome = Literal["ATTENDED", "NO_SHOW"]


class Appointment:
    def __init__(
        self,
        id: str,
        patient_id: str,
        intern_id: str,
        scheduled_at: datetime,
        status: AppointmentStatus,
        notes: str | None,
        room_id: str | None = None,
        room_name: str | None = None,
        patient_code: str | None = None,
    ) -> None:
        self.id = id
        self.patient_id = patient_id
        self.intern_id = intern_id
        self.scheduled_at = scheduled_at
        self.status: AppointmentStatus = status
        self.notes = notes
        self.room_id = room_id
        self.room_name = room_name
        self.patient_code = patient_code

    def register_attendance(self, outcome: AttendanceOutcome) -> None:
        """Registra presença/falta. Só é possível a partir de um agendamento SCHEDULED."""
        if self.status != "SCHEDULED":
            raise ConflictError(
                "Presença só pode ser registrada em agendamento SCHEDULED.",
                {"appointmentId": self.id, "status": self.status},
            )
        self.status = outcome

    def assert_changeable(self) -> None:
        """Cancelar ou remarcar só vale para consulta ainda marcada: uma
        consulta realizada, faltada ou já cancelada é histórico."""
        if self.status != "SCHEDULED":
            raise ConflictError(
                "Só é possível cancelar ou remarcar uma consulta ainda agendada.",
                {"appointmentId": self.id, "status": self.status},
            )

    @staticmethod
    def assert_future_or_today(scheduled_at: datetime) -> None:  # noqa: ARG004 - hook de domínio, ver nota
        """No original TS, este método só existe pra rejeitar um `new
        Date(string_invalida)` — que em JS não lança, produz um objeto
        "Invalid Date" (NaN silencioso) que só um check explícito pega.
        Em Python, `datetime.fromisoformat()` já lança `ValueError` sozinho
        pra entrada malformada (ver ScheduleAppointment.execute), então não
        existe um "NaN" equivalente pra checar aqui — o parse já falhou
        antes de chegar neste ponto. Mantido como hook de domínio (mesmo
        nome/lugar do original) pra uma validação futura de verdade
        (ex.: não aceitar datas muito no passado), que o nome já sugeria
        mas o TS original nunca chegou a implementar."""
        return None
