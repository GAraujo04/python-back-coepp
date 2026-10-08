"""Testes de integração contra o SQL Server de verdade.

Existem para pegar o que os fakes em memória não pegam: SQL que o SQL
Server recusa (ex.: `SELECT EXISTS(...)`, que passou nos testes unitários
e quebrou no banco), e as regras de RLS — a última linha de defesa de
acesso, que só existe no banco.

Cada teste roda numa transação que é DESFEITA no fim: cria os próprios
dados (usuários, paciente, vínculo, documento) e não deixa rastro. Sem
banco acessível (máquina sem SQL Server), os testes são pulados — o CI
sobe um SQL Server e roda todos.
"""

from __future__ import annotations

import os
import uuid
from collections.abc import Iterator
from dataclasses import dataclass

import pytest
from sqlalchemy import text
from sqlalchemy.orm import Session

from app.shared.crypto.field_encryption import encrypt_field
from app.shared.crypto.json_field import content_digest, encrypt_json
from app.shared.db.models import Assignment, ClinicalDocument, Patient, User
from app.shared.db.session import SessionLocal, with_rls_context


def _db_available() -> bool:
    try:
        with SessionLocal() as s:
            s.execute(text("SELECT 1"))
        return True
    except Exception:
        return False


_DB = _db_available()

# No CI (REQUIRE_DB=1) banco fora do ar é falha, não "pulado": senão a CI
# ficaria verde sem ter rodado nenhum teste de integração.
if not _DB and os.environ.get("REQUIRE_DB") == "1":
    raise RuntimeError("REQUIRE_DB=1, mas o SQL Server não está acessível — testes de integração não rodariam.")


@pytest.fixture
def db() -> Iterator[Session]:
    # Skip aqui, e não via `pytestmark`: pytestmark num conftest não se
    # aplica aos módulos de teste. Todo teste daqui depende desta fixture.
    if not _DB:
        pytest.skip("SQL Server indisponível")
    session = SessionLocal()
    try:
        yield session
    finally:
        session.rollback()
        session.close()


def _uid() -> str:
    return uuid.uuid4().hex[:10]


def make_user(db: Session, role: str, **kw: object) -> User:
    u = User(role=role, full_name=f"{role} {_uid()}", email=f"{_uid()}@teste.invalid", **kw)
    db.add(u)
    db.flush()
    return u


def make_patient(db: Session) -> Patient:
    p = Patient(code=f"T{_uid()}", full_name_enc=encrypt_field("Paciente Teste"))
    db.add(p)
    db.flush()
    return p


@dataclass
class World:
    admin: User
    sup_a: User  # supervisiona o paciente
    sup_b: User  # não supervisiona
    intern: User
    other_intern: User
    patient: Patient
    doc: ClinicalDocument


@pytest.fixture
def world(db: Session) -> World:
    admin = make_user(db, "ADMIN")
    sup_a = make_user(db, "SUPERVISOR")
    sup_b = make_user(db, "SUPERVISOR")
    intern = make_user(db, "INTERN", academic_supervisor_id=sup_a.id)
    other_intern = make_user(db, "INTERN")
    patient = make_patient(db)
    db.add(Assignment(patient_id=patient.id, intern_id=intern.id, supervisor_id=sup_a.id))

    def _insert(session: Session) -> ClinicalDocument:
        content = {"identificacao": {"nome": "Paciente Teste"}}
        doc = ClinicalDocument(
            numero=f"T-{_uid()}",
            type="SCREENING_ADULT",
            status="ENVIADO_PARA_SUPERVISAO",
            patient_id=patient.id,
            author_id=intern.id,
            content_enc=encrypt_json(content),
            content_hash=content_digest(content),
        )
        session.add(doc)
        session.flush()
        return doc

    # clinical_documents tem BLOCK PREDICATE de INSERT: precisa do contexto.
    doc = with_rls_context(db, admin.id, "ADMIN", _insert)
    return World(admin, sup_a, sup_b, intern, other_intern, patient, doc)
