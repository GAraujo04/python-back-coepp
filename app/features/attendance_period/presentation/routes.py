"""Rotas do período de atendimentos (Administrativo). Regra em
application/attendance_period.py."""

from __future__ import annotations

from collections.abc import Iterator
from datetime import date

from fastapi import APIRouter, Depends, Request
from sqlalchemy.orm import Session

from ....shared.audit.audit_recorder import AuditRecorder
from ....shared.audit.sql_audit_recorder import SqlAuditRecorder
from ....shared.auth.jwt_auth import CurrentUser, require_role
from ....shared.db.session import get_session
from ....shared.http.camel_model import CamelModel
from ....shared.scheduling.series_writer import current_period
from ..application.attendance_period import GenerateSeries, SetAttendancePeriod

router = APIRouter(prefix="/api", tags=["attendance-period"])


class AttendancePeriodIn(CamelModel):
    start_date: date
    end_date: date


class AttendancePeriodOut(CamelModel):
    start_date: date
    end_date: date


class SeriesResultOut(CamelModel):
    created: int
    pairs: int
    pairs_without_anchor: int


def _get_db() -> Iterator[Session]:
    with get_session() as session:
        yield session


def _get_audit(db: Session = Depends(_get_db)) -> AuditRecorder:
    return SqlAuditRecorder(db)


@router.get(
    "/settings/attendance-period",
    response_model=AttendancePeriodOut | None,
    summary="Período de atendimentos vigente (null se não configurado) — Administrativo",
)
def get_period(
    current: CurrentUser = Depends(require_role(["ADMIN"])), db: Session = Depends(_get_db)
) -> AttendancePeriodOut | None:
    period = current_period(db)
    return AttendancePeriodOut(start_date=period.start, end_date=period.end) if period else None


@router.put(
    "/settings/attendance-period",
    response_model=AttendancePeriodOut,
    summary="Define início e fim dos atendimentos do ciclo — Administrativo",
)
def set_period(
    body: AttendancePeriodIn,
    request: Request,
    current: CurrentUser = Depends(require_role(["ADMIN"])),
    db: Session = Depends(_get_db),
    audit: AuditRecorder = Depends(_get_audit),
) -> AttendancePeriodOut:
    period = SetAttendancePeriod(db, audit).execute(
        current.sub, body.start_date, body.end_date, getattr(request.state, "correlation_id", None)
    )
    return AttendancePeriodOut(start_date=period.start, end_date=period.end)


@router.post(
    "/appointments/generate-series",
    response_model=SeriesResultOut,
    summary="Agenda as consultas semanais dos vínculos ativos até o fim do período (idempotente) — Administrativo",
)
def generate_series(
    request: Request,
    current: CurrentUser = Depends(require_role(["ADMIN"])),
    db: Session = Depends(_get_db),
    audit: AuditRecorder = Depends(_get_audit),
) -> SeriesResultOut:
    r = GenerateSeries(db, audit).execute(current.sub, getattr(request.state, "correlation_id", None))
    return SeriesResultOut(created=r.created, pairs=r.pairs, pairs_without_anchor=r.pairs_without_anchor)
