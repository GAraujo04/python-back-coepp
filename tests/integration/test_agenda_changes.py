"""Cancelar/remarcar consultas e o efeito da mudança de vínculo na agenda."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

import pytest
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.features.appointments.application.change_appointment import (
    CancelAppointment,
    CancelInput,
    RescheduleAppointment,
    RescheduleInput,
)
from app.features.appointments.domain.appointment_repository import AccessContext
from app.features.appointments.infrastructure.sqlalchemy_appointment_repository import (
    SqlAlchemyAppointmentRepository,
)
from app.features.assignments.infrastructure.sqlalchemy_assignment_repository import (
    SqlAlchemyAssignmentRepository,
)
from app.shared.audit.audit_recorder import AuditEvent, AuditRecorder
from app.shared.db.models import Appointment, Assignment, Room
from app.shared.db.session import with_rls_context
from app.shared.errors.app_error import ConflictError, NotFoundError

from .conftest import World, make_user


class NoAudit(AuditRecorder):
    def record(self, event: AuditEvent) -> None:
        pass


def _now() -> datetime:
    return datetime.now(UTC).replace(tzinfo=None).replace(microsecond=0)


def _weekly(db: Session, w: World, weeks: int, room_id: str | None = None) -> list[Appointment]:
    """`weeks` consultas semanais futuras do par do mundo (+ uma passada)."""
    start = _now() + timedelta(days=1)

    def _do(s: Session) -> list[Appointment]:
        rows = [
            Appointment(
                patient_id=w.patient.id, intern_id=w.intern.id, room_id=room_id, scheduled_at=start + timedelta(weeks=i)
            )
            for i in range(-1, weeks)  # i=-1 fica no passado
        ]
        rows[0].scheduled_at = _now() - timedelta(days=6)
        rows[0].status = "ATTENDED"
        s.add_all(rows)
        s.flush()
        return rows

    return with_rls_context(db, w.admin.id, "ADMIN", _do)


def _statuses(db: Session, w: World) -> list[tuple[str, str]]:
    def _do(s: Session) -> list[tuple[str, str]]:
        rows = s.scalars(
            select(Appointment).where(Appointment.patient_id == w.patient.id).order_by(Appointment.scheduled_at)
        ).all()
        s.expire_all()
        return [(r.status, r.intern_id) for r in rows]

    return with_rls_context(db, w.admin.id, "ADMIN", _do)


def _admin(w: World) -> AccessContext:
    return AccessContext(w.admin.id, "ADMIN")


def test_cancelar_esta_e_as_seguintes(db: Session, world: World) -> None:
    appts = _weekly(db, world, 4)
    repo = SqlAlchemyAppointmentRepository(db)
    n = CancelAppointment(repo, NoAudit()).execute(CancelInput(_admin(world), appts[2].id, following=True))
    assert n == 3
    assert [s for s, _ in _statuses(db, world)] == ["ATTENDED", "SCHEDULED", "CANCELLED", "CANCELLED", "CANCELLED"]


def test_cancelar_so_uma(db: Session, world: World) -> None:
    appts = _weekly(db, world, 3)
    repo = SqlAlchemyAppointmentRepository(db)
    assert CancelAppointment(repo, NoAudit()).execute(CancelInput(_admin(world), appts[2].id)) == 1
    assert [s for s, _ in _statuses(db, world)] == ["ATTENDED", "SCHEDULED", "CANCELLED", "SCHEDULED"]


def test_consulta_realizada_nao_e_cancelada(db: Session, world: World) -> None:
    appts = _weekly(db, world, 1)
    with pytest.raises(ConflictError):
        CancelAppointment(SqlAlchemyAppointmentRepository(db), NoAudit()).execute(
            CancelInput(_admin(world), appts[0].id)
        )


def test_remarcar_recusa_sala_ocupada(db: Session, world: World) -> None:
    room = Room(name=f"Sala teste {world.patient.code}")
    db.add(room)
    db.flush()
    appts = _weekly(db, world, 2, room_id=room.id)
    repo = SqlAlchemyAppointmentRepository(db)
    use_case = RescheduleAppointment(repo, NoAudit())
    # Para o horário da consulta seguinte, na mesma sala: conflito.
    with pytest.raises(ConflictError):
        use_case.execute(
            RescheduleInput(_admin(world), appts[1].id, appts[2].scheduled_at.isoformat() + "Z", room.id)
        )
    novo = appts[1].scheduled_at + timedelta(hours=3)
    updated = use_case.execute(RescheduleInput(_admin(world), appts[1].id, novo.isoformat() + "Z", room.id))
    assert updated.scheduled_at == novo


def test_troca_de_estagiario_leva_as_consultas_futuras(db: Session, world: World) -> None:
    _weekly(db, world, 3)
    novo = make_user(db, "INTERN")
    assignment = db.scalar(select(Assignment).where(Assignment.patient_id == world.patient.id))
    assert assignment is not None
    counts = SqlAlchemyAssignmentRepository(db).update(world.admin.id, assignment.id, intern_id=novo.id)
    assert counts == {"transferred": 3, "cancelled": 0}
    interns = [i for _, i in _statuses(db, world)]
    assert interns[0] == world.intern.id  # a passada é histórico
    assert set(interns[1:]) == {novo.id}


def test_encerrar_vinculo_cancela_as_futuras(db: Session, world: World) -> None:
    _weekly(db, world, 2)
    assignment = db.scalar(select(Assignment).where(Assignment.patient_id == world.patient.id))
    assert assignment is not None
    counts = SqlAlchemyAssignmentRepository(db).update(world.admin.id, assignment.id, active=False)
    assert counts == {"transferred": 0, "cancelled": 2}
    assert [s for s, _ in _statuses(db, world)] == ["ATTENDED", "CANCELLED", "CANCELLED"]
    # Já encerrado: não é mais alterável.
    with pytest.raises(NotFoundError):
        SqlAlchemyAssignmentRepository(db).update(world.admin.id, assignment.id, active=False)


def test_vinculo_inexistente_da_404(db: Session, world: World) -> None:
    with pytest.raises(NotFoundError):
        SqlAlchemyAssignmentRepository(db).update(world.admin.id, "00000000-0000-0000-0000-000000000000")
