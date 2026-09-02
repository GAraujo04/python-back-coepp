"""Modelos SQLAlchemy (mapeamento ORM ↔ tabelas).

Porta prisma/schema.prisma. Fica num arquivo central em shared/db/, não
espalhado por slice — mesma decisão estrutural do `schema.prisma` original,
que também é um arquivo único descrevendo TODAS as tabelas (o próprio
Prisma não organiza schema por slice; só os *repositórios* que usam cada
model são organizados por slice, em `infrastructure/`).

Cresce incrementalmente: só os campos que as slices já migradas precisam
são mapeados aqui — os demais (ex.: PII cifrada do Patient, colunas de
outras tabelas) entram quando a slice correspondente for migrada. Isso é
seguro porque o SQLAlchemy não exige mapear 100% das colunas de uma
tabela para fazer SELECT nela.
"""

from __future__ import annotations

import uuid
from datetime import UTC, date, datetime

from sqlalchemy import Column, Date, DateTime, ForeignKey, Integer, LargeBinary, String, Table, Text, func
from sqlalchemy.dialects.mssql import UNIQUEIDENTIFIER
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship


class Base(DeclarativeBase):
    pass


def _new_uuid() -> str:
    """Gera o id no lado da aplicação (igual ao `@default(uuid())` do
    Prisma) — não delega ao banco (`NEWID()`), pra manter o mesmo formato
    (uuid4 minúsculo) que o Node já grava."""
    return str(uuid.uuid4())


def _now() -> datetime:
    """Equivalente ao `@updatedAt` do Prisma: calculado na APLICAÇÃO a cada
    escrita, não por um DEFAULT/trigger do banco — confirmado lendo a
    migration (`updated_at DATETIME2 NOT NULL`, sem `DEFAULT`, diferente de
    `created_at`, que tem `DEFAULT CURRENT_TIMESTAMP`). Usar server_default
    aqui causaria o INSERT falhar (coluna NOT NULL sem valor nem default)."""
    return datetime.now(UTC).replace(tzinfo=None)


class User(Base):
    __tablename__ = "users"

    id: Mapped[str] = mapped_column(UNIQUEIDENTIFIER(as_uuid=False), primary_key=True, default=_new_uuid)
    role: Mapped[str] = mapped_column(String)
    full_name: Mapped[str] = mapped_column(String, name="full_name")
    email: Mapped[str] = mapped_column(String, unique=True)
    crp: Mapped[str | None] = mapped_column(String, default=None)
    ra: Mapped[str | None] = mapped_column(String, default=None)
    totvs_usuario: Mapped[str | None] = mapped_column(String, name="totvs_usuario", unique=True, default=None)
    phone: Mapped[str | None] = mapped_column(String, default=None)
    department: Mapped[str | None] = mapped_column(String, default=None)
    password_hash: Mapped[str | None] = mapped_column(String, name="password_hash", default=None)
    active: Mapped[bool] = mapped_column(default=True)
    enrollment_verified: Mapped[bool] = mapped_column(name="enrollment_verified", default=False)
    academic_supervisor_id: Mapped[str | None] = mapped_column(
        UNIQUEIDENTIFIER(as_uuid=False), ForeignKey("users.id"), name="academic_supervisor_id", default=None
    )
    pending_supervisor_name: Mapped[str | None] = mapped_column(String, name="pending_supervisor_name", default=None)
    disciplina_id: Mapped[str | None] = mapped_column(
        UNIQUEIDENTIFIER(as_uuid=False), name="disciplina_id", default=None
    )
    periodo: Mapped[str | None] = mapped_column(String, default=None)
    turma: Mapped[str | None] = mapped_column(String, default=None)
    created_at: Mapped[datetime] = mapped_column(DateTime, name="created_at", server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(DateTime, name="updated_at", default=_now, onupdate=_now)


class RefreshSession(Base):
    __tablename__ = "refresh_sessions"

    id: Mapped[str] = mapped_column(UNIQUEIDENTIFIER(as_uuid=False), primary_key=True, default=_new_uuid)
    user_id: Mapped[str] = mapped_column(UNIQUEIDENTIFIER(as_uuid=False), ForeignKey("users.id"), name="user_id")
    token_hash: Mapped[str] = mapped_column(String, name="token_hash", unique=True)
    user_agent: Mapped[str | None] = mapped_column(String, name="user_agent", default=None)
    ip: Mapped[str | None] = mapped_column(String, default=None)
    expires_at: Mapped[datetime] = mapped_column(DateTime, name="expires_at")
    revoked_at: Mapped[datetime | None] = mapped_column(DateTime, name="revoked_at", default=None)
    created_at: Mapped[datetime] = mapped_column(DateTime, name="created_at", server_default=func.now())


class Patient(Base):
    __tablename__ = "patients"

    id: Mapped[str] = mapped_column(UNIQUEIDENTIFIER(as_uuid=False), primary_key=True, default=_new_uuid)
    code: Mapped[str] = mapped_column(String, unique=True)
    user_id: Mapped[str | None] = mapped_column(
        UNIQUEIDENTIFIER(as_uuid=False), ForeignKey("users.id"), name="user_id", unique=True, default=None
    )
    full_name_enc: Mapped[bytes] = mapped_column(LargeBinary, name="full_name_enc")
    cpf_enc: Mapped[bytes | None] = mapped_column(LargeBinary, name="cpf_enc", default=None)
    cpf_hash: Mapped[str | None] = mapped_column(String, name="cpf_hash", unique=True, default=None)
    birth_date: Mapped[date | None] = mapped_column(Date, name="birth_date", default=None)
    phone: Mapped[str | None] = mapped_column(String, default=None)
    guardian_name_enc: Mapped[bytes | None] = mapped_column(LargeBinary, name="guardian_name_enc", default=None)
    guardian_cpf_enc: Mapped[bytes | None] = mapped_column(LargeBinary, name="guardian_cpf_enc", default=None)
    guardian_relationship: Mapped[str | None] = mapped_column(String, name="guardian_relationship", default=None)
    guardian_phone: Mapped[str | None] = mapped_column(String, name="guardian_phone", default=None)
    has_disability: Mapped[bool] = mapped_column(name="has_disability", default=False)
    created_at: Mapped[datetime] = mapped_column(DateTime, name="created_at", server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(DateTime, name="updated_at", default=_now, onupdate=_now)

    disabilities: Mapped[list[PatientDisability]] = relationship("PatientDisability", lazy="selectin")


class Disciplina(Base):
    __tablename__ = "disciplinas"

    id: Mapped[str] = mapped_column(UNIQUEIDENTIFIER(as_uuid=False), primary_key=True, default=_new_uuid)
    name: Mapped[str] = mapped_column(String, unique=True)
    active: Mapped[bool] = mapped_column(default=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, name="created_at", server_default=func.now())


class Room(Base):
    __tablename__ = "rooms"

    id: Mapped[str] = mapped_column(UNIQUEIDENTIFIER(as_uuid=False), primary_key=True, default=_new_uuid)
    name: Mapped[str] = mapped_column(String, unique=True)
    active: Mapped[bool] = mapped_column(default=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, name="created_at", server_default=func.now())


class Appointment(Base):
    __tablename__ = "appointments"

    id: Mapped[str] = mapped_column(UNIQUEIDENTIFIER(as_uuid=False), primary_key=True, default=_new_uuid)
    patient_id: Mapped[str] = mapped_column(
        UNIQUEIDENTIFIER(as_uuid=False), ForeignKey("patients.id"), name="patient_id"
    )
    intern_id: Mapped[str] = mapped_column(UNIQUEIDENTIFIER(as_uuid=False), ForeignKey("users.id"), name="intern_id")
    room_id: Mapped[str | None] = mapped_column(
        UNIQUEIDENTIFIER(as_uuid=False), ForeignKey("rooms.id"), name="room_id", default=None
    )
    scheduled_at: Mapped[datetime] = mapped_column(DateTime, name="scheduled_at")
    status: Mapped[str] = mapped_column(String, default="SCHEDULED")
    notes: Mapped[str | None] = mapped_column(String, default=None)
    created_at: Mapped[datetime] = mapped_column(DateTime, name="created_at", server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(DateTime, name="updated_at", default=_now, onupdate=_now)

    room: Mapped[Room | None] = relationship(Room, lazy="joined")


class PatientDisability(Base):
    __tablename__ = "patient_disabilities"

    id: Mapped[str] = mapped_column(UNIQUEIDENTIFIER(as_uuid=False), primary_key=True, default=_new_uuid)
    patient_id: Mapped[str] = mapped_column(
        UNIQUEIDENTIFIER(as_uuid=False), ForeignKey("patients.id"), name="patient_id"
    )
    type: Mapped[str] = mapped_column(String)
    other_text_enc: Mapped[bytes | None] = mapped_column(LargeBinary, name="other_text_enc", default=None)
    created_at: Mapped[datetime] = mapped_column(DateTime, name="created_at", server_default=func.now())


class AvailabilitySlot(Base):
    __tablename__ = "availability_slots"

    id: Mapped[str] = mapped_column(UNIQUEIDENTIFIER(as_uuid=False), primary_key=True, default=_new_uuid)
    patient_id: Mapped[str | None] = mapped_column(
        UNIQUEIDENTIFIER(as_uuid=False), ForeignKey("patients.id"), name="patient_id", default=None
    )
    intern_id: Mapped[str | None] = mapped_column(
        UNIQUEIDENTIFIER(as_uuid=False), ForeignKey("users.id"), name="intern_id", default=None
    )
    slot_at: Mapped[datetime] = mapped_column(DateTime, name="slot_at")
    matched: Mapped[bool] = mapped_column(default=False)
    created_at: Mapped[datetime] = mapped_column(DateTime, name="created_at", server_default=func.now())


class AvailabilityWindow(Base):
    """Disponibilidade recorrente por dia da semana (não é a data da
    consulta — é o insumo do algoritmo de match). Distinta de
    AvailabilitySlot (um horário concreto, já casado ou não)."""

    __tablename__ = "availability_windows"

    id: Mapped[str] = mapped_column(UNIQUEIDENTIFIER(as_uuid=False), primary_key=True, default=_new_uuid)
    patient_id: Mapped[str | None] = mapped_column(
        UNIQUEIDENTIFIER(as_uuid=False), ForeignKey("patients.id"), name="patient_id", default=None
    )
    intern_id: Mapped[str | None] = mapped_column(
        UNIQUEIDENTIFIER(as_uuid=False), ForeignKey("users.id"), name="intern_id", default=None
    )
    weekday: Mapped[int] = mapped_column(Integer)
    start_time: Mapped[str] = mapped_column(String, name="start_time")
    end_time: Mapped[str] = mapped_column(String, name="end_time")
    created_at: Mapped[datetime] = mapped_column(DateTime, name="created_at", server_default=func.now())


class TermAcceptance(Base):
    __tablename__ = "term_acceptances"

    id: Mapped[str] = mapped_column(UNIQUEIDENTIFIER(as_uuid=False), primary_key=True, default=_new_uuid)
    user_id: Mapped[str] = mapped_column(UNIQUEIDENTIFIER(as_uuid=False), ForeignKey("users.id"), name="user_id")
    term_version: Mapped[str] = mapped_column(String, name="term_version")
    accepted_at: Mapped[datetime] = mapped_column(DateTime, name="accepted_at", server_default=func.now())


class Assignment(Base):
    __tablename__ = "assignments"

    id: Mapped[str] = mapped_column(UNIQUEIDENTIFIER(as_uuid=False), primary_key=True, default=_new_uuid)
    patient_id: Mapped[str] = mapped_column(
        UNIQUEIDENTIFIER(as_uuid=False), ForeignKey("patients.id"), name="patient_id"
    )
    intern_id: Mapped[str] = mapped_column(UNIQUEIDENTIFIER(as_uuid=False), ForeignKey("users.id"), name="intern_id")
    supervisor_id: Mapped[str | None] = mapped_column(
        UNIQUEIDENTIFIER(as_uuid=False), ForeignKey("users.id"), name="supervisor_id", default=None
    )
    active: Mapped[bool] = mapped_column(default=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, name="created_at", server_default=func.now())


# Tabela de junção do relacionamento implícito m:n coAuthors do Prisma
# (`User[] @relation("DocumentCoAuthors")` em ClinicalDocument) — Prisma
# cria essa tabela sozinho, com esse nome e colunas A/B exatos (A =
# ClinicalDocument.id, B = User.id, ordem alfabética dos nomes dos
# models). A RLS de clinical_documents (fn_documents_select) lê ela
# diretamente por esse nome — não pode divergir.
document_co_authors = Table(
    "_DocumentCoAuthors",
    Base.metadata,
    Column("A", UNIQUEIDENTIFIER(as_uuid=False), ForeignKey("clinical_documents.id"), primary_key=True),
    Column("B", UNIQUEIDENTIFIER(as_uuid=False), ForeignKey("users.id"), primary_key=True),
)


class ClinicalDocument(Base):
    __tablename__ = "clinical_documents"

    id: Mapped[str] = mapped_column(UNIQUEIDENTIFIER(as_uuid=False), primary_key=True, default=_new_uuid)
    numero: Mapped[str | None] = mapped_column(String, unique=True, default=None)
    patient_id: Mapped[str] = mapped_column(
        UNIQUEIDENTIFIER(as_uuid=False), ForeignKey("patients.id"), name="patient_id"
    )
    appointment_id: Mapped[str | None] = mapped_column(
        UNIQUEIDENTIFIER(as_uuid=False), ForeignKey("appointments.id"), name="appointment_id", default=None
    )
    author_id: Mapped[str] = mapped_column(UNIQUEIDENTIFIER(as_uuid=False), ForeignKey("users.id"), name="author_id")
    type: Mapped[str] = mapped_column(String)
    status: Mapped[str] = mapped_column(String, default="RASCUNHO")
    version: Mapped[int] = mapped_column(Integer, default=1)
    content: Mapped[str] = mapped_column(Text, default="{}")
    supersedes_id: Mapped[str | None] = mapped_column(
        UNIQUEIDENTIFIER(as_uuid=False), name="supersedes_id", default=None
    )
    locked_at: Mapped[datetime | None] = mapped_column(DateTime, name="locked_at", default=None)
    created_at: Mapped[datetime] = mapped_column(DateTime, name="created_at", server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(DateTime, name="updated_at", default=_now, onupdate=_now)

    co_authors: Mapped[list[User]] = relationship("User", secondary=document_co_authors, lazy="selectin")
    signatures: Mapped[list[DocumentSignature]] = relationship(
        "DocumentSignature", order_by="DocumentSignature.signed_at", lazy="selectin"
    )


class DocumentSignature(Base):
    __tablename__ = "document_signatures"

    id: Mapped[str] = mapped_column(UNIQUEIDENTIFIER(as_uuid=False), primary_key=True, default=_new_uuid)
    document_id: Mapped[str] = mapped_column(
        UNIQUEIDENTIFIER(as_uuid=False), ForeignKey("clinical_documents.id"), name="document_id"
    )
    signer_id: Mapped[str] = mapped_column(UNIQUEIDENTIFIER(as_uuid=False), ForeignKey("users.id"), name="signer_id")
    signer_role: Mapped[str] = mapped_column(String, name="signer_role")
    signer_name: Mapped[str] = mapped_column(String, name="signer_name")
    signer_ref: Mapped[str | None] = mapped_column(String, name="signer_ref", default=None)
    content_hash: Mapped[str] = mapped_column(String, name="content_hash")
    signature_hash: Mapped[str] = mapped_column(String, name="signature_hash")
    provider: Mapped[str] = mapped_column(String, default="internal")
    signed_at: Mapped[datetime] = mapped_column(DateTime, name="signed_at", server_default=func.now())
