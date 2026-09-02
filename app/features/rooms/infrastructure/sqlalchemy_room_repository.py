"""Leitura/escrita de salas e alocação (gestão do Administrativo).
"Ocupada" mostra o próximo atendimento futuro alocado naquela sala (não
uma agenda completa — v1 simples).

Porta features/rooms/infrastructure/prisma-room-repository.ts.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime

from sqlalchemy import select
from sqlalchemy.orm import Session

from ....shared.crypto.field_encryption import decrypt_field
from ....shared.db.models import Appointment, Patient, Room, User
from ....shared.errors.app_error import ConflictError, NotFoundError
from ....shared.scheduling.room_conflict import find_room_conflict


@dataclass
class OccupiedBy:
    appointment_id: str
    scheduled_at: datetime
    patient_name: str
    intern_name: str


@dataclass
class RoomStatus:
    id: str
    name: str
    active: bool
    occupied_by: OccupiedBy | None


class SqlAlchemyRoomRepository:
    def __init__(self, session: Session) -> None:
        self._session = session

    def list_with_status(self) -> list[RoomStatus]:
        rooms = self._session.scalars(select(Room).where(Room.active).order_by(Room.name.asc())).all()

        now = datetime.now(UTC).replace(tzinfo=None)
        upcoming = self._session.execute(
            select(Appointment, Patient, User)
            .join(Patient, Appointment.patient_id == Patient.id)
            .join(User, Appointment.intern_id == User.id)
            .where(Appointment.room_id.isnot(None), Appointment.status != "CANCELLED", Appointment.scheduled_at >= now)
            .order_by(Appointment.scheduled_at.asc())
        ).all()

        # Primeiro (mais próximo) atendimento futuro por sala.
        next_by_room: dict[str, tuple[Appointment, Patient, User]] = {}
        for appt, patient, intern in upcoming:
            if appt.room_id and appt.room_id not in next_by_room:
                next_by_room[appt.room_id] = (appt, patient, intern)

        result: list[RoomStatus] = []
        for r in rooms:
            found = next_by_room.get(r.id)
            occupied = None
            if found:
                appt, patient, intern = found
                occupied = OccupiedBy(
                    appointment_id=appt.id,
                    scheduled_at=appt.scheduled_at,
                    patient_name=decrypt_field(patient.full_name_enc),
                    intern_name=intern.full_name,
                )
            result.append(RoomStatus(id=r.id, name=r.name, active=r.active, occupied_by=occupied))
        return result

    def reassign(self, appointment_id: str, room_id: str) -> str | None:
        """Troca a sala de um agendamento, validando conflito. Retorna a sala anterior (p/ auditoria)."""
        appointment = self._session.get(Appointment, appointment_id)
        if not appointment:
            raise NotFoundError("Agendamento não encontrado.", {"appointmentId": appointment_id})
        conflict_id = find_room_conflict(self._session, room_id, appointment.scheduled_at, appointment_id)
        if conflict_id:
            raise ConflictError(
                "A sala já está ocupada nesse horário.", {"roomId": room_id, "conflictingAppointmentId": conflict_id}
            )
        previous_room_id = appointment.room_id
        appointment.room_id = room_id
        self._session.flush()
        return previous_room_id
