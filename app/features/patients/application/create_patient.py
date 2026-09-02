"""Cadastro de paciente (Administrativo). Regra: se o paciente for menor
de idade (calculado pela data de nascimento), os dados do responsável
legal são obrigatórios.

Porta features/patients/application/create-patient.ts.
"""

from __future__ import annotations

from dataclasses import dataclass

from ....shared.audit.audit_recorder import AuditEvent, AuditRecorder
from ....shared.errors.app_error import ValidationError
from ..infrastructure.sqlalchemy_patient_repository import (
    NewPatient,
    PatientSummary,
    SqlAlchemyPatientRepository,
    age_in_years,
)

# Mesma lista do enum DisabilityType (schema.prisma).
_DISABILITY_TYPES = ["FISICA", "VISUAL", "AUDITIVA", "INTELECTUAL", "PSICOSSOCIAL", "MULTIPLA", "OUTRA"]


@dataclass
class CreatePatientInput(NewPatient):
    actor_id: str = ""
    correlation_id: str | None = None


def _validate_disability(input: NewPatient) -> None:
    """Só obrigatório quando has_disability=True, tipo precisa vir da
    lista pré-definida, e "outra" exige texto livre descrevendo."""
    if not input.has_disability:
        return
    if not input.disability_types:
        raise ValidationError("Selecione ao menos um tipo de deficiência.")
    for t in input.disability_types:
        if t not in _DISABILITY_TYPES:
            raise ValidationError(f"Tipo de deficiência inválido: {t}.")
    if "OUTRA" in input.disability_types and not (input.disability_other_text or "").strip():
        raise ValidationError('Descreva o tipo de deficiência em "outra".')


class CreatePatient:
    def __init__(self, repo: SqlAlchemyPatientRepository, audit: AuditRecorder) -> None:
        self._repo = repo
        self._audit = audit

    def execute(self, input: CreatePatientInput) -> PatientSummary:
        if not input.full_name.strip():
            raise ValidationError("Nome do paciente é obrigatório.")
        is_minor = age_in_years(input.birth_date) < 18 if input.birth_date else False
        if is_minor and not (input.guardian and input.guardian.name.strip()):
            raise ValidationError("Paciente menor de idade exige os dados do responsável legal.")
        _validate_disability(input)

        patient = self._repo.create(input)

        self._audit.record(
            AuditEvent(
                actor_id=input.actor_id,
                action="CREATE",
                resource_type="patient",
                resource_id=patient.id,
                correlation_id=input.correlation_id,
            )
        )

        return patient
