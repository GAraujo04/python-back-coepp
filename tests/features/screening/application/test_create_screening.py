"""CreateScreening: a triagem é preenchida uma única vez por paciente.
Fakes em memória (sem banco), mesmo estilo dos testes de auth."""

from __future__ import annotations

from datetime import datetime

import pytest

from app.features.screening.application.create_screening import CreateScreening, CreateScreeningInput
from app.features.screening.domain.screening_content import ScreeningType
from app.features.screening.domain.screening_repository import (
    AccessContext,
    NewScreening,
    ScreeningRecord,
    ScreeningRepository,
)
from app.shared.audit.audit_recorder import AuditEvent, AuditRecorder
from app.shared.errors.app_error import ConflictError

INTERN = AccessContext(user_id="intern-1", role="INTERN")


class FakeRepo(ScreeningRepository):
    def __init__(self, has_screening: bool) -> None:
        self.has_screening = has_screening
        self.created: list[NewScreening] = []
        self.checked: list[str] = []

    def patient_has_screening(self, ctx: AccessContext, patient_id: str) -> bool:
        self.checked.append(patient_id)
        return self.has_screening

    def create(self, ctx: AccessContext, data: NewScreening) -> ScreeningRecord:
        self.created.append(data)
        now = datetime(2026, 10, 6)
        return ScreeningRecord(
            id="doc-1",
            numero="2026-0001",
            type=data.type,
            status="RASCUNHO",
            version=1,
            patient_id=data.patient_id,
            author_id=data.author_id,
            co_author_ids=data.co_author_ids,
            content=data.content,
            created_at=now,
            updated_at=now,
        )

    def list_for_actor(self, ctx: AccessContext) -> list[ScreeningRecord]:
        return []

    def find_by_id(self, ctx: AccessContext, id: str) -> ScreeningRecord | None:
        return None

    def update_draft(
        self, ctx: AccessContext, id: str, content: dict[str, object], expected_version: int
    ) -> ScreeningRecord:
        raise NotImplementedError

    def delete(self, ctx: AccessContext, id: str) -> None:
        raise NotImplementedError


class FakeAudit(AuditRecorder):
    def record(self, event: AuditEvent) -> None:
        pass


def _input(type_: ScreeningType) -> CreateScreeningInput:
    return CreateScreeningInput(actor=INTERN, type=type_, patient_id="patient-1")


@pytest.mark.parametrize("type_", ["SCREENING_ADULT", "SCREENING_CHILD"])
def test_recusa_segunda_triagem_do_mesmo_paciente(type_: ScreeningType) -> None:
    repo = FakeRepo(has_screening=True)
    with pytest.raises(ConflictError):
        CreateScreening(repo, FakeAudit()).execute(_input(type_))
    assert repo.created == []


def test_cria_a_primeira_triagem() -> None:
    repo = FakeRepo(has_screening=False)
    CreateScreening(repo, FakeAudit()).execute(_input("SCREENING_ADULT"))
    assert len(repo.created) == 1


def test_outros_documentos_nao_passam_pela_regra() -> None:
    repo = FakeRepo(has_screening=True)
    CreateScreening(repo, FakeAudit()).execute(_input("EVOLUTION"))
    assert repo.checked == []
    assert len(repo.created) == 1
