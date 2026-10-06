"""Leitura/escrita de salas e alocação (gestão do Administrativo).
"Ocupada" mostra o próximo atendimento futuro alocado naquela sala (não
uma agenda completa — v1 simples).

Sala não é apagada, é desativada: agendamentos antigos apontam para ela
(FK) e o histórico precisa continuar dizendo onde o atendimento ocorreu.

Porta features/rooms/infrastructure/prisma-room-repository.ts.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime

from sqlalchemy import select
from sqlalchemy.orm import Session

from ....shared.crypto.field_encryption import decrypt_field
from ....shared.db.models import Appointment, Patient, Room, User
from ....shared.errors.app_error import ConflictError, NotFoundError, ValidationError
from ....shared.scheduling.room_category import ROOM_CATEGORIES, RoomCategory
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
    category: str
    active: bool
    occupied_by: OccupiedBy | None


@dataclass
class RoomChanges:
    """Campos ausentes (None) ficam como estão."""

    name: str | None = None
    category: RoomCategory | None = None
    active: bool | None = None


_NAME_MAX = 60


def _clean_name(name: str) -> str:
    cleaned = " ".join(name.split())
    if not cleaned or len(cleaned) > _NAME_MAX:
        raise ValidationError(f"O nome da sala deve ter entre 1 e {_NAME_MAX} caracteres.")
    return cleaned


def _check_category(category: str) -> None:
    # O CHECK do banco também recusa, mas com erro 547 genérico; aqui a
    # mensagem diz o que está errado.
    if category not in ROOM_CATEGORIES:
        raise ValidationError("Categoria de sala inválida.", {"category": category})


class SqlAlchemyRoomRepository:
    def __init__(self, session: Session) -> None:
        self._session = session

    def list_with_status(self, include_inactive: bool = False) -> list[RoomStatus]:
        stmt = select(Room).order_by(Room.active.desc(), Room.name.asc())
        if not include_inactive:
            stmt = stmt.where(Room.active)
        rooms = self._session.scalars(stmt).all()

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
            result.append(RoomStatus(id=r.id, name=r.name, category=r.category, active=r.active, occupied_by=occupied))
        return result

    def _name_taken(self, name: str, except_id: str | None = None) -> bool:
        # `name` é UNIQUE no banco; a collation padrão do SQL Server é
        # case-insensitive, então "sala 12" colide com "Sala 12" lá também.
        stmt = select(Room.id).where(Room.name == name)
        if except_id:
            stmt = stmt.where(Room.id != except_id)
        return self._session.scalar(stmt) is not None

    def create(self, name: str, category: RoomCategory) -> Room:
        name = _clean_name(name)
        _check_category(category)
        if self._name_taken(name):
            raise ConflictError("Já existe uma sala com esse nome.", {"name": name})
        room = Room(name=name, category=category, active=True)
        self._session.add(room)
        self._session.flush()
        return room

    def update(self, room_id: str, changes: RoomChanges) -> dict[str, object]:
        """Aplica as mudanças e devolve o diff (antes/depois) para auditoria."""
        room = self._session.get(Room, room_id)
        if not room:
            raise NotFoundError("Sala não encontrada.", {"roomId": room_id})
        diff: dict[str, object] = {}
        if changes.name is not None:
            name = _clean_name(changes.name)
            if name != room.name:
                if self._name_taken(name, except_id=room_id):
                    raise ConflictError("Já existe uma sala com esse nome.", {"name": name})
                diff["name"] = {"from": room.name, "to": name}
                room.name = name
        if changes.category is not None and changes.category != room.category:
            _check_category(changes.category)
            diff["category"] = {"from": room.category, "to": changes.category}
            room.category = changes.category
        if changes.active is not None and changes.active != room.active:
            if not changes.active:
                self._assert_no_upcoming(room_id)
            diff["active"] = {"from": room.active, "to": changes.active}
            room.active = changes.active
        self._session.flush()
        return diff

    def _assert_no_upcoming(self, room_id: str) -> None:
        """Desativar uma sala com atendimento futuro deixaria esse
        atendimento numa sala que some das listas — o administrativo
        precisa realocá-lo antes."""
        now = datetime.now(UTC).replace(tzinfo=None)
        upcoming = self._session.scalar(
            select(Appointment.id).where(
                Appointment.room_id == room_id,
                Appointment.status == "SCHEDULED",
                Appointment.scheduled_at >= now,
            )
        )
        if upcoming:
            raise ConflictError(
                "A sala tem atendimentos futuros. Realoque-os antes de desativá-la.",
                {"roomId": room_id, "appointmentId": upcoming},
            )

    def reassign(self, appointment_id: str, room_id: str) -> str | None:
        """Troca a sala de um agendamento, validando conflito. Retorna a sala anterior (p/ auditoria)."""
        appointment = self._session.get(Appointment, appointment_id)
        if not appointment:
            raise NotFoundError("Agendamento não encontrado.", {"appointmentId": appointment_id})
        target = self._session.get(Room, room_id)
        if not target or not target.active:
            raise NotFoundError("Sala não encontrada ou desativada.", {"roomId": room_id})
        conflict_id = find_room_conflict(self._session, room_id, appointment.scheduled_at, appointment_id)
        if conflict_id:
            raise ConflictError(
                "A sala já está ocupada nesse horário.", {"roomId": room_id, "conflictingAppointmentId": conflict_id}
            )
        previous_room_id = appointment.room_id
        appointment.room_id = room_id
        self._session.flush()
        return previous_room_id
