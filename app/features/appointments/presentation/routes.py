"""Rotas do slice appointments. Guards RBAC no boundary; RLS no banco
(defesa em profundidade).

Porta features/appointments/presentation/routes.ts.
"""

from __future__ import annotations

from collections.abc import Iterator

from fastapi import APIRouter, Depends, Request
from sqlalchemy.orm import Session

from ....shared.audit.audit_recorder import AuditRecorder
from ....shared.audit.sql_audit_recorder import SqlAuditRecorder
from ....shared.auth.jwt_auth import CurrentUser, get_current_user, require_role
from ....shared.db.session import get_session
from ..application.change_appointment import CancelAppointment, CancelInput, RescheduleAppointment, RescheduleInput
from ..application.list_agenda import ListAgenda
from ..application.register_attendance import RegisterAttendance, RegisterAttendanceInput
from ..application.schedule_appointment import ScheduleAppointment, ScheduleInput
from ..domain.appointment import Appointment
from ..domain.appointment_repository import AccessContext, AppointmentRepository
from ..infrastructure.sqlalchemy_appointment_repository import SqlAlchemyAppointmentRepository
from .schemas import (
    AppointmentOut,
    AttendanceRequest,
    CancelRequest,
    CancelResponse,
    RescheduleRequest,
    ScheduleRequest,
)

router = APIRouter(prefix="/api", tags=["appointments"])


def _get_db() -> Iterator[Session]:
    with get_session() as session:
        yield session


def _get_repo(db: Session = Depends(_get_db)) -> AppointmentRepository:
    return SqlAlchemyAppointmentRepository(db)


def _get_audit(db: Session = Depends(_get_db)) -> AuditRecorder:
    return SqlAuditRecorder(db)


def _ctx_of(user: CurrentUser) -> AccessContext:
    return AccessContext(user_id=user.sub, role=user.role)


def _serialize(a: Appointment) -> AppointmentOut:
    return AppointmentOut(
        id=a.id,
        patient_id=a.patient_id,
        intern_id=a.intern_id,
        scheduled_at=a.scheduled_at,
        status=a.status,
        notes=a.notes,
        room_id=a.room_id,
        room_name=a.room_name,
        patient_code=a.patient_code,
    )


# Criar agendamento — apenas Administrativo.
@router.post(
    "/appointments", response_model=AppointmentOut, status_code=201, summary="Agenda uma sessão (Administrativo)"
)
def schedule(
    body: ScheduleRequest,
    request: Request,
    current: CurrentUser = Depends(require_role(["ADMIN"])),
    repo: AppointmentRepository = Depends(_get_repo),
    audit: AuditRecorder = Depends(_get_audit),
) -> AppointmentOut:
    use_case = ScheduleAppointment(repo, audit)
    appointment = use_case.execute(
        ScheduleInput(
            actor=_ctx_of(current),
            patient_id=body.patient_id,
            intern_id=body.intern_id,
            scheduled_at=body.scheduled_at,
            notes=body.notes,
            room_id=body.room_id,
            correlation_id=getattr(request.state, "correlation_id", None),
        )
    )
    return _serialize(appointment)


# Listar a própria agenda (escopo por RLS) — qualquer usuário autenticado.
@router.get(
    "/appointments",
    response_model=list[AppointmentOut],
    summary="Lista a agenda visível ao usuário (escopo por papel/vínculo via RLS)",
)
def list_agenda(
    current: CurrentUser = Depends(get_current_user), repo: AppointmentRepository = Depends(_get_repo)
) -> list[AppointmentOut]:
    use_case = ListAgenda(repo)
    return [_serialize(a) for a in use_case.execute(_ctx_of(current))]


# Registrar presença/falta — Estagiário (dono, via RLS) ou Administrativo.
@router.patch(
    "/appointments/{appointment_id}/attendance",
    response_model=AppointmentOut,
    summary="Registra presença/falta de uma sessão",
)
def register_attendance(
    appointment_id: str,
    body: AttendanceRequest,
    request: Request,
    current: CurrentUser = Depends(require_role(["INTERN", "ADMIN"])),
    repo: AppointmentRepository = Depends(_get_repo),
    audit: AuditRecorder = Depends(_get_audit),
) -> AppointmentOut:
    use_case = RegisterAttendance(repo, audit)
    updated = use_case.execute(
        RegisterAttendanceInput(
            actor=_ctx_of(current),
            appointment_id=appointment_id,
            outcome=body.outcome,
            correlation_id=getattr(request.state, "correlation_id", None),
        )
    )
    return _serialize(updated)


@router.patch(
    "/appointments/{appointment_id}/cancel",
    response_model=CancelResponse,
    summary="Cancela a consulta (ou ela e as seguintes do mesmo par) — Administrativo",
)
def cancel(
    appointment_id: str,
    body: CancelRequest,
    request: Request,
    current: CurrentUser = Depends(require_role(["ADMIN"])),
    repo: AppointmentRepository = Depends(_get_repo),
    audit: AuditRecorder = Depends(_get_audit),
) -> CancelResponse:
    count = CancelAppointment(repo, audit).execute(
        CancelInput(
            actor=_ctx_of(current),
            appointment_id=appointment_id,
            following=body.following,
            correlation_id=getattr(request.state, "correlation_id", None),
        )
    )
    return CancelResponse(cancelled=count)


@router.patch(
    "/appointments/{appointment_id}/reschedule",
    response_model=AppointmentOut,
    summary="Remarca data/hora e sala de uma consulta — Administrativo",
)
def reschedule(
    appointment_id: str,
    body: RescheduleRequest,
    request: Request,
    current: CurrentUser = Depends(require_role(["ADMIN"])),
    repo: AppointmentRepository = Depends(_get_repo),
    audit: AuditRecorder = Depends(_get_audit),
) -> AppointmentOut:
    updated = RescheduleAppointment(repo, audit).execute(
        RescheduleInput(
            actor=_ctx_of(current),
            appointment_id=appointment_id,
            scheduled_at=body.scheduled_at,
            room_id=body.room_id,
            correlation_id=getattr(request.state, "correlation_id", None),
        )
    )
    return _serialize(updated)
