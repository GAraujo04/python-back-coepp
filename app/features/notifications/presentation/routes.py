"""Rotas dos avisos internos (o sininho do menu). Regra em
domain/notification.py."""

from __future__ import annotations

from collections.abc import Iterator
from datetime import UTC, datetime

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from ....shared.auth.jwt_auth import CurrentUser, get_current_user
from ....shared.db.session import get_session
from ....shared.http.camel_model import CamelModel
from ....shared.http.utc_datetime import UtcDatetime
from ..domain.notification import NotificationKind, is_unseen, sort_for_display, unread_count
from ..infrastructure.sqlalchemy_notification_source import SqlAlchemyNotificationSource

router = APIRouter(prefix="/api", tags=["notifications"])


class NotificationOut(CamelModel):
    kind: NotificationKind
    actionable: bool
    at: UtcDatetime | None
    count: int
    document_id: str | None
    doc_type: str | None
    patient_code: str | None
    until: UtcDatetime | None
    # Informativo ainda não visto (pendências são sempre "novas" enquanto existem).
    unseen: bool


class NotificationsOut(CamelModel):
    unread: int
    items: list[NotificationOut]


def _get_db() -> Iterator[Session]:
    with get_session() as session:
        yield session


def _now() -> datetime:
    return datetime.now(UTC).replace(tzinfo=None)


@router.get(
    "/notifications", response_model=NotificationsOut, summary="Avisos do usuário logado (pendências e informativos)"
)
def list_notifications(
    current: CurrentUser = Depends(get_current_user), db: Session = Depends(_get_db)
) -> NotificationsOut:
    source = SqlAlchemyNotificationSource(db)
    items = sort_for_display(source.for_user(current.sub, current.role, _now()))
    seen = source.seen_at(current.sub)
    return NotificationsOut(
        unread=unread_count(items, seen),
        items=[
            NotificationOut(
                kind=n.kind,
                actionable=n.actionable,
                at=n.at,
                count=n.count,
                document_id=n.document_id,
                doc_type=n.doc_type,
                patient_code=n.patient_code,
                until=n.until,
                unseen=is_unseen(n, seen),
            )
            for n in items
        ],
    )


@router.post("/notifications/seen", status_code=204, summary="Marca os avisos informativos como vistos (abriu a lista)")
def mark_seen(current: CurrentUser = Depends(get_current_user), db: Session = Depends(_get_db)) -> None:
    SqlAlchemyNotificationSource(db).mark_seen(current.sub, _now())
