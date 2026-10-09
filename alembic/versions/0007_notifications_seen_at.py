"""Quando o usuário viu os avisos pela última vez.

Revision ID: 0007_notifications_seen_at
Revises: 0006_attendance_period
Create Date: 2026-10-08

Os avisos internos (o sininho) são calculados na hora a partir do estado
que já existe — fila de revisão, ajustes solicitados, pedidos de
disponibilidade —, sem tabela própria. Só falta saber, para os avisos
informativos (documento aprovado/rejeitado), quais a pessoa já viu: esta
coluna. NULL = nunca abriu, tudo conta como novo.
"""

from __future__ import annotations

from alembic import op

revision = "0007_notifications_seen_at"
down_revision = "0006_attendance_period"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("ALTER TABLE users ADD notifications_seen_at DATETIME2 NULL")


def downgrade() -> None:
    op.execute("ALTER TABLE users DROP COLUMN notifications_seen_at")
