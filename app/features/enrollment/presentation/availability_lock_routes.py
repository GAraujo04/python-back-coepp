"""Rotas da trava de disponibilidade do estagiário. O supervisor vê os
pedidos, libera por um prazo, recusa/revoga; o administrativo só vê as
alterações já feitas (com a nova disponibilidade). Regra em
application/availability_lock.py."""

from __future__ import annotations

from collections.abc import Iterator
from datetime import timedelta

from fastapi import APIRouter, Depends, Request
from sqlalchemy.orm import Session

from ....shared.audit.audit_recorder import AuditRecorder
from ....shared.audit.sql_audit_recorder import SqlAuditRecorder
from ....shared.auth.jwt_auth import CurrentUser, require_role
from ....shared.db.session import get_session
from ..application.availability_lock import Actor, GrantAvailabilityUnlock, RevokeAvailabilityUnlock, utcnow
from ..infrastructure.sqlalchemy_availability_lock_repository import SqlAlchemyAvailabilityLockRepository
from .schemas import (
    AvailabilityChangeOut,
    AvailabilityUnlockIn,
    AvailabilityUnlockOut,
    AvailabilityWindowOut,
    PendingAvailabilityRequestOut,
)

router = APIRouter(prefix="/api", tags=["availability-lock"])

# Até quando uma alteração continua na lista do administrativo.
RECENT_CHANGES_WINDOW = timedelta(days=30)


def _get_db() -> Iterator[Session]:
    with get_session() as session:
        yield session


def _get_repo(db: Session = Depends(_get_db)) -> SqlAlchemyAvailabilityLockRepository:
    return SqlAlchemyAvailabilityLockRepository(db)


def _get_audit(db: Session = Depends(_get_db)) -> AuditRecorder:
    return SqlAuditRecorder(db)


@router.get(
    "/availability-requests",
    response_model=list[PendingAvailabilityRequestOut],
    summary="Pedidos de mudança de disponibilidade e liberações em vigor dos estagiários do supervisor",
)
def list_requests(
    current: CurrentUser = Depends(require_role(["SUPERVISOR"])),
    repo: SqlAlchemyAvailabilityLockRepository = Depends(_get_repo),
) -> list[PendingAvailabilityRequestOut]:
    return [
        PendingAvailabilityRequestOut(
            intern_id=r.intern_id,
            intern_name=r.intern_name,
            ra=r.ra,
            requested_at=r.requested_at,
            reason=r.reason,
            unlocked_until=r.unlocked_until,
        )
        for r in repo.list_open(current.sub, utcnow())
    ]


@router.get(
    "/availability-changes",
    response_model=list[AvailabilityChangeOut],
    summary="Alterações de disponibilidade dos últimos 30 dias, com a nova disponibilidade (Administrativo)",
)
def list_changes(
    current: CurrentUser = Depends(require_role(["ADMIN"])),
    repo: SqlAlchemyAvailabilityLockRepository = Depends(_get_repo),
) -> list[AvailabilityChangeOut]:
    return [
        AvailabilityChangeOut(
            intern_id=c.intern_id,
            intern_name=c.intern_name,
            ra=c.ra,
            changed_at=c.changed_at,
            windows=[AvailabilityWindowOut(weekday=d, start_time=a, end_time=b) for d, a, b in c.windows],
        )
        for c in repo.list_changes_since(utcnow() - RECENT_CHANGES_WINDOW)
    ]


@router.post(
    "/interns/{intern_id}/availability-unlock",
    response_model=AvailabilityUnlockOut,
    summary="Libera o estagiário para alterar a disponibilidade por um prazo (uma alteração)",
)
def unlock(
    intern_id: str,
    body: AvailabilityUnlockIn,
    request: Request,
    current: CurrentUser = Depends(require_role(["SUPERVISOR"])),
    repo: SqlAlchemyAvailabilityLockRepository = Depends(_get_repo),
    audit: AuditRecorder = Depends(_get_audit),
) -> AvailabilityUnlockOut:
    until = GrantAvailabilityUnlock(repo, audit).execute(
        Actor(current.sub, current.role), intern_id, body.hours, getattr(request.state, "correlation_id", None)
    )
    return AvailabilityUnlockOut(unlocked_until=until)


@router.post(
    "/interns/{intern_id}/availability-relock",
    status_code=204,
    summary="Recusa o pedido ou revoga a liberação — a disponibilidade volta a ficar travada",
)
def relock(
    intern_id: str,
    request: Request,
    current: CurrentUser = Depends(require_role(["SUPERVISOR"])),
    repo: SqlAlchemyAvailabilityLockRepository = Depends(_get_repo),
    audit: AuditRecorder = Depends(_get_audit),
) -> None:
    RevokeAvailabilityUnlock(repo, audit).execute(
        Actor(current.sub, current.role), intern_id, getattr(request.state, "correlation_id", None)
    )
