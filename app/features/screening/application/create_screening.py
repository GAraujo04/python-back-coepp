"""Cria uma triagem em RASCUNHO. O autor é o estagiário logado; coautores
são outros estagiários. O Nº é gerado pelo repositório. Conteúdo validado
por tipo.

Porta features/screening/application/create-screening.ts.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from ....shared.audit.audit_recorder import AuditEvent, AuditRecorder
from ..domain.screening_content import ScreeningType, validate_screening_content
from ..domain.screening_repository import AccessContext, NewScreening, ScreeningRecord, ScreeningRepository


@dataclass
class CreateScreeningInput:
    actor: AccessContext
    type: ScreeningType
    patient_id: str
    co_author_ids: list[str] = field(default_factory=list)
    content: dict[str, object] = field(default_factory=dict)
    correlation_id: str | None = None


class CreateScreening:
    def __init__(self, repo: ScreeningRepository, audit: AuditRecorder) -> None:
        self._repo = repo
        self._audit = audit

    def execute(self, input: CreateScreeningInput) -> ScreeningRecord:
        content = validate_screening_content(input.type, input.content)
        # Coautores sem duplicar o próprio autor.
        co_author_ids = [i for i in dict.fromkeys(input.co_author_ids) if i != input.actor.user_id]

        screening = self._repo.create(
            input.actor,
            NewScreening(
                type=input.type,
                patient_id=input.patient_id,
                author_id=input.actor.user_id,
                co_author_ids=co_author_ids,
                content=content,
            ),
        )

        self._audit.record(
            AuditEvent(
                actor_id=input.actor.user_id,
                action="CREATE",
                resource_type="screening",
                resource_id=screening.id,
                correlation_id=input.correlation_id,
            )
        )

        return screening
