"""Modelos Pydantic do slice enrollment.

Porta features/enrollment/presentation/routes.ts (os `schema` inline do
Fastify viram estas classes CamelModel).
"""

from __future__ import annotations

from typing import Literal

from pydantic import EmailStr, Field

from ....shared.http.camel_model import CamelModel

# Padrões de formato (validados também no front por máscara) — mesmos
# regex do original.
_CPF = r"^\d{3}\.\d{3}\.\d{3}-\d{2}$"
_PHONE = r"^\(\d{2}\) \d{4,5}-\d{4}$"
_RA = r"^\d{6}$"
_HHMM = r"^([01]\d|2[0-3]):([0-5]\d)$"

# Mesma lista do enum DisabilityType (schema.prisma).
DisabilityType = Literal["FISICA", "VISUAL", "AUDITIVA", "INTELECTUAL", "PSICOSSOCIAL", "MULTIPLA", "OUTRA"]


class AvailabilityWindowIn(CamelModel):
    weekday: int = Field(ge=0, le=6)
    start_time: str = Field(pattern=_HHMM)
    end_time: str = Field(pattern=_HHMM)


class AvailabilityWindowOut(CamelModel):
    weekday: int
    start_time: str
    end_time: str


class GuardianIn(CamelModel):
    name: str
    cpf: str | None = Field(default=None, pattern=_CPF)
    relationship: str | None = None
    phone: str | None = Field(default=None, pattern=_PHONE)


class RegisterPatientRequest(CamelModel):
    full_name: str = Field(min_length=2)
    email: EmailStr
    cpf: str = Field(pattern=_CPF)
    birth_date: str
    windows: list[AvailabilityWindowIn] = Field(min_length=1)
    phone: str | None = Field(default=None, pattern=_PHONE)
    guardian: GuardianIn | None = None
    has_disability: bool = False
    disability_types: list[DisabilityType] = Field(default_factory=list)
    disability_other_text: str | None = None


class RegisterPatientResponse(CamelModel):
    id: str
    code: str


class RegisterStudentRequest(CamelModel):
    full_name: str = Field(min_length=2)
    email: EmailStr
    ra: str = Field(pattern=_RA)
    password: str = Field(min_length=8, max_length=128)
    phone: str | None = Field(default=None, pattern=_PHONE)
    # Exatamente um dos dois — validado na application layer (mensagem melhor
    # do que um validador genérico conseguiria dar).
    academic_supervisor_id: str | None = None
    pending_supervisor_name: str | None = Field(default=None, min_length=1)
    disciplina_id: str
    periodo: str | None = None
    turma: str | None = None
    windows: list[AvailabilityWindowIn] = Field(min_length=1)
    # Versão do termo de responsabilidade lida em GET /register/responsibility-term
    # no momento do aceite; validada contra a versão vigente na application layer.
    accepted_term_version: str = Field(min_length=1)


class RegisterStudentResponse(CamelModel):
    id: str


class CompleteInternProfileRequest(CamelModel):
    academic_supervisor_id: str | None = None
    pending_supervisor_name: str | None = Field(default=None, min_length=1)
    disciplina_id: str
    periodo: str | None = None
    turma: str | None = None
    windows: list[AvailabilityWindowIn] = Field(min_length=1)
    accepted_term_version: str = Field(min_length=1)
    # Opcionais — conta auto-provisionada via TOTVS não tem RA nem e-mail
    # real ainda (só o placeholder <usuarioRm>@totvs.invalid).
    ra: str | None = Field(default=None, pattern=_RA)
    phone: str | None = Field(default=None, pattern=_PHONE)
    email: EmailStr | None = None


class UpdateAvailabilityWindowsRequest(CamelModel):
    windows: list[AvailabilityWindowIn] = Field(min_length=1)


class SupervisorOptionOut(CamelModel):
    id: str
    full_name: str


class DisciplinaOptionOut(CamelModel):
    id: str
    name: str


class RegistrationOptionsOut(CamelModel):
    supervisors: list[SupervisorOptionOut]
    disciplinas: list[DisciplinaOptionOut]


class ResponsibilityTermOut(CamelModel):
    version: str
    content: str
