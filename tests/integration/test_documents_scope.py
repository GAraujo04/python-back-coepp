"""Fila de revisão, leitura e decisão limitadas ao supervisor do paciente."""

from __future__ import annotations

import pytest
from sqlalchemy.orm import Session

from app.features.documents.application.transition_document import TransitionDocument, TransitionInput
from app.features.documents.infrastructure.internal_signature_provider import InternalSignatureProvider
from app.features.documents.infrastructure.sqlalchemy_document_repository import SqlAlchemyDocumentRepository
from app.shared.audit.audit_recorder import AuditEvent, AuditRecorder
from app.shared.errors.app_error import ForbiddenError

from .conftest import World


class NoAudit(AuditRecorder):
    def record(self, event: AuditEvent) -> None:
        pass


def _queue_ids(db: Session, actor_id: str, role: str) -> set[str]:
    return {i.id for i in SqlAlchemyDocumentRepository(db).list_review_queue(actor_id, role)}


def test_fila_mostra_so_os_pacientes_do_supervisor(db: Session, world: World) -> None:
    assert world.doc.id in _queue_ids(db, world.sup_a.id, "SUPERVISOR")
    assert world.doc.id not in _queue_ids(db, world.sup_b.id, "SUPERVISOR")
    assert world.doc.id in _queue_ids(db, world.admin.id, "ADMIN")


def test_supervisor_de_fora_nao_le_o_documento(db: Session, world: World) -> None:
    repo = SqlAlchemyDocumentRepository(db)
    assert repo.get_for_review(world.sup_a.id, "SUPERVISOR", world.doc.id) is not None
    assert repo.get_for_review(world.sup_b.id, "SUPERVISOR", world.doc.id) is None


def test_relatorios_respeitam_o_vinculo(db: Session, world: World) -> None:
    repo = SqlAlchemyDocumentRepository(db)
    assert world.doc.id in {r.id for r in repo.list_reports(world.sup_a.id, "SUPERVISOR")}
    assert world.doc.id not in {r.id for r in repo.list_reports(world.sup_b.id, "SUPERVISOR")}


def _transition(db: Session, actor_id: str, role: str, doc_id: str, action: str) -> str:
    use_case = TransitionDocument(SqlAlchemyDocumentRepository(db), NoAudit(), InternalSignatureProvider())
    return use_case.execute(TransitionInput(actor_id=actor_id, role=role, document_id=doc_id, action=action)).status  # type: ignore[arg-type]


def test_supervisor_de_fora_nao_decide(db: Session, world: World) -> None:
    with pytest.raises(ForbiddenError):
        _transition(db, world.sup_b.id, "SUPERVISOR", world.doc.id, "TAKE")


def test_supervisor_do_paciente_decide(db: Session, world: World) -> None:
    assert _transition(db, world.sup_a.id, "SUPERVISOR", world.doc.id, "TAKE") == "EM_REVISAO"
