"""Administrativo vincula um estagiário com supervisor pendente (opção
"Outro" no autocadastro) a um supervisor já cadastrado.

Porta features/auth/application/link-pending-supervisor.ts. Só aplica se
o vínculo ainda não tiver sido resolvido (evita sobrescrever silenciosamente).
"""

from __future__ import annotations

from dataclasses import dataclass

from ....shared.audit.audit_recorder import AuditEvent, AuditRecorder
from ....shared.errors.app_error import ConflictError, NotFoundError, ValidationError
from ..domain.user_repository import UserRepository


@dataclass
class LinkPendingSupervisorInput:
    actor_id: str
    intern_id: str
    supervisor_id: str
    correlation_id: str | None = None


class LinkPendingSupervisor:
    def __init__(self, users: UserRepository, audit: AuditRecorder) -> None:
        self._users = users
        self._audit = audit

    def execute(self, input: LinkPendingSupervisorInput) -> None:
        supervisor = self._users.find_by_id(input.supervisor_id)
        if not supervisor:
            raise NotFoundError("Supervisor não encontrado.", {"supervisorId": input.supervisor_id})
        if supervisor.role != "SUPERVISOR" or not supervisor.active:
            raise ValidationError(
                "O usuário selecionado não é um supervisor ativo.", {"supervisorId": input.supervisor_id}
            )

        linked = self._users.link_supervisor(input.intern_id, input.supervisor_id)
        if not linked:
            raise ConflictError(
                "Estagiário não encontrado ou já vinculado a um supervisor.", {"internId": input.intern_id}
            )

        self._audit.record(
            AuditEvent(
                actor_id=input.actor_id,
                action="UPDATE",
                resource_type="user",
                resource_id=input.intern_id,
                correlation_id=input.correlation_id,
                diff={"academicSupervisorId": input.supervisor_id, "pendingSupervisorName": None},
            )
        )
