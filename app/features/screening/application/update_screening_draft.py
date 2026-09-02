"""Auto-save do rascunho de triagem. Valida o conteúdo e usa concorrência
otimista.

Porta features/screening/application/update-screening-draft.ts.
"""

from __future__ import annotations

from dataclasses import dataclass

from ....shared.audit.audit_recorder import AuditEvent, AuditRecorder
from ....shared.errors.app_error import NotFoundError
from ..domain.screening_content import validate_screening_content
from ..domain.screening_repository import AccessContext, ScreeningRecord, ScreeningRepository


@dataclass
class UpdateDraftInput:
    actor: AccessContext
    screening_id: str
    content: dict[str, object]
    expected_version: int
    correlation_id: str | None = None


class UpdateScreeningDraft:
    def __init__(self, repo: ScreeningRepository, audit: AuditRecorder) -> None:
        self._repo = repo
        self._audit = audit

    def execute(self, input: UpdateDraftInput) -> ScreeningRecord:
        current = self._repo.find_by_id(input.actor, input.screening_id)
        if not current:
            raise NotFoundError("Triagem não encontrada.")

        content = validate_screening_content(current.type, input.content)
        updated = self._repo.update_draft(input.actor, input.screening_id, content, input.expected_version)

        self._audit.record(
            AuditEvent(
                actor_id=input.actor.user_id,
                action="UPDATE",
                resource_type="screening",
                resource_id=updated.id,
                correlation_id=input.correlation_id,
            )
        )

        return updated
