"""Quando o estagiário alterou a disponibilidade pela última vez.

Revision ID: 0008_availability_changed_at
Revises: 0007_notifications_seen_at
Create Date: 2026-11-21

A liberação da mudança é do supervisor; o administrativo só precisa saber
que a disponibilidade mudou e qual é a nova, para ajustar o pareamento.
Esta coluna é o "quando" desse aviso. NULL = nunca alterou depois do
cadastro (o 1º preenchimento não conta como alteração).
"""

from __future__ import annotations

from alembic import op

revision = "0008_availability_changed_at"
down_revision = "0007_notifications_seen_at"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("ALTER TABLE users ADD availability_changed_at DATETIME2 NULL")


def downgrade() -> None:
    op.execute("ALTER TABLE users DROP COLUMN availability_changed_at")
