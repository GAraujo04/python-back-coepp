"""Completa o cadastro do estagiário já autenticado via TOTVS (1º acesso
ou qualquer acesso enquanto o perfil estiver incompleto — ver
InternLogin/is_intern_profile_complete). Mesma validação de negócio do
autocadastro público antigo (RegisterStudentPublic), menos identidade
(nome/e-mail/senha vêm do TOTVS ou já existem na conta).

Porta features/enrollment/application/complete-intern-profile.ts.
"""

from __future__ import annotations

import re
from collections.abc import Callable
from dataclasses import dataclass

from ....shared.audit.audit_recorder import AuditEvent, AuditRecorder
from ....shared.errors.app_error import ConflictError, ValidationError
from ....shared.scheduling.availability_window import AvailabilityWindowInput, validate_availability_windows
from ..infrastructure.responsibility_term import ResponsibilityTerm
from ..infrastructure.sqlalchemy_enrollment_repository import InternProfileCompletion, SqlAlchemyEnrollmentRepository

_EMAIL_RE = re.compile(r"^[^\s@]+@[^\s@]+\.[^\s@]+$")


@dataclass
class CompleteInternProfileInput:
    user_id: str
    disciplina_id: str
    windows: list[AvailabilityWindowInput]
    accepted_term_version: str
    academic_supervisor_id: str | None = None
    pending_supervisor_name: str | None = None
    periodo: str | None = None
    turma: str | None = None
    ra: str | None = None
    phone: str | None = None
    email: str | None = None
    correlation_id: str | None = None


class CompleteInternProfile:
    def __init__(
        self,
        repo: SqlAlchemyEnrollmentRepository,
        audit: AuditRecorder,
        read_term: Callable[[], ResponsibilityTerm],
    ) -> None:
        self._repo = repo
        self._audit = audit
        self._read_term = read_term

    def execute(self, input: CompleteInternProfileInput) -> None:
        has_known_supervisor = bool(input.academic_supervisor_id)
        has_pending_supervisor = bool((input.pending_supervisor_name or "").strip())
        if has_known_supervisor == has_pending_supervisor:
            # Ambos ausentes OU ambos presentes — exige exatamente um dos dois.
            raise ValidationError(
                'Informe o supervisor cadastrado OU o nome em "Outro", não os dois.'
                if has_known_supervisor
                else 'Selecione o supervisor ou informe o nome em "Outro".'
            )
        if not input.disciplina_id:
            raise ValidationError("Selecione a disciplina.")
        validate_availability_windows(input.windows, "estagiário")
        if not (input.accepted_term_version or "").strip():
            raise ValidationError("É necessário ler e aceitar o termo de responsabilidade.")
        current_term = self._read_term()
        if input.accepted_term_version != current_term.version:
            raise ConflictError(
                "O termo de responsabilidade foi atualizado — releia e aceite a versão atual.",
                {"acceptedVersion": input.accepted_term_version, "currentVersion": current_term.version},
            )
        if input.email:
            if not _EMAIL_RE.match(input.email):
                raise ValidationError("E-mail inválido.")
            if self._repo.email_taken_by_other(input.email, input.user_id):
                raise ConflictError("Já existe um usuário com este e-mail.")

        self._repo.complete_intern_profile(
            input.user_id,
            InternProfileCompletion(
                academic_supervisor_id=input.academic_supervisor_id,
                pending_supervisor_name=input.pending_supervisor_name,
                disciplina_id=input.disciplina_id,
                periodo=input.periodo,
                turma=input.turma,
                windows=input.windows,
                accepted_term_version=input.accepted_term_version,
                ra=input.ra,
                phone=input.phone,
                email=input.email,
            ),
        )

        self._audit.record(
            AuditEvent(
                actor_id=input.user_id,
                action="UPDATE",
                resource_type="user",
                resource_id=input.user_id,
                correlation_id=input.correlation_id,
                diff={"event": "complete_intern_profile"},
            )
        )
