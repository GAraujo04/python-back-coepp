"""Popula o banco de desenvolvimento: um usuário de cada papel de staff, um
paciente com PII cifrada e conta de portal, as salas de atendimento e o
vínculo estagiário/supervisor/paciente.

    .venv/bin/python -m scripts.seed

Porta `prisma/seed.ts` do repo `pep` (a versão antiga do projeto), que era de
onde os dados de exemplo vinham até agora. Mesmos e-mails, mesma senha, mesmo
CPF — quem já usava aquele seed não precisa reaprender nada.

Idempotente: pode rodar quantas vezes quiser (antes de uma apresentação, por
exemplo) sem duplicar nada. NUNCA rode contra um banco de produção: as senhas
aqui são públicas.

Uma diferença em relação ao original, e o motivo: a data de nascimento do
paciente vai cifrada (`birth_date_enc`), não em claro. A migration 0002
converteu essa coluna — ela é metade da credencial de login do paciente (a
outra é o CPF, também cifrado), então em claro ela entregaria um dos dois
fatores de toda a base para quem lesse a tabela.
"""

from __future__ import annotations

import sys

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.shared.config.env import load_env
from app.shared.crypto.blind_index import cpf_blind_index
from app.shared.crypto.field_encryption import encrypt_field
from app.shared.db.models import Assignment, Patient, Room, User
from app.shared.db.patient_code import next_patient_code
from app.shared.db.session import SessionLocal

DEV_PASSWORD = "senha1234"
PATIENT_CPF = "000.000.000-00"
PATIENT_BIRTH_DATE = "1998-05-20"
# Salas de atendimento: dado de referência real, não conta fake de demo como o
# resto deste arquivo — por isso o upsert por nome, que preserva o que já existe.
ROOM_NAMES = [f"Sala {i}" for i in range(1, 12)]

STAFF = [
    {"email": "admin@clinica.br", "full_name": "Administrativo", "role": "ADMIN"},
    {"email": "supervisor@clinica.br", "full_name": "Dra. Helena Prof.", "role": "SUPERVISOR", "crp": "CRP-06/123456"},
    {"email": "estagiario@clinica.br", "full_name": "João Estagiário", "role": "INTERN"},
]


def _upsert_user(session: Session, password_hash: str, **campos: str) -> User:
    existente = session.scalar(select(User).where(User.email == campos["email"]))
    if existente is not None:
        return existente
    user = User(password_hash=password_hash, **campos)
    session.add(user)
    session.flush()
    return user


def seed(session: Session) -> dict[str, str]:
    # Import local: a infra de auth conhece o algoritmo (Argon2id), o resto do
    # código não — mesma fronteira que o backend mantém em produção.
    from app.features.auth.infrastructure.argon_password_hasher import ArgonPasswordHasher

    password_hash = ArgonPasswordHasher().hash(DEV_PASSWORD)

    usuarios = {campos["role"]: _upsert_user(session, password_hash, **campos) for campos in STAFF}

    # Paciente no mesmo formato do autocadastro público: sem senha, login por
    # CPF + data de nascimento. A idempotência é pelo cpf_hash (índice cego,
    # único) — e a checagem vem ANTES de next_patient_code() de propósito, pra
    # não queimar um sequencial do contador a cada rerun.
    cpf_hash = cpf_blind_index(PATIENT_CPF)
    paciente = session.scalar(select(Patient).where(Patient.cpf_hash == cpf_hash))
    if paciente is None:
        conta = User(role="PATIENT", full_name="Maria dos Santos", email="maria.santos@exemplo.br")
        session.add(conta)
        session.flush()
        paciente = Patient(
            code=next_patient_code(session),
            user_id=conta.id,
            full_name_enc=encrypt_field("Maria dos Santos"),
            cpf_enc=encrypt_field(PATIENT_CPF),
            cpf_hash=cpf_hash,
            birth_date_enc=encrypt_field(PATIENT_BIRTH_DATE),
        )
        session.add(paciente)
        session.flush()

    for nome in ROOM_NAMES:
        if session.scalar(select(Room).where(Room.name == nome)) is None:
            session.add(Room(name=nome))

    vinculo = session.scalar(
        select(Assignment).where(
            Assignment.patient_id == paciente.id,
            Assignment.intern_id == usuarios["INTERN"].id,
        )
    )
    if vinculo is None:
        session.add(
            Assignment(
                patient_id=paciente.id,
                intern_id=usuarios["INTERN"].id,
                supervisor_id=usuarios["SUPERVISOR"].id,
            )
        )

    session.commit()
    return {"codigo_paciente": paciente.code}


def main() -> None:
    env = load_env()
    if env.APP_ENV == "production":
        # As credenciais deste arquivo são públicas — estão no repositório.
        print("❌ Recusando rodar o seed com APP_ENV=production.", file=sys.stderr)
        raise SystemExit(1)

    with SessionLocal() as session:
        resultado = seed(session)

    print("✅ Seed concluído.")
    print("   admin ......... admin@clinica.br      / " + DEV_PASSWORD)
    print("   supervisor .... supervisor@clinica.br / " + DEV_PASSWORD)
    print("   estagiário .... estagiario@clinica.br / " + DEV_PASSWORD + " (não loga por senha — é via TOTVS)")
    print(f"   paciente ...... CPF {PATIENT_CPF} + nascimento 20/05/1998 (código {resultado['codigo_paciente']})")
    print(f"   salas ......... {len(ROOM_NAMES)}")


if __name__ == "__main__":
    main()
