"""Persistência do autocadastro público. Cifra a PII do paciente/responsável
e grava a disponibilidade informada. Alunos entram como INTERN com
matrícula pendente de verificação (integração com o banco da faculdade é
futura).

Porta features/enrollment/infrastructure/prisma-enrollment-repository.ts.
Sem domain/ nesta slice no original — os tipos vivem aqui mesmo, junto do
repositório; mantido fiel.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date

from sqlalchemy import select
from sqlalchemy.orm import Session

from ....shared.crypto.blind_index import cpf_blind_index
from ....shared.crypto.field_encryption import encrypt_field
from ....shared.db.models import (
    AvailabilityWindow,
    Disciplina,
    Patient,
    PatientDisability,
    TermAcceptance,
    User,
)
from ....shared.db.patient_code import next_patient_code
from ....shared.scheduling.availability_window import AvailabilityWindowInput
from ...auth.infrastructure.argon_password_hasher import ArgonPasswordHasher

_password_hasher = ArgonPasswordHasher()


@dataclass
class GuardianInput:
    name: str
    cpf: str | None = None
    relationship: str | None = None
    phone: str | None = None


@dataclass
class PatientRegistration:
    full_name: str
    email: str
    cpf: str  # login por CPF (índice cego)
    birth_date: str  # segundo fator do login
    windows: list[AvailabilityWindowInput]  # disponibilidade recorrente (não é a data da consulta)
    phone: str | None = None
    guardian: GuardianInput | None = None
    has_disability: bool = False
    disability_types: list[str] = field(default_factory=list)
    disability_other_text: str | None = None


@dataclass
class StudentRegistration:
    full_name: str
    email: str
    ra: str
    password: str
    disciplina_id: str
    windows: list[AvailabilityWindowInput]  # disponibilidade recorrente (não é a data da consulta)
    accepted_term_version: str
    phone: str | None = None
    # Exatamente um dos dois (validado na application layer): supervisor já
    # cadastrado, ou nome livre quando ainda não existe (opção "Outro").
    academic_supervisor_id: str | None = None
    pending_supervisor_name: str | None = None
    periodo: str | None = None
    turma: str | None = None


@dataclass
class SupervisorOption:
    id: str
    full_name: str


@dataclass
class DisciplinaOption:
    id: str
    name: str


@dataclass
class RegistrationOptions:
    supervisors: list[SupervisorOption]
    disciplinas: list[DisciplinaOption]


@dataclass
class InternProfileCompletion:
    disciplina_id: str
    windows: list[AvailabilityWindowInput]
    accepted_term_version: str
    academic_supervisor_id: str | None = None
    pending_supervisor_name: str | None = None
    periodo: str | None = None
    turma: str | None = None
    # Opcionais: contas auto-provisionadas via TOTVS não têm RA nem e-mail
    # real (só o placeholder <usuarioRm>@totvs.invalid) — completar cadastro
    # é a oportunidade de preencher isso, mas não é obrigatório.
    ra: str | None = None
    phone: str | None = None
    email: str | None = None


class SqlAlchemyEnrollmentRepository:
    def __init__(self, session: Session) -> None:
        self._session = session

    def email_exists(self, email: str) -> bool:
        return self._session.scalar(select(User).where(User.email == email.lower())) is not None

    def email_taken_by_other(self, email: str, owner_id: str) -> bool:
        """Igual email_exists, mas ignora o próprio dono — usado ao trocar
        o e-mail de uma conta já existente."""
        owner = self._session.scalar(select(User).where(User.email == email.lower()))
        return owner is not None and owner.id != owner_id

    def patient_cpf_exists(self, cpf: str) -> bool:
        return self._session.scalar(select(Patient).where(Patient.cpf_hash == cpf_blind_index(cpf))) is not None

    def register_patient(self, data: PatientRegistration) -> tuple[str, str]:
        disability_types = list(dict.fromkeys(data.disability_types)) if data.has_disability else []
        code = next_patient_code(self._session)
        # Conta do paciente (portal), SEM senha — login é por CPF + data de
        # nascimento. O nome fica no User p/ saudação; o registro clínico
        # mantém o nome cifrado. Criada primeiro pra ter o id disponível
        # pro FK user_id do Patient (não há relationship `account` mapeada
        # — só a coluna, então o vínculo é feito explicitamente aqui).
        account = User(role="PATIENT", full_name=data.full_name, email=data.email.lower())
        self._session.add(account)
        self._session.flush()
        patient = Patient(
            code=code,
            user_id=account.id,
            full_name_enc=encrypt_field(data.full_name),
            cpf_enc=encrypt_field(data.cpf),
            cpf_hash=cpf_blind_index(data.cpf),  # índice cego p/ login por CPF
            birth_date=date.fromisoformat(data.birth_date),
            phone=data.phone,
            guardian_name_enc=encrypt_field(data.guardian.name) if data.guardian and data.guardian.name else None,
            guardian_cpf_enc=encrypt_field(data.guardian.cpf) if data.guardian and data.guardian.cpf else None,
            guardian_relationship=data.guardian.relationship if data.guardian else None,
            guardian_phone=data.guardian.phone if data.guardian else None,
            has_disability=data.has_disability,
        )
        patient.disabilities = [
            PatientDisability(
                type=t,
                other_text_enc=encrypt_field(data.disability_other_text)
                if t == "OUTRA" and data.disability_other_text
                else None,
            )
            for t in disability_types
        ]
        self._session.add(patient)
        self._session.flush()
        self._session.add_all(
            [
                AvailabilityWindow(
                    patient_id=patient.id, weekday=w.weekday, start_time=w.start_time, end_time=w.end_time
                )
                for w in data.windows
            ]
        )
        self._session.flush()
        return patient.id, patient.code

    def register_student(self, data: StudentRegistration) -> str:
        user = User(
            role="INTERN",
            full_name=data.full_name,
            email=data.email.lower(),
            ra=data.ra,
            phone=data.phone,
            password_hash=_password_hasher.hash(data.password),
            enrollment_verified=False,
            academic_supervisor_id=data.academic_supervisor_id,
            pending_supervisor_name=(data.pending_supervisor_name or "").strip() or None,
            disciplina_id=data.disciplina_id,
            periodo=data.periodo,
            turma=data.turma,
        )
        self._session.add(user)
        self._session.flush()
        self._session.add_all(
            [
                AvailabilityWindow(intern_id=user.id, weekday=w.weekday, start_time=w.start_time, end_time=w.end_time)
                for w in data.windows
            ]
        )
        self._session.add(TermAcceptance(user_id=user.id, term_version=data.accepted_term_version))
        self._session.flush()
        return user.id

    def complete_intern_profile(self, user_id: str, data: InternProfileCompletion) -> None:
        """Completa o perfil de um estagiário já autenticado (via TOTVS) —
        grava disciplina/supervisor/turma/período, cria a disponibilidade e
        o aceite do termo. Diferente de register_student: não cria conta
        nova, não mexe em senha (estagiário não usa mais senha local pra
        login), e RA/telefone/e-mail são opcionais (só sobrescreve se
        informados)."""
        user = self._session.get(User, user_id)
        assert user is not None  # garantido pelo JWT já validado no boundary
        user.academic_supervisor_id = data.academic_supervisor_id
        user.pending_supervisor_name = (data.pending_supervisor_name or "").strip() or None
        user.disciplina_id = data.disciplina_id
        user.periodo = data.periodo
        user.turma = data.turma
        if data.ra:
            user.ra = data.ra
        if data.phone:
            user.phone = data.phone
        if data.email:
            user.email = data.email.lower()
        self._session.add_all(
            [
                AvailabilityWindow(intern_id=user_id, weekday=w.weekday, start_time=w.start_time, end_time=w.end_time)
                for w in data.windows
            ]
        )
        self._session.add(TermAcceptance(user_id=user_id, term_version=data.accepted_term_version))
        self._session.flush()

    def get_availability_windows(self, user_id: str) -> list[AvailabilityWindowInput]:
        """Disponibilidade recorrente atual do estagiário (pra pré-preencher
        a tela de edição)."""
        rows = self._session.scalars(
            select(AvailabilityWindow)
            .where(AvailabilityWindow.intern_id == user_id)
            .order_by(AvailabilityWindow.weekday.asc(), AvailabilityWindow.start_time.asc())
        ).all()
        return [AvailabilityWindowInput(weekday=r.weekday, start_time=r.start_time, end_time=r.end_time) for r in rows]

    def update_availability_windows(self, user_id: str, windows: list[AvailabilityWindowInput]) -> None:
        """Substitui a disponibilidade recorrente do estagiário pelo novo
        conjunto (diferente de complete_intern_profile, que só CRIA — aqui
        é uma edição que pode repetir a qualquer momento do semestre).
        Delete + create dentro da mesma transação da Session — nunca deixa
        o estagiário momentaneamente sem nenhuma janela gravada se a
        criação falhar no meio."""
        self._session.query(AvailabilityWindow).filter(AvailabilityWindow.intern_id == user_id).delete()
        self._session.add_all(
            [
                AvailabilityWindow(intern_id=user_id, weekday=w.weekday, start_time=w.start_time, end_time=w.end_time)
                for w in windows
            ]
        )
        self._session.flush()

    def list_options(self) -> RegistrationOptions:
        supervisors = self._session.scalars(
            select(User).where(User.role == "SUPERVISOR", User.active).order_by(User.full_name.asc())
        ).all()
        disciplinas = self._session.scalars(
            select(Disciplina).where(Disciplina.active).order_by(Disciplina.name.asc())
        ).all()
        return RegistrationOptions(
            supervisors=[SupervisorOption(id=s.id, full_name=s.full_name) for s in supervisors],
            disciplinas=[DisciplinaOption(id=d.id, name=d.name) for d in disciplinas],
        )
