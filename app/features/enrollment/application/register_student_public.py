"""Autocadastro público do aluno/estagiário: dados + disponibilidade. A
matrícula é marcada como não verificada (a checagem no banco da faculdade
é integração futura). Exige o aceite do termo de responsabilidade vigente
(item 4.2).

Porta features/enrollment/application/register-student-public.ts.
"""

from __future__ import annotations

import re
from collections.abc import Callable
from dataclasses import dataclass

from ....shared.audit.audit_recorder import AuditEvent, AuditRecorder
from ....shared.errors.app_error import ConflictError, ValidationError
from ....shared.scheduling.availability_window import AvailabilityWindowInput, validate_availability_windows
from ..infrastructure.responsibility_term import ResponsibilityTerm
from ..infrastructure.sqlalchemy_enrollment_repository import SqlAlchemyEnrollmentRepository, StudentRegistration

_EMAIL_RE = re.compile(r"^[^\s@]+@[^\s@]+\.[^\s@]+$")


@dataclass
class RegisterStudentPublicInput:
    full_name: str
    email: str
    ra: str
    password: str
    disciplina_id: str
    windows: list[AvailabilityWindowInput]
    accepted_term_version: str
    phone: str | None = None
    academic_supervisor_id: str | None = None
    pending_supervisor_name: str | None = None
    periodo: str | None = None
    turma: str | None = None
    correlation_id: str | None = None


class RegisterStudentPublic:
    def __init__(
        self,
        repo: SqlAlchemyEnrollmentRepository,
        audit: AuditRecorder,
        read_term: Callable[[], ResponsibilityTerm],
    ) -> None:
        self._repo = repo
        self._audit = audit
        self._read_term = read_term

    def execute(self, input: RegisterStudentPublicInput) -> str:
        if not input.full_name.strip():
            raise ValidationError("Nome é obrigatório.")
        if not _EMAIL_RE.match(input.email or ""):
            raise ValidationError("E-mail inválido.")
        if not input.ra.strip():
            raise ValidationError("RA (Registro Acadêmico) é obrigatório.")
        if len(input.password or "") < 8:
            raise ValidationError("A senha deve ter ao menos 8 caracteres.")
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

        if self._repo.email_exists(input.email):
            raise ConflictError("Já existe um usuário com este e-mail.")

        user_id = self._repo.register_student(
            StudentRegistration(
                full_name=input.full_name,
                email=input.email,
                ra=input.ra,
                password=input.password,
                disciplina_id=input.disciplina_id,
                windows=input.windows,
                accepted_term_version=input.accepted_term_version,
                phone=input.phone,
                academic_supervisor_id=input.academic_supervisor_id,
                pending_supervisor_name=input.pending_supervisor_name,
                periodo=input.periodo,
                turma=input.turma,
            )
        )
        self._audit.record(
            AuditEvent(
                actor_id=None,
                action="CREATE",
                resource_type="user",
                resource_id=user_id,
                correlation_id=input.correlation_id,
                diff={"source": "autocadastro", "role": "INTERN", "enrollmentVerified": False},
            )
        )
        return user_id
