"""Autocadastro público do paciente (sem login): dados + disponibilidade.
Menor de idade exige responsável legal. Pelo menos um horário disponível.

Porta features/enrollment/application/register-patient-public.ts.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from datetime import date, datetime

from ....shared.audit.audit_recorder import AuditEvent, AuditRecorder
from ....shared.errors.app_error import ConflictError, ValidationError
from ....shared.scheduling.availability_window import AvailabilityWindowInput, validate_availability_windows
from ..infrastructure.sqlalchemy_enrollment_repository import (
    GuardianInput,
    PatientRegistration,
    SqlAlchemyEnrollmentRepository,
)

_EMAIL_RE = re.compile(r"^[^\s@]+@[^\s@]+\.[^\s@]+$")
# Lista pré-definida de tipos de deficiência (mesma do enum DisabilityType do schema.prisma).
_DISABILITY_TYPES = ["FISICA", "VISUAL", "AUDITIVA", "INTELECTUAL", "PSICOSSOCIAL", "MULTIPLA", "OUTRA"]


def _age_in_years(birth_iso: str) -> int:
    """Duplicado deliberadamente (não importado de patients/) — slices não
    compartilham internals; ver patients/infrastructure para o equivalente
    daquela slice."""
    b = date.fromisoformat(birth_iso)
    now = datetime.now().date()
    age = now.year - b.year
    if (now.month, now.day) < (b.month, b.day):
        age -= 1
    return age


@dataclass
class RegisterPatientPublicInput:
    full_name: str
    email: str
    cpf: str
    birth_date: str
    windows: list[AvailabilityWindowInput]
    phone: str | None = None
    guardian: GuardianInput | None = None
    has_disability: bool = False
    disability_types: list[str] = field(default_factory=list)
    disability_other_text: str | None = None
    correlation_id: str | None = None


class RegisterPatientPublic:
    def __init__(self, repo: SqlAlchemyEnrollmentRepository, audit: AuditRecorder) -> None:
        self._repo = repo
        self._audit = audit

    def execute(self, input: RegisterPatientPublicInput) -> tuple[str, str]:
        if not input.full_name.strip():
            raise ValidationError("Nome é obrigatório.")
        if not _EMAIL_RE.match(input.email or ""):
            raise ValidationError("E-mail inválido.")
        if not input.cpf or len([c for c in input.cpf if c.isdigit()]) != 11:
            raise ValidationError("CPF inválido.")
        if not input.birth_date:
            raise ValidationError("Data de nascimento é obrigatória.")
        validate_availability_windows(input.windows, "paciente")

        is_minor = _age_in_years(input.birth_date) < 18
        if is_minor and not (input.guardian and input.guardian.name.strip()):
            raise ValidationError("Paciente menor de idade exige os dados do responsável legal.")
        if input.has_disability:
            if not input.disability_types:
                raise ValidationError("Selecione ao menos um tipo de deficiência.")
            for t in input.disability_types:
                if t not in _DISABILITY_TYPES:
                    raise ValidationError(f"Tipo de deficiência inválido: {t}.")
            if "OUTRA" in input.disability_types and not (input.disability_other_text or "").strip():
                raise ValidationError('Descreva o tipo de deficiência em "outra".')

        if self._repo.email_exists(input.email):
            raise ConflictError("Já existe um cadastro com este e-mail.")
        if self._repo.patient_cpf_exists(input.cpf):
            raise ConflictError("Já existe um cadastro com este CPF.")

        patient_id, code = self._repo.register_patient(
            PatientRegistration(
                full_name=input.full_name,
                email=input.email,
                cpf=input.cpf,
                birth_date=input.birth_date,
                windows=input.windows,
                phone=input.phone,
                guardian=input.guardian,
                has_disability=input.has_disability,
                disability_types=input.disability_types,
                disability_other_text=input.disability_other_text,
            )
        )
        self._audit.record(
            AuditEvent(
                actor_id=None,
                action="CREATE",
                resource_type="patient",
                resource_id=patient_id,
                correlation_id=input.correlation_id,
                diff={"source": "autocadastro"},
            )
        )
        return patient_id, code
