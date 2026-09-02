"""Rotas de salas: status (Admin) e realocação manual (Admin).

Porta features/rooms/presentation/routes.ts.
"""

from __future__ import annotations

from collections.abc import Iterator

from fastapi import APIRouter, Depends, Request
from sqlalchemy.orm import Session

from ....shared.audit.audit_recorder import AuditEvent, AuditRecorder
from ....shared.audit.sql_audit_recorder import SqlAuditRecorder
from ....shared.auth.jwt_auth import CurrentUser, require_role
from ....shared.db.session import get_session
from ....shared.http.camel_model import CamelModel
from ....shared.http.utc_datetime import UtcDatetime
from ..infrastructure.sqlalchemy_room_repository import SqlAlchemyRoomRepository

router = APIRouter(prefix="/api", tags=["rooms"], dependencies=[Depends(require_role(["ADMIN"]))])


class OccupiedByOut(CamelModel):
    appointment_id: str
    scheduled_at: UtcDatetime
    patient_name: str
    intern_name: str


class RoomStatusOut(CamelModel):
    id: str
    name: str
    active: bool
    occupied_by: OccupiedByOut | None


class ReassignRequest(CamelModel):
    appointment_id: str
    room_id: str


def _get_db() -> Iterator[Session]:
    with get_session() as session:
        yield session


def _get_repo(db: Session = Depends(_get_db)) -> SqlAlchemyRoomRepository:
    return SqlAlchemyRoomRepository(db)


def _get_audit(db: Session = Depends(_get_db)) -> AuditRecorder:
    return SqlAuditRecorder(db)


@router.get(
    "/rooms", response_model=list[RoomStatusOut], summary="Lista salas com status (ocupada/disponível) — Administrativo"
)
def list_rooms(repo: SqlAlchemyRoomRepository = Depends(_get_repo)) -> list[RoomStatusOut]:
    return [
        RoomStatusOut(
            id=r.id,
            name=r.name,
            active=r.active,
            occupied_by=OccupiedByOut(
                appointment_id=r.occupied_by.appointment_id,
                scheduled_at=r.occupied_by.scheduled_at,
                patient_name=r.occupied_by.patient_name,
                intern_name=r.occupied_by.intern_name,
            )
            if r.occupied_by
            else None,
        )
        for r in repo.list_with_status()
    ]


@router.patch(
    "/rooms/reassign", status_code=204, summary="Troca a sala de um agendamento, validando conflito — Administrativo"
)
def reassign(
    body: ReassignRequest,
    request: Request,
    current: CurrentUser = Depends(require_role(["ADMIN"])),
    repo: SqlAlchemyRoomRepository = Depends(_get_repo),
    audit: AuditRecorder = Depends(_get_audit),
) -> None:
    previous_room_id = repo.reassign(body.appointment_id, body.room_id)
    audit.record(
        AuditEvent(
            actor_id=current.sub,
            action="UPDATE",
            resource_type="appointment",
            resource_id=body.appointment_id,
            correlation_id=getattr(request.state, "correlation_id", None),
            diff={"roomId": body.room_id, "previousRoomId": previous_room_id},
        )
    )
