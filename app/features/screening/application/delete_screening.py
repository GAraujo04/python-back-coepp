"""Remove um documento clínico (triagem). Só o autor/coautor pode remover,
e somente enquanto está em RASCUNHO — depois de enviado para supervisão, a
remoção fica bloqueada (mesmo para o autor). ADMIN remove em qualquer
status. A RLS (BLOCK PREDICATE em clinical_documents) é o backstop final;
esta checagem existe para dar uma mensagem de erro clara em vez do erro
bruto do banco.

Porta features/screening/application/delete-screening.ts.
"""

from __future__ import annotations

from ....shared.audit.audit_recorder import AuditEvent, AuditRecorder
from ....shared.errors.app_error import ConflictError, ForbiddenError, NotFoundError
from ..domain.screening_repository import AccessContext, ScreeningRepository


class DeleteScreening:
    def __init__(self, repo: ScreeningRepository, audit: AuditRecorder) -> None:
        self._repo = repo
        self._audit = audit

    def execute(self, actor: AccessContext, id: str, correlation_id: str | None = None) -> None:
        screening = self._repo.find_by_id(actor, id)
        if not screening:
            raise NotFoundError("Triagem não encontrada.")

        is_admin = actor.role == "ADMIN"
        is_owner = screening.author_id == actor.user_id or actor.user_id in screening.co_author_ids
        if not is_admin and not is_owner:
            raise ForbiddenError("Você não tem permissão para remover este documento.")
        if not is_admin and screening.status != "RASCUNHO":
            raise ConflictError(
                "Só é possível remover documentos em rascunho — este já foi enviado para supervisão.",
                {"documentId": id, "status": screening.status},
            )

        self._repo.delete(actor, id)

        self._audit.record(
            AuditEvent(
                actor_id=actor.user_id,
                action="DELETE",
                resource_type="screening",
                resource_id=id,
                correlation_id=correlation_id,
                diff={"status": screening.status, "type": screening.type},
            )
        )
