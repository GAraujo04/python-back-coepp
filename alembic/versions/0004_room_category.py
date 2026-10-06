"""Categoria das salas de atendimento.

Revision ID: 0004_room_category
Revises: 0003_doc_types_partial_final
Create Date: 2026-10-06

As 11 salas eram fixas e indistintas. A clínica precisa diferenciá-las —
sala adaptada para pacientes com deficiência (PCD), sala de atendimento
infantil, sala de grupo/família — para o pareamento escolher a sala
conforme a necessidade do atendimento (ver
app/shared/scheduling/room_category.py).

A coluna nasce NOT NULL com DEFAULT 'PADRAO': as salas existentes viram
padrão sem backfill à parte, e todo INSERT que não informe a categoria
(como o seed) continua válido. Com todas as salas padrão o pareamento
escolhe exatamente as mesmas salas de antes.

Constraints com nome explícito, no padrão `<tabela>_<coluna>_<tipo>` das
demais, para o downgrade conseguir derrubá-las (o SQL Server não remove
coluna que ainda tem DEFAULT ou CHECK pendurado).
"""

from __future__ import annotations

from alembic import op

revision = "0004_room_category"
down_revision = "0003_doc_types_partial_final"
branch_labels = None
depends_on = None

_CATEGORIAS = ("PADRAO", "ACESSIVEL", "INFANTIL", "GRUPO")


def upgrade() -> None:
    lista = ", ".join(f"'{c}'" for c in _CATEGORIAS)
    op.execute(
        "ALTER TABLE rooms ADD category NVARCHAR(30) NOT NULL "
        "CONSTRAINT [rooms_category_default] DEFAULT 'PADRAO'"
    )
    op.execute(f"ALTER TABLE rooms ADD CONSTRAINT [rooms_category_check] CHECK ([category] IN ({lista}))")


def downgrade() -> None:
    op.execute("ALTER TABLE rooms DROP CONSTRAINT [rooms_category_check]")
    op.execute("ALTER TABLE rooms DROP CONSTRAINT [rooms_category_default]")
    op.execute("ALTER TABLE rooms DROP COLUMN category")
