"""Executa uma transição na máquina de estados do documento. Valida
estado+papel; exige autoria para ações do estagiário; na aprovação,
congela um hash do conteúdo (assinatura) e trava o documento (WORM).

Porta features/documents/application/transition-document.ts.
"""

from __future__ import annotations

from dataclasses import dataclass

from ....shared.audit.audit_recorder import AuditEvent, AuditRecorder
from ....shared.crypto.json_field import content_digest
from ....shared.errors.app_error import ForbiddenError, NotFoundError
from ..domain.document_status import AUTHOR_ACTIONS, ActorRole, DocAction, resolve_transition
from ..domain.signature_provider import SignaturePayload, SignatureProvider
from ..infrastructure.sqlalchemy_document_repository import (
    AddSignatureInput,
    ApprovalWrite,
    CommentWrite,
    SqlAlchemyDocumentRepository,
    TransitionWrite,
)


@dataclass
class TransitionInput:
    actor_id: str
    role: ActorRole
    document_id: str
    action: DocAction
    comment: str | None = None
    correlation_id: str | None = None


@dataclass
class TransitionOutput:
    id: str
    status: str


class TransitionDocument:
    def __init__(self, repo: SqlAlchemyDocumentRepository, audit: AuditRecorder, signatures: SignatureProvider) -> None:
        self._repo = repo
        self._audit = audit
        self._signatures = signatures

    def execute(self, input: TransitionInput) -> TransitionOutput:
        doc = self._repo.get_for_transition(input.actor_id, input.document_id)
        if not doc:
            raise NotFoundError("Documento não encontrado.")

        to = resolve_transition(doc.status, input.action, input.role)

        # A leitura acima roda como ADMIN (a escrita da transição precisa),
        # então o vínculo do supervisor é checado aqui: só decide sobre o
        # documento quem supervisiona o paciente. Admin decide sobre todos.
        if input.role == "SUPERVISOR" and not self._repo.supervises_patient(input.actor_id, doc.patient_id):
            raise ForbiddenError("Você não supervisiona este paciente.")

        if input.action in AUTHOR_ACTIONS:
            is_author = doc.author_id == input.actor_id or input.actor_id in doc.co_author_ids
            if not is_author:
                raise ForbiddenError("Apenas o autor ou coautor pode executar esta ação.")

        lock = to == "APROVADO_LOCKED"
        # A canonicalização vive em shared/crypto/json_field.py desde que o
        # conteúdo passou a ser cifrado: o MESMO dígito é gravado em
        # clinical_documents.content_hash (o que o trigger de imutabilidade
        # compara) e usado aqui na assinatura. Fossem dois cálculos
        # separados, bastaria um divergir pra "o documento mudou desde a
        # aprovação" passar a responder diferente em cada lugar.
        content_hash = content_digest(doc.content)

        write = TransitionWrite(id=input.document_id, to_status=to, lock=lock)
        if lock:
            write.approval = ApprovalWrite(supervisor_id=input.actor_id, content_hash=content_hash)
        if input.action in ("REQUEST_CHANGES", "REJECT") and (input.comment or "").strip():
            write.comment = CommentWrite(reviewer_id=input.actor_id, body=(input.comment or "").strip())

        self._repo.transition(input.actor_id, write)

        # Assinatura: o estagiário assina ao ENVIAR; o supervisor assina ao APROVAR.
        if input.action in ("SUBMIT", "APPROVE"):
            sig = self._signatures.sign(
                SignaturePayload(document_id=input.document_id, signer_id=input.actor_id, content_hash=content_hash)
            )
            self._repo.add_signature(
                input.actor_id,
                AddSignatureInput(
                    document_id=input.document_id,
                    signer_id=input.actor_id,
                    signer_role=input.role,
                    content_hash=content_hash,
                    signature_hash=sig.signature_hash,
                    provider=sig.provider,
                ),
            )

        self._audit.record(
            AuditEvent(
                actor_id=input.actor_id,
                action="TRANSITION",
                resource_type="document",
                resource_id=input.document_id,
                correlation_id=input.correlation_id,
                diff={"from": doc.status, "to": to, "action": input.action},
            )
        )

        return TransitionOutput(id=input.document_id, status=to)
