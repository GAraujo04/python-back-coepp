"""Rotas do supervisor/administrativo para a trava de disponibilidade do
estagiário: ver pedidos, liberar por um prazo, recusar/revogar. Regra em
application/availability_lock.py."""

from __future__ import annotations

from collections.abc import Iterator

from fastapi import APIRouter, Depends, Request
from sqlalchemy.orm import Session

from ....shared.audit.audit_recorder import AuditRecorder
from ....shared.audit.sql_audit_recorder import SqlAuditRecorder
from ....shared.auth.jwt_auth import CurrentUser, require_role
from ....shared.db.session import get_session
from ..application.availability_lock import Actor, GrantAvailabilityUnlock, RevokeAvailabilityUnlock, utcnow
from ..infrastructure.sqlalchemy_availability_lock_repository import SqlAlchemyAvailabilityLockRepository
from .schemas import AvailabilityUnlockIn, AvailabilityUnlockOut, PendingAvailabilityRequestOut

router = APIRouter(prefix="/api", tags=["availability-lock"])


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
    summary="Pedidos de mudança de disponibilidade e liberações em vigor (Supervisor: seus estagiários; Admin: todos)",
)
def list_requests(
    current: CurrentUser = Depends(require_role(["SUPERVISOR", "ADMIN"])),
    repo: SqlAlchemyAvailabilityLockRepository = Depends(_get_repo),
) -> list[PendingAvailabilityRequestOut]:
    supervisor_id = None if current.role == "ADMIN" else current.sub
    return [
        PendingAvailabilityRequestOut(
            intern_id=r.intern_id,
            intern_name=r.intern_name,
            ra=r.ra,
            requested_at=r.requested_at,
            reason=r.reason,
            unlocked_until=r.unlocked_until,
        )
        for r in repo.list_open(supervisor_id, utcnow())
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
    current: CurrentUser = Depends(require_role(["SUPERVISOR", "ADMIN"])),
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
    current: CurrentUser = Depends(require_role(["SUPERVISOR", "ADMIN"])),
    repo: SqlAlchemyAvailabilityLockRepository = Depends(_get_repo),
    audit: AuditRecorder = Depends(_get_audit),
) -> None:
    RevokeAvailabilityUnlock(repo, audit).execute(
        Actor(current.sub, current.role), intern_id, getattr(request.state, "correlation_id", None)
    )
