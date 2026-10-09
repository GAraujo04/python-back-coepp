"""Modelos Pydantic do slice patients.

Porta features/patients/presentation/routes.ts (schemas inline no
Fastify original).
"""

from __future__ import annotations

from typing import Literal

from pydantic import Field

from ....shared.http.camel_model import CamelModel
from ....shared.http.utc_datetime import UtcDatetime

_CPF_RE = r"^\d{3}\.\d{3}\.\d{3}-\d{2}$"
_PHONE_RE = r"^\(\d{2}\) \d{4,5}-\d{4}$"
DisabilityType = Literal["FISICA", "VISUAL", "AUDITIVA", "INTELECTUAL", "PSICOSSOCIAL", "MULTIPLA", "OUTRA"]


class DisabilitySummaryOut(CamelModel):
    type: str
    other_text: str | None


class PatientSummaryOut(CamelModel):
    id: str
    code: str
    full_name: str | None  # None para o supervisor (shared/privacy/patient_name.py)
    birth_date: str | None
    is_minor: bool
    has_disability: bool
    disabilities: list[DisabilitySummaryOut]


class GuardianRequest(CamelModel):
    name: str
    cpf: str | None = Field(default=None, pattern=_CPF_RE)
    relationship: str | None = None
    phone: str | None = Field(default=None, pattern=_PHONE_RE)


class CreatePatientRequest(CamelModel):
    full_name: str = Field(min_length=2)
    cpf: str | None = Field(default=None, pattern=_CPF_RE)
    birth_date: str | None = None
    phone: str | None = Field(default=None, pattern=_PHONE_RE)
    guardian: GuardianRequest | None = None
    has_disability: bool = False
    disability_types: list[DisabilityType] = Field(default_factory=list)
    disability_other_text: str | None = None


class PortalAppointmentOut(CamelModel):
    scheduled_at: UtcDatetime
    status: str
    intern_name: str


class PortalDataOut(CamelModel):
    code: str
    full_name: str
    appointments: list[PortalAppointmentOut]
    pending_slots: list[UtcDatetime]
