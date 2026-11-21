"""Propostas de pareamento aguardando a confirmação do administrativo.

Revision ID: 0009_match_proposals
Revises: 0008_availability_changed_at
Create Date: 2026-11-21

Antes, "Rodar pareamento" gravava direto o vínculo e a agenda do semestre.
Agora a rodada só PROPÕE (paciente, estagiário, horário fixo, sala); o
administrativo confere, ajusta se preciso e salva — aí nasce o vínculo — ou
cancela, e a proposta é descartada sem deixar vínculo nem consulta.

Sem RLS: tela exclusiva do administrativo, mesma situação de
pending_match_requests e assignments.
"""

from __future__ import annotations

from alembic import op

revision = "0009_match_proposals"
down_revision = "0008_availability_changed_at"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute(
        "CREATE TABLE match_proposals ("
        "id UNIQUEIDENTIFIER NOT NULL CONSTRAINT [match_proposals_pkey] PRIMARY KEY, "
        "patient_id UNIQUEIDENTIFIER NOT NULL "
        "CONSTRAINT [match_proposals_patient_id_fkey] REFERENCES patients(id), "
        "intern_id UNIQUEIDENTIFIER NOT NULL CONSTRAINT [match_proposals_intern_id_fkey] REFERENCES users(id), "
        "room_id UNIQUEIDENTIFIER NULL CONSTRAINT [match_proposals_room_id_fkey] REFERENCES rooms(id), "
        "scheduled_at DATETIME2 NOT NULL, "
        "created_at DATETIME2 NOT NULL CONSTRAINT [match_proposals_created_at_df] DEFAULT CURRENT_TIMESTAMP)"
    )
    # Um paciente tem no máximo uma proposta em aberto.
    op.execute("CREATE UNIQUE INDEX [match_proposals_patient_id_key] ON match_proposals(patient_id)")


def downgrade() -> None:
    op.execute("DROP TABLE match_proposals")
