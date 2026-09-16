"""Repositório de pacientes. Cifra a PII (nome, CPF do paciente e do
responsável) em repouso e descriptografa na leitura. Escopo de leitura por
vínculo (aplicado por WHERE explícito, não por RLS — a tabela `patients`
não tem SECURITY POLICY no banco, diferente de `appointments`).

Porta features/patients/infrastructure/prisma-patient-repository.ts. Sem
domain/ nesta slice no original — os tipos (NewPatient, PatientSummary,
PortalData...) vivem aqui mesmo, junto do repositório; mantido fiel.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date, datetime

from sqlalchemy import select
from sqlalchemy.orm import Session

from ....shared.crypto.field_encryption import decrypt_field, encrypt_field
from ....shared.db.models import Appointment, Assignment, AvailabilitySlot, Patient, PatientDisability, User
from ....shared.db.patient_code import next_patient_code
from ....shared.db.session import with_rls_context


@dataclass
class AccessContext:
    user_id: str
    role: str


@dataclass
class DisabilitySummary:
    type: str
    other_text: str | None


@dataclass
class PatientSummary:
    id: str
    code: str
    full_name: str
    birth_date: str | None
    is_minor: bool
    has_disability: bool
    disabilities: list[DisabilitySummary] = field(default_factory=list)


@dataclass
class GuardianInput:
    name: str
    cpf: str | None = None
    relationship: str | None = None
    phone: str | None = None


@dataclass
class NewPatient:
    full_name: str
    cpf: str | None = None
    birth_date: str | None = None  # yyyy-mm-dd
    phone: str | None = None
    guardian: GuardianInput | None = None
    has_disability: bool = False
    disability_types: list[str] = field(default_factory=list)
    disability_other_text: str | None = None


@dataclass
class PortalAppointment:
    scheduled_at: datetime
    status: str
    intern_name: str


@dataclass
class PortalData:
    code: str
    full_name: str
    appointments: list[PortalAppointment]
    pending_slots: list[datetime]


def age_in_years(birth_iso: str, ref: date | None = None) -> int:
    """Idade em anos completos a partir de uma data ISO (yyyy-mm-dd)."""
    ref = ref or datetime.now().date()
    b = date.fromisoformat(birth_iso)
    age = ref.year - b.year
    if (ref.month, ref.day) < (b.month, b.day):
        age -= 1
    return age


def _to_disability_summaries(rows: list[PatientDisability]) -> list[DisabilitySummary]:
    return [
        DisabilitySummary(type=d.type, other_text=decrypt_field(d.other_text_enc) if d.other_text_enc else None)
        for d in rows
    ]


def _to_summary(row: Patient) -> PatientSummary:
    birth_date = decrypt_field(row.birth_date_enc) if row.birth_date_enc else None
    return PatientSummary(
        id=row.id,
        code=row.code,
        full_name=decrypt_field(row.full_name_enc),
        birth_date=birth_date,
        is_minor=age_in_years(birth_date) < 18 if birth_date else False,
        has_disability=row.has_disability,
        disabilities=_to_disability_summaries(row.disabilities),
    )


class SqlAlchemyPatientRepository:
    def __init__(self, session: Session) -> None:
        self._session = session

    def list_for_actor(self, ctx: AccessContext) -> list[PatientSummary]:
        stmt = select(Patient).order_by(Patient.created_at.desc())
        if ctx.role == "SUPERVISOR":
            stmt = stmt.join(Assignment, Assignment.patient_id == Patient.id).where(
                Assignment.supervisor_id == ctx.user_id, Assignment.active
            )
        elif ctx.role != "ADMIN":
            stmt = stmt.join(Assignment, Assignment.patient_id == Patient.id).where(
                Assignment.intern_id == ctx.user_id, Assignment.active
            )
        rows = self._session.scalars(stmt).unique().all()
        return [_to_summary(r) for r in rows]

    def create(self, data: NewPatient) -> PatientSummary:
        disability_types = list(dict.fromkeys(data.disability_types)) if data.has_disability else []
        code = next_patient_code(self._session)
        row = Patient(
            code=code,
            full_name_enc=encrypt_field(data.full_name),
            cpf_enc=encrypt_field(data.cpf) if data.cpf else None,
            birth_date_enc=encrypt_field(data.birth_date) if data.birth_date else None,
            phone_enc=encrypt_field(data.phone) if data.phone else None,
            guardian_name_enc=encrypt_field(data.guardian.name) if data.guardian and data.guardian.name else None,
            guardian_cpf_enc=encrypt_field(data.guardian.cpf) if data.guardian and data.guardian.cpf else None,
            guardian_relationship=data.guardian.relationship if data.guardian else None,
            guardian_phone_enc=encrypt_field(data.guardian.phone) if data.guardian and data.guardian.phone else None,
            has_disability=data.has_disability,
        )
        row.disabilities = [
            PatientDisability(
                type=t,
                other_text_enc=encrypt_field(data.disability_other_text)
                if t == "OUTRA" and data.disability_other_text
                else None,
            )
            for t in disability_types
        ]
        self._session.add(row)
        self._session.flush()
        return _to_summary(row)

    def portal_data(self, user_id: str) -> PortalData | None:
        """Dados do portal do próprio paciente (consultas + horários
        pendentes de pareamento). Usa with_rls_context com role="ADMIN"
        fixo de propósito (mesma decisão do TS original): appointments tem
        RLS e PATIENT não tem cláusula própria na policy — o paciente vendo
        SÓ as próprias consultas (via `where user_id=...` logo abaixo, já
        estritamente escopado a ele) precisa desse bypass deliberado, não é
        uma falha de autorização.
        """

        def _do(session: Session) -> PortalData | None:
            patient = session.scalar(select(Patient).where(Patient.user_id == user_id))
            if not patient:
                return None
            appointments = session.scalars(
                select(Appointment).where(Appointment.patient_id == patient.id).order_by(Appointment.scheduled_at.asc())
            ).all()
            # ~AvailabilitySlot.matched (não .is_(False)) — mesma armadilha
            # do .is_(True) já documentada em list_by_role: SQL Server não
            # tem BOOLEAN nativo, e `IS 0`/`IS 1` são sintaxe que o T-SQL
            # rejeita nessa coluna BIT.
            slots = session.scalars(
                select(AvailabilitySlot)
                .where(AvailabilitySlot.patient_id == patient.id, ~AvailabilitySlot.matched)
                .order_by(AvailabilitySlot.slot_at.asc())
            ).all()
            interns = {
                intern.id: intern.full_name
                for intern in session.scalars(
                    select(User).where(User.id.in_({a.intern_id for a in appointments}))
                ).all()
            }
            return PortalData(
                code=patient.code,
                full_name=decrypt_field(patient.full_name_enc),
                appointments=[
                    PortalAppointment(scheduled_at=a.scheduled_at, status=a.status, intern_name=interns[a.intern_id])
                    for a in appointments
                ],
                pending_slots=[s.slot_at for s in slots],
            )

        return with_rls_context(self._session, user_id, "ADMIN", _do)
