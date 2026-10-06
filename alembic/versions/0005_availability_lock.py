"""Trava de alteração da disponibilidade do estagiário.

Revision ID: 0005_availability_lock
Revises: 0004_room_category
Create Date: 2026-10-06

A disponibilidade recorrente do estagiário é o insumo do pareamento: mudá-la
no meio do semestre desfaz horários já combinados com pacientes. Ela passa a
ficar travada por padrão; o estagiário pede a mudança e o supervisor libera
por um prazo (ver app/features/enrollment/application/availability_lock.py).

- availability_unlocked_until: até quando a edição está liberada. NULL =
  travada. Todo estagiário existente nasce travado — é o requisito.
- availability_change_requested_at / _reason: pedido pendente do
  estagiário, com a justificativa que o supervisor lê antes de liberar.

Colunas anuláveis, sem DEFAULT: nada a derrubar no downgrade além delas.
O 1º preenchimento (completar cadastro) não passa por aqui — grava a
disponibilidade por outro caminho, que continua livre.
"""

from __future__ import annotations

from alembic import op

revision = "0005_availability_lock"
down_revision = "0004_room_category"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute(
        "ALTER TABLE users ADD "
        "availability_unlocked_until DATETIME2 NULL, "
        "availability_change_requested_at DATETIME2 NULL, "
        "availability_change_reason NVARCHAR(500) NULL"
    )


def downgrade() -> None:
    op.execute(
        "ALTER TABLE users DROP COLUMN "
        "availability_unlocked_until, availability_change_requested_at, availability_change_reason"
    )
