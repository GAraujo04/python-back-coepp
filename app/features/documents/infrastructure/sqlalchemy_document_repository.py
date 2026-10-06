"""Persistência das transições/revisão de documentos. Escritas sob
contexto ADMIN (coordenação).

Porta features/documents/infrastructure/prisma-document-repository.ts.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import UTC, datetime
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from ....shared.crypto.field_encryption import decrypt_field
from ....shared.crypto.json_field import decrypt_json
from ....shared.db.models import ClinicalDocument, DocumentApproval, DocumentSignature, ReviewComment, User
from ....shared.db.session import with_rls_context
from ..domain.document_status import DocStatus

_REVIEW_STATES = ("ENVIADO_PARA_SUPERVISAO", "EM_REVISAO")


@dataclass
class DocForTransition:
    id: str
    type: str
    status: DocStatus
    author_id: str
    co_author_ids: list[str]
    patient_id: str
    content: dict[str, Any]


@dataclass
class QueueItem:
    id: str
    numero: str | None
    type: str
    status: str
    author_name: str
    patient_name: str
    # Código do paciente (Patient.code) — é o "Nº" exibido no documento, o
    # identificador pelo qual o supervisor sabe de qual paciente se trata.
    patient_code: str
    updated_at: datetime


@dataclass
class ReportItem(QueueItem):
    author_id: str = ""
    # "Chegada" ao supervisor: a última assinatura do estagiário, que é
    # gravada a cada envio (SUBMIT) — um reenvio após ajustes conta como
    # nova chegada. Documento sem assinatura de estagiário (legado) usa
    # updated_at.
    submitted_at: datetime | None = None


@dataclass
class SignatureView:
    signer_name: str
    signer_role: str
    signer_ref: str | None
    provider: str
    signed_at: datetime


@dataclass
class CommentView:
    id: str
    body: str
    reviewer_name: str
    created_at: datetime


@dataclass
class DocForReview(QueueItem):
    content: dict[str, Any] = field(default_factory=dict)
    comments: list[CommentView] = field(default_factory=list)
    signatures: list[SignatureView] = field(default_factory=list)


@dataclass
class ApprovalWrite:
    supervisor_id: str
    content_hash: str


@dataclass
class CommentWrite:
    reviewer_id: str
    body: str


@dataclass
class TransitionWrite:
    id: str
    to_status: DocStatus
    lock: bool
    approval: ApprovalWrite | None = None
    comment: CommentWrite | None = None


@dataclass
class AddSignatureInput:
    document_id: str
    signer_id: str
    signer_role: str
    content_hash: str
    signature_hash: str
    provider: str


class SqlAlchemyDocumentRepository:
    def __init__(self, session: Session) -> None:
        self._session = session

    def get_for_transition(self, actor_id: str, document_id: str) -> DocForTransition | None:
        def _do(session: Session) -> DocForTransition | None:
            doc = session.get(ClinicalDocument, document_id)
            if not doc:
                return None
            return DocForTransition(
                id=doc.id,
                type=doc.type,
                status=doc.status,  # type: ignore[arg-type]  # CHECK constraint no banco garante o conjunto fechado
                author_id=doc.author_id,
                co_author_ids=[u.id for u in doc.co_authors],
                patient_id=doc.patient_id,
                content=decrypt_json(doc.content_enc),
            )

        return with_rls_context(self._session, actor_id, "ADMIN", _do)

    def transition(self, actor_id: str, w: TransitionWrite) -> None:
        def _do(session: Session) -> None:
            doc = session.get(ClinicalDocument, w.id)
            assert doc is not None  # já validado por get_for_transition antes desta chamada
            doc.status = w.to_status
            doc.locked_at = datetime.now(UTC).replace(tzinfo=None) if w.lock else None

            if w.approval:
                supervisor = session.get(User, w.approval.supervisor_id)
                sup_name = supervisor.full_name if supervisor else "Supervisor"
                sup_crp = (supervisor.crp if supervisor else "") or ""
                signature = f"{sup_name} — {sup_crp}".strip()
                session.add(
                    DocumentApproval(
                        document_id=w.id,
                        supervisor_id=w.approval.supervisor_id,
                        signature=signature,
                        content_hash=w.approval.content_hash,
                    )
                )
            if w.comment:
                session.add(ReviewComment(document_id=w.id, reviewer_id=w.comment.reviewer_id, body=w.comment.body))
            session.flush()

        with_rls_context(self._session, actor_id, "ADMIN", _do)

    def add_signature(self, actor_id: str, input: AddSignatureInput) -> None:
        def _do(session: Session) -> None:
            signer = session.get(User, input.signer_id)
            signer_ref = (signer.ra if input.signer_role == "INTERN" else signer.crp) if signer else None
            session.add(
                DocumentSignature(
                    document_id=input.document_id,
                    signer_id=input.signer_id,
                    signer_role=input.signer_role,
                    signer_name=signer.full_name if signer else "",
                    signer_ref=signer_ref,
                    content_hash=input.content_hash,
                    signature_hash=input.signature_hash,
                    provider=input.provider,
                )
            )
            session.flush()

        with_rls_context(self._session, actor_id, "ADMIN", _do)

    def list_review_queue(self, actor_id: str) -> list[QueueItem]:
        def _do(session: Session) -> list[QueueItem]:
            rows = session.scalars(
                select(ClinicalDocument)
                .where(ClinicalDocument.status.in_(_REVIEW_STATES))
                .order_by(ClinicalDocument.updated_at.asc())
            ).all()
            return [
                QueueItem(
                    id=r.id,
                    numero=r.numero,
                    type=r.type,
                    status=r.status,
                    author_name=r.author.full_name,
                    patient_name=decrypt_field(r.patient.full_name_enc),
                    patient_code=r.patient.code,
                    updated_at=r.updated_at,
                )
                for r in rows
            ]

        return with_rls_context(self._session, actor_id, "ADMIN", _do)

    def list_reports(self, actor_id: str, role: str) -> list[ReportItem]:
        """Documentos já enviados (tudo menos RASCUNHO), em ordem de
        chegada. Diferente da fila de revisão, roda sob o papel REAL do
        ator: a RLS restringe o supervisor aos pacientes dos quais ele é
        supervisor num vínculo ativo, e o admin vê todos."""

        def _do(session: Session) -> list[ReportItem]:
            rows = session.scalars(select(ClinicalDocument).where(ClinicalDocument.status != "RASCUNHO")).all()
            items = []
            for r in rows:
                intern_signatures = [s.signed_at for s in r.signatures if s.signer_role == "INTERN"]
                items.append(
                    ReportItem(
                        id=r.id,
                        numero=r.numero,
                        type=r.type,
                        status=r.status,
                        author_name=r.author.full_name,
                        patient_name=decrypt_field(r.patient.full_name_enc),
                        patient_code=r.patient.code,
                        updated_at=r.updated_at,
                        author_id=r.author_id,
                        submitted_at=max(intern_signatures) if intern_signatures else r.updated_at,
                    )
                )
            items.sort(key=lambda i: (i.submitted_at or i.updated_at, i.id))
            return items

        return with_rls_context(self._session, actor_id, role, _do)

    def get_for_review(self, actor_id: str, document_id: str) -> DocForReview | None:
        def _do(session: Session) -> DocForReview | None:
            r = session.get(ClinicalDocument, document_id)
            if not r:
                return None
            return DocForReview(
                id=r.id,
                numero=r.numero,
                type=r.type,
                status=r.status,
                author_name=r.author.full_name,
                patient_name=decrypt_field(r.patient.full_name_enc),
                patient_code=r.patient.code,
                updated_at=r.updated_at,
                content=decrypt_json(r.content_enc),
                comments=[
                    CommentView(id=c.id, body=c.body, reviewer_name=c.reviewer.full_name, created_at=c.created_at)
                    for c in r.comments
                ],
                signatures=[
                    SignatureView(
                        signer_name=s.signer_name,
                        signer_role=s.signer_role,
                        signer_ref=s.signer_ref,
                        provider=s.provider,
                        signed_at=s.signed_at,
                    )
                    for s in r.signatures
                ],
            )

        return with_rls_context(self._session, actor_id, "ADMIN", _do)
