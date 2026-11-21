"""Lê, por papel, o estado que vira aviso. Reaproveita os escopos que já
existem — a RLS de clinical_documents e a regra de "supervisor
responsável" da trava de disponibilidade —, para o sininho nunca mostrar
algo que a tela correspondente não mostraria."""

from __future__ import annotations

from datetime import datetime

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from ....shared.db.models import Assignment, ClinicalDocument, MatchProposal, PendingMatchRequest, User
from ....shared.db.session import with_rls_context
from ...documents.infrastructure.sqlalchemy_document_repository import SqlAlchemyDocumentRepository
from ...enrollment.infrastructure.sqlalchemy_availability_lock_repository import (
    SqlAlchemyAvailabilityLockRepository,
)
from ..domain.notification import INFO_WINDOW, Notification


class SqlAlchemyNotificationSource:
    def __init__(self, session: Session) -> None:
        self._session = session

    def seen_at(self, user_id: str) -> datetime | None:
        return self._session.scalar(select(User.notifications_seen_at).where(User.id == user_id))

    def mark_seen(self, user_id: str, at: datetime) -> None:
        user = self._session.get(User, user_id)
        if user:
            user.notifications_seen_at = at
            self._session.flush()

    def for_user(self, user_id: str, role: str, now: datetime) -> list[Notification]:
        if role == "SUPERVISOR":
            return self._review_queue(user_id, role) + self._availability_requests(user_id, now)
        if role == "ADMIN":
            return self._pending_matches() + self._assignments_without_supervisor() + self._availability_changes(now)
        if role == "INTERN":
            return self._intern_documents(user_id, now) + self._availability_unlocked(user_id, now)
        return []

    # --- supervisor -------------------------------------------------------

    def _review_queue(self, user_id: str, role: str) -> list[Notification]:
        queue = SqlAlchemyDocumentRepository(self._session).list_review_queue(user_id, role)
        if not queue:
            return []
        oldest = min(i.updated_at for i in queue)
        return [Notification(kind="REVIEW_QUEUE", actionable=True, at=oldest, count=len(queue))]

    def _availability_requests(self, supervisor_id: str, now: datetime) -> list[Notification]:
        # Só os pedidos ainda sem decisão; liberação em vigor não é pendência
        # do supervisor (é do estagiário).
        rows = SqlAlchemyAvailabilityLockRepository(self._session).list_open(supervisor_id, now)
        pending = [r for r in rows if r.requested_at and not r.unlocked_until]
        if not pending:
            return []
        oldest = min(r.requested_at for r in pending if r.requested_at)
        return [Notification(kind="AVAILABILITY_REQUESTS", actionable=True, at=oldest, count=len(pending))]

    # --- admin ------------------------------------------------------------

    def _pending_matches(self) -> list[Notification]:
        # Pacientes (distintos) que o pareamento não conseguiu encaixar e que
        # continuam sem par — some sozinho quando ganham vínculo ou proposta.
        count, oldest = self._session.execute(
            select(
                func.count(func.distinct(PendingMatchRequest.patient_id)), func.min(PendingMatchRequest.created_at)
            ).where(
                PendingMatchRequest.status == "pendente_ajuste_manual",
                PendingMatchRequest.patient_id.not_in(select(Assignment.patient_id).where(Assignment.active)),
                PendingMatchRequest.patient_id.not_in(select(MatchProposal.patient_id)),
            )
        ).one()
        return [Notification(kind="PENDING_MATCHES", actionable=True, at=oldest, count=count)] if count else []

    def _assignments_without_supervisor(self) -> list[Notification]:
        count = self._session.scalar(
            select(func.count(Assignment.id)).where(Assignment.active, Assignment.supervisor_id.is_(None))
        )
        return [Notification(kind="ASSIGNMENTS_WITHOUT_SUPERVISOR", actionable=True, count=count)] if count else []

    def _availability_changes(self, now: datetime) -> list[Notification]:
        # Informativo: a decisão foi do supervisor; o administrativo só
        # precisa saber que a disponibilidade mudou (e ver a nova).
        changes = SqlAlchemyAvailabilityLockRepository(self._session).list_changes_since(now - INFO_WINDOW)
        if not changes:
            return []
        latest = max(c.changed_at for c in changes)
        return [Notification(kind="AVAILABILITY_CHANGED", actionable=False, at=latest, count=len(changes))]

    # --- estagiário -------------------------------------------------------

    def _intern_documents(self, user_id: str, now: datetime) -> list[Notification]:
        since = now - INFO_WINDOW

        def _do(session: Session) -> list[Notification]:
            # Sob a RLS do estagiário: só documentos de que ele é autor/coautor.
            docs = session.scalars(
                select(ClinicalDocument).where(
                    ClinicalDocument.status.in_(("REVISAO_SOLICITADA", "APROVADO_LOCKED", "REJEITADO"))
                )
            ).all()
            out: list[Notification] = []
            for d in docs:
                common = {"document_id": d.id, "doc_type": d.type, "patient_code": d.patient.code, "at": d.updated_at}
                if d.status == "REVISAO_SOLICITADA":
                    out.append(Notification(kind="CHANGES_REQUESTED", actionable=True, **common))  # type: ignore[arg-type]
                elif d.updated_at >= since:
                    kind = "DOCUMENT_APPROVED" if d.status == "APROVADO_LOCKED" else "DOCUMENT_REJECTED"
                    out.append(Notification(kind=kind, actionable=False, **common))  # type: ignore[arg-type]
            return out

        return with_rls_context(self._session, user_id, "INTERN", _do)

    def _availability_unlocked(self, user_id: str, now: datetime) -> list[Notification]:
        state = SqlAlchemyAvailabilityLockRepository(self._session).get_state(user_id)
        if not state or not state.editable(now):
            return []
        return [Notification(kind="AVAILABILITY_UNLOCKED", actionable=True, until=state.unlocked_until)]
