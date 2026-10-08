"""Adapter SQLAlchemy do AppointmentRepository. Cada método roda dentro de
with_rls_context(...): a transação seta app_user_id/app_role e as
SECURITY POLICIES do SQL Server filtram/autorizam as linhas por papel e
vínculo.

Porta features/appointments/infrastructure/prisma-appointment-repository.ts.
"""

from __future__ import annotations

from datetime import datetime

from sqlalchemy import select
from sqlalchemy.orm import Session

from ....shared.db.models import Appointment as AppointmentRow
from ....shared.db.session import get_under_rls, with_rls_context
from ....shared.errors.app_error import ConflictError, NotFoundError
from ....shared.scheduling.room_conflict import find_room_conflict
from ..domain.appointment import Appointment, AppointmentStatus
from ..domain.appointment_repository import AccessContext, AppointmentRepository, NewAppointment


def _to_domain(row: AppointmentRow) -> Appointment:
    return Appointment(
        id=row.id,
        patient_id=row.patient_id,
        intern_id=row.intern_id,
        scheduled_at=row.scheduled_at,
        status=row.status,  # type: ignore[arg-type]  # coluna String com CHECK constraint no banco garante o conjunto fechado
        notes=row.notes,
        room_id=row.room_id,
        room_name=row.room.name if row.room else None,
        patient_code=row.patient.code if row.patient else None,
    )


class SqlAlchemyAppointmentRepository(AppointmentRepository):
    def __init__(self, session: Session) -> None:
        self._session = session

    def create(self, ctx: AccessContext, data: NewAppointment) -> Appointment:
        def _do(session: Session) -> Appointment:
            if data.room_id:
                conflict_id = find_room_conflict(session, data.room_id, data.scheduled_at)
                if conflict_id:
                    raise ConflictError(
                        "A sala já está ocupada nesse horário.",
                        {"roomId": data.room_id, "conflictingAppointmentId": conflict_id},
                    )
            row = AppointmentRow(
                patient_id=data.patient_id,
                intern_id=data.intern_id,
                scheduled_at=data.scheduled_at,
                notes=data.notes,
                room_id=data.room_id,
            )
            session.add(row)
            session.flush()
            session.refresh(row, attribute_names=["room", "patient"])
            return _to_domain(row)

        return with_rls_context(self._session, ctx.user_id, ctx.role, _do)

    def list_for_actor(self, ctx: AccessContext) -> list[Appointment]:
        def _do(session: Session) -> list[Appointment]:
            rows = session.scalars(select(AppointmentRow).order_by(AppointmentRow.scheduled_at.asc()))
            return [_to_domain(r) for r in rows]

        return with_rls_context(self._session, ctx.user_id, ctx.role, _do)

    def find_by_id(self, ctx: AccessContext, id: str) -> Appointment | None:
        def _do(session: Session) -> Appointment | None:
            row = get_under_rls(session, AppointmentRow, id)
            return _to_domain(row) if row else None

        return with_rls_context(self._session, ctx.user_id, ctx.role, _do)

    def update_status(self, ctx: AccessContext, id: str, status: AppointmentStatus) -> Appointment:
        def _do(session: Session) -> Appointment:
            row = get_under_rls(session, AppointmentRow, id)
            if not row:
                raise LookupError(f"Appointment {id} não encontrado dentro do contexto de RLS.")
            row.status = status
            session.flush()
            session.refresh(row, attribute_names=["room", "patient"])
            return _to_domain(row)

        return with_rls_context(self._session, ctx.user_id, ctx.role, _do)

    def cancel(self, ctx: AccessContext, id: str, following: bool) -> int:
        def _do(session: Session) -> int:
            row = get_under_rls(session, AppointmentRow, id)
            if not row:
                raise NotFoundError("Agendamento não encontrado.")
            rows = [row]
            if following:
                rows += session.scalars(
                    select(AppointmentRow).where(
                        AppointmentRow.patient_id == row.patient_id,
                        AppointmentRow.intern_id == row.intern_id,
                        AppointmentRow.status == "SCHEDULED",
                        AppointmentRow.scheduled_at > row.scheduled_at,
                    )
                ).all()
            for r in rows:
                r.status = "CANCELLED"
            session.flush()
            return len(rows)

        return with_rls_context(self._session, ctx.user_id, ctx.role, _do)

    def reschedule(self, ctx: AccessContext, id: str, scheduled_at: datetime, room_id: str | None) -> Appointment:
        def _do(session: Session) -> Appointment:
            row = get_under_rls(session, AppointmentRow, id)
            if not row:
                raise NotFoundError("Agendamento não encontrado.")
            if room_id:
                conflict_id = find_room_conflict(session, room_id, scheduled_at, exclude_appointment_id=id)
                if conflict_id:
                    raise ConflictError(
                        "A sala já está ocupada nesse horário.",
                        {"roomId": room_id, "conflictingAppointmentId": conflict_id},
                    )
            row.scheduled_at = scheduled_at
            row.room_id = room_id
            session.flush()
            session.refresh(row, attribute_names=["room", "patient"])
            return _to_domain(row)

        return with_rls_context(self._session, ctx.user_id, ctx.role, _do)
