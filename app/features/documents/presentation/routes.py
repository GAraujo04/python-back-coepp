"""Rotas de transição e revisão de documentos clínicos (máquina de estados).

Porta features/documents/presentation/routes.ts.
"""

from __future__ import annotations

from collections.abc import Iterator

from fastapi import APIRouter, Depends, Request
from sqlalchemy.orm import Session

from ....shared.audit.audit_recorder import AuditRecorder
from ....shared.audit.sql_audit_recorder import SqlAuditRecorder
from ....shared.auth.jwt_auth import CurrentUser, get_current_user, require_role
from ....shared.db.session import get_session
from ....shared.errors.app_error import NotFoundError
from ..application.transition_document import TransitionDocument, TransitionInput
from ..infrastructure.internal_signature_provider import InternalSignatureProvider
from ..infrastructure.sqlalchemy_document_repository import SqlAlchemyDocumentRepository
from .schemas import CommentOut, DocForReviewOut, QueueItemOut, SignatureOut, TransitionRequest, TransitionResponse

router = APIRouter(prefix="/api", tags=["documents"])


def _get_db() -> Iterator[Session]:
    with get_session() as session:
        yield session


def _get_repo(db: Session = Depends(_get_db)) -> SqlAlchemyDocumentRepository:
    return SqlAlchemyDocumentRepository(db)


def _get_audit(db: Session = Depends(_get_db)) -> AuditRecorder:
    return SqlAuditRecorder(db)


@router.post(
    "/documents/{document_id}/transitions",
    response_model=TransitionResponse,
    summary="Executa uma transição no documento (submeter/aprovar/solicitar ajustes/rejeitar)",
)
def transition(
    document_id: str,
    body: TransitionRequest,
    request: Request,
    current: CurrentUser = Depends(get_current_user),
    repo: SqlAlchemyDocumentRepository = Depends(_get_repo),
    audit: AuditRecorder = Depends(_get_audit),
) -> TransitionResponse:
    use_case = TransitionDocument(repo, audit, InternalSignatureProvider())
    result = use_case.execute(
        TransitionInput(
            actor_id=current.sub,
            role=current.role,  # type: ignore[arg-type]  # validado pelo próprio resolve_transition (rejeita papel desconhecido)
            document_id=document_id,
            action=body.action,
            comment=body.comment,
            correlation_id=getattr(request.state, "correlation_id", None),
        )
    )
    return TransitionResponse(id=result.id, status=result.status)


@router.get("/documents/review-queue", response_model=list[QueueItemOut], summary="Fila de revisão (Supervisor/Admin)")
def review_queue(
    current: CurrentUser = Depends(require_role(["SUPERVISOR", "ADMIN"])),
    repo: SqlAlchemyDocumentRepository = Depends(_get_repo),
) -> list[QueueItemOut]:
    items = repo.list_review_queue(current.sub)
    return [
        QueueItemOut(
            id=i.id,
            numero=i.numero,
            type=i.type,
            status=i.status,
            author_name=i.author_name,
            patient_name=i.patient_name,
            updated_at=i.updated_at,
        )
        for i in items
    ]


@router.get(
    "/documents/{document_id}/review",
    response_model=DocForReviewOut,
    summary="Lê um documento para revisão (Supervisor/Admin)",
)
def get_review(
    document_id: str,
    current: CurrentUser = Depends(require_role(["SUPERVISOR", "ADMIN"])),
    repo: SqlAlchemyDocumentRepository = Depends(_get_repo),
) -> DocForReviewOut:
    doc = repo.get_for_review(current.sub, document_id)
    if not doc:
        raise NotFoundError("Documento não encontrado.")
    return DocForReviewOut(
        id=doc.id,
        numero=doc.numero,
        type=doc.type,
        status=doc.status,
        author_name=doc.author_name,
        patient_name=doc.patient_name,
        updated_at=doc.updated_at,
        content=doc.content,
        comments=[
            CommentOut(id=c.id, body=c.body, reviewer_name=c.reviewer_name, created_at=c.created_at)
            for c in doc.comments
        ],
        signatures=[
            SignatureOut(
                signer_name=s.signer_name,
                signer_role=s.signer_role,
                signer_ref=s.signer_ref,
                provider=s.provider,
                signed_at=s.signed_at,
            )
            for s in doc.signatures
        ],
    )
