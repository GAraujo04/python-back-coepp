"""Período de atendimentos configurado pelo administrativo.

Revision ID: 0006_attendance_period
Revises: 0005_availability_lock
Create Date: 2026-10-06

O administrativo define a data de início e de fim dos atendimentos do
ciclo (semestre); a partir dela o sistema agenda as consultas semanais no
mesmo horário do pareamento (ver app/shared/scheduling/weekly_series.py).

Uma linha por configuração salva: a vigente é a mais recente. Mudar o
período não apaga o anterior — a trilha de quem definiu o quê fica no
próprio dado, além do audit_log.

Sem RLS: é configuração da clínica, não dado de paciente.
"""

from __future__ import annotations

from alembic import op

revision = "0006_attendance_period"
down_revision = "0005_availability_lock"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute(
        "CREATE TABLE attendance_periods ("
        "id UNIQUEIDENTIFIER NOT NULL CONSTRAINT [attendance_periods_pkey] PRIMARY KEY, "
        "start_date DATE NOT NULL, "
        "end_date DATE NOT NULL, "
        "created_by UNIQUEIDENTIFIER NULL "
        "CONSTRAINT [attendance_periods_created_by_fkey] REFERENCES users(id), "
        "created_at DATETIME2 NOT NULL CONSTRAINT [attendance_periods_created_at_df] DEFAULT CURRENT_TIMESTAMP, "
        "CONSTRAINT [attendance_periods_range_check] CHECK (end_date >= start_date))"
    )


def downgrade() -> None:
    op.execute("DROP TABLE attendance_periods")
