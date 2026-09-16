"""Cifra data de nascimento e telefones do paciente.

Revision ID: 0002_encrypt_patient_contact
Revises: 0001_encrypt_clinical_content
Create Date: 2026-09-10

`patients` já cifrava nome e CPF, mas deixava em claro `birth_date`,
`phone` e `guardian_phone`. A data de nascimento é o caso que pesa: ela é
METADE da credencial de login do paciente (o outro fator é o CPF). Em
claro, quem lesse a tabela já teria um dos dois fatores de toda a base —
inclusive dos pacientes cujo nome e CPF a criptografia protegia.

Diferente da 0001, aqui não há armadilha de RLS: `patients` não tem
SECURITY POLICY (o escopo por vínculo é WHERE explícito na aplicação),
então a conexão da migração enxerga todas as linhas. O contador de
verificação no fim existe mesmo assim — custa uma query e é o que
distingue "converteu tudo" de "não tinha nada pra converter".

`guardian_relationship` fica em claro de propósito: é um rótulo curto e
fechado ("mãe", "pai", "responsável legal") que não identifica ninguém
sozinho.
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

from app.shared.crypto.field_encryption import decrypt_field, encrypt_field

revision = "0002_encrypt_patient_contact"
down_revision = "0001_encrypt_clinical_content"
branch_labels = None
depends_on = None

# (coluna em claro, coluna cifrada)
_COLUNAS = [
    ("birth_date", "birth_date_enc"),
    ("phone", "phone_enc"),
    ("guardian_phone", "guardian_phone_enc"),
]


def upgrade() -> None:
    bind = op.get_bind()

    for _, cifrada in _COLUNAS:
        op.add_column("patients", sa.Column(cifrada, sa.LargeBinary(), nullable=True))

    rows = bind.execute(sa.text("SELECT id, birth_date, phone, guardian_phone FROM patients")).fetchall()
    for row in rows:
        # birth_date volta do driver como datetime.date; guardamos o ISO
        # (yyyy-mm-dd), que é a forma em que todo consumidor já a usava.
        valores = {
            "birth_date_enc": encrypt_field(row.birth_date.isoformat()) if row.birth_date else None,
            "phone_enc": encrypt_field(row.phone) if row.phone else None,
            "guardian_phone_enc": encrypt_field(row.guardian_phone) if row.guardian_phone else None,
            "id": row.id,
        }
        bind.execute(
            sa.text(
                "UPDATE patients SET birth_date_enc = :birth_date_enc, phone_enc = :phone_enc, "
                "guardian_phone_enc = :guardian_phone_enc WHERE id = :id"
            ),
            valores,
        )

    pendentes = bind.execute(
        sa.text("SELECT COUNT(*) FROM patients WHERE birth_date IS NOT NULL AND birth_date_enc IS NULL")
    ).scalar_one()
    if pendentes:
        raise RuntimeError(f"{pendentes} paciente(s) com data de nascimento não convertida. Transação revertida.")

    for clara, _ in _COLUNAS:
        op.drop_column("patients", clara)


def downgrade() -> None:
    bind = op.get_bind()

    op.add_column("patients", sa.Column("birth_date", sa.Date(), nullable=True))
    op.add_column("patients", sa.Column("phone", sa.Unicode(length=255), nullable=True))
    op.add_column("patients", sa.Column("guardian_phone", sa.Unicode(length=255), nullable=True))

    rows = bind.execute(sa.text("SELECT id, birth_date_enc, phone_enc, guardian_phone_enc FROM patients")).fetchall()
    for row in rows:
        bind.execute(
            sa.text(
                "UPDATE patients SET birth_date = :birth_date, phone = :phone, "
                "guardian_phone = :guardian_phone WHERE id = :id"
            ),
            {
                "birth_date": decrypt_field(row.birth_date_enc) if row.birth_date_enc else None,
                "phone": decrypt_field(row.phone_enc) if row.phone_enc else None,
                "guardian_phone": decrypt_field(row.guardian_phone_enc) if row.guardian_phone_enc else None,
                "id": row.id,
            },
        )

    for _, cifrada in _COLUNAS:
        op.drop_column("patients", cifrada)
