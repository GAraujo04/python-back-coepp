"""Lista/obtém triagens visíveis ao ator (escopo por RLS).

Porta features/screening/application/query-screenings.ts.
"""

from __future__ import annotations

from ....shared.audit.audit_recorder import AuditEvent, AuditRecorder
from ....shared.errors.app_error import NotFoundError
from ..domain.screening_repository import AccessContext, ScreeningRecord, ScreeningRepository


class ListScreenings:
    def __init__(self, repo: ScreeningRepository) -> None:
        self._repo = repo

    def execute(self, actor: AccessContext) -> list[ScreeningRecord]:
        return self._repo.list_for_actor(actor)


class GetScreening:
    """Obtém uma triagem. Leitura de prontuário é auditada (LGPD Art. 37)."""

    def __init__(self, repo: ScreeningRepository, audit: AuditRecorder) -> None:
        self._repo = repo
        self._audit = audit

    def execute(self, actor: AccessContext, id: str, correlation_id: str | None = None) -> ScreeningRecord:
        screening = self._repo.find_by_id(actor, id)
        if not screening:
            raise NotFoundError("Triagem não encontrada.")
        self._audit.record(
            AuditEvent(
                actor_id=actor.user_id,
                action="READ",
                resource_type="screening",
                resource_id=id,
                correlation_id=correlation_id,
            )
        )
        return screening
