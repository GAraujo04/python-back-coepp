"""Persistência da trava de disponibilidade (colunas em `users`, migration
0005). `users` e `assignments` não têm RLS — mesma situação do restante
desta slice."""

from __future__ import annotations

from datetime import datetime

from sqlalchemy import or_, select
from sqlalchemy.orm import Session

from ....shared.db.models import Assignment, User
from ..application.availability_lock import (
    AvailabilityChange,
    AvailabilityLockRepository,
    AvailabilityLockState,
    PendingAvailabilityRequest,
)


class SqlAlchemyAvailabilityLockRepository(AvailabilityLockRepository):
    def __init__(self, session: Session) -> None:
        self._session = session

    def _intern(self, intern_id: str, for_update: bool = False) -> User | None:
        stmt = select(User).where(User.id == intern_id, User.role == "INTERN")
        if for_update:
            stmt = stmt.with_for_update()
        return self._session.scalar(stmt)

    def get_state(self, intern_id: str) -> AvailabilityLockState | None:
        user = self._intern(intern_id)
        if not user:
            return None
        return AvailabilityLockState(
            unlocked_until=user.availability_unlocked_until,
            requested_at=user.availability_change_requested_at,
            request_reason=user.availability_change_reason,
        )

    def save_request(self, intern_id: str, reason: str, at: datetime) -> None:
        user = self._intern(intern_id)
        if user:
            user.availability_change_requested_at = at
            user.availability_change_reason = reason
            self._session.flush()

    def unlock(self, intern_id: str, until: datetime) -> None:
        user = self._intern(intern_id)
        if user:
            user.availability_unlocked_until = until
            user.availability_change_requested_at = None
            user.availability_change_reason = None
            self._session.flush()

    def relock(self, intern_id: str) -> None:
        user = self._intern(intern_id)
        if user:
            user.availability_unlocked_until = None
            user.availability_change_requested_at = None
            user.availability_change_reason = None
            self._session.flush()

    def consume_unlock(self, intern_id: str, now: datetime) -> bool:
        # UPDLOCK na linha: o segundo salvamento simultâneo espera o
        # primeiro commitar e então já encontra a edição travada.
        user = self._intern(intern_id, for_update=True)
        if not user or not user.availability_unlocked_until or user.availability_unlocked_until <= now:
            return False
        user.availability_unlocked_until = None
        self._session.flush()
        return True

    def is_responsible(self, supervisor_id: str, intern_id: str) -> bool:
        # Duas consultas e não `SELECT EXISTS(...) OR EXISTS(...)`: o SQL
        # Server não tem booleano como valor de coluna.
        academic = self._session.scalar(
            select(User.id).where(User.id == intern_id, User.academic_supervisor_id == supervisor_id)
        )
        if academic:
            return True
        assigned = self._session.scalar(
            select(Assignment.id).where(
                Assignment.intern_id == intern_id, Assignment.supervisor_id == supervisor_id, Assignment.active
            )
        )
        return assigned is not None

    def list_open(self, supervisor_id: str | None, now: datetime) -> list[PendingAvailabilityRequest]:
        stmt = (
            select(User)
            .where(
                User.role == "INTERN",
                or_(User.availability_change_requested_at.isnot(None), User.availability_unlocked_until > now),
            )
            .order_by(User.availability_change_requested_at.asc(), User.full_name.asc())
        )
        if supervisor_id:
            supervised = select(Assignment.intern_id).where(
                Assignment.supervisor_id == supervisor_id, Assignment.active
            )
            stmt = stmt.where(or_(User.academic_supervisor_id == supervisor_id, User.id.in_(supervised)))
        return [
            PendingAvailabilityRequest(
                intern_id=u.id,
                intern_name=u.full_name,
                ra=u.ra,
                requested_at=u.availability_change_requested_at,
                reason=u.availability_change_reason,
                unlocked_until=u.availability_unlocked_until
                if u.availability_unlocked_until and u.availability_unlocked_until > now
                else None,
            )
            for u in self._session.scalars(stmt).all()
        ]

    def list_changes_since(self, since: datetime) -> list[AvailabilityChange]:
        """Estagiários que alteraram a disponibilidade a partir de `since`,
        mais recente primeiro, com a disponibilidade atual (a nova)."""
        rows = self._session.scalars(
            select(User)
            .where(User.role == "INTERN", User.availability_changed_at >= since)
            .order_by(User.availability_changed_at.desc())
        ).all()
        return [
            AvailabilityChange(
                intern_id=u.id,
                intern_name=u.full_name,
                ra=u.ra,
                changed_at=u.availability_changed_at,
                windows=sorted((w.weekday, w.start_time, w.end_time) for w in u.availability_windows),
            )
            for u in rows
            if u.availability_changed_at is not None
        ]
