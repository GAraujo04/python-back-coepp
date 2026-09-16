"""Libera os tipos PARTIAL_REPORT e FINAL_REPORT em clinical_documents.

Revision ID: 0003_doc_types_partial_final
Revises: 0002_encrypt_patient_contact
Create Date: 2026-09-16

A CHECK constraint `clinical_documents_type_check` enumera os tipos de
documento aceitos, e a modelagem original já reservava quatro dos cinco
formulários do COEPP — EVOLUTION (ficha de evolução), WEEKLY_REPORT
(acompanhamento semanal), PSYCH_ASSESSMENT (laudo) e PSYCH_REPORT
(relatório psicológico). Faltavam os relatórios de estágio parcial e
final, que o modelo em Word trata como um documento só ("RELATÓRIO FINAL
(OU PARCIAL)") mas que aqui são dois tipos, para aparecerem separados no
prontuário.

Sem esta migração, criar um relatório parcial/final falha no INSERT com
erro 547 da constraint — e não com uma mensagem de validação, porque o
tipo é aceito em toda a aplicação e só o banco o recusa.

A constraint é RECRIADA em vez de alterada: o SQL Server não tem
`ALTER CHECK CONSTRAINT ... WITH` para trocar a expressão. O nome é
preservado (`clinical_documents_type_check`, gerado pelo Prisma quando o
schema foi criado) para não deixar o banco com uma constraint de nome
diferente do que as demais seguem.
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "0003_doc_types_partial_final"
down_revision = "0002_encrypt_patient_contact"
branch_labels = None
depends_on = None

_CONSTRAINT = "clinical_documents_type_check"

_TIPOS_ANTES = (
    "SCREENING_ADULT",
    "SCREENING_CHILD",
    "EVOLUTION",
    "WEEKLY_REPORT",
    "PSYCH_ASSESSMENT",
    "PSYCH_REPORT",
)
_TIPOS_DEPOIS = (*_TIPOS_ANTES, "PARTIAL_REPORT", "FINAL_REPORT")


def _recriar(tipos: tuple[str, ...]) -> None:
    lista = ", ".join(f"'{t}'" for t in tipos)
    op.execute(f"ALTER TABLE clinical_documents DROP CONSTRAINT [{_CONSTRAINT}]")
    op.execute(f"ALTER TABLE clinical_documents ADD CONSTRAINT [{_CONSTRAINT}] CHECK ([type] IN ({lista}))")


def upgrade() -> None:
    _recriar(_TIPOS_DEPOIS)


def downgrade() -> None:
    # Voltar a constraint com documentos parciais/finais já gravados faria o
    # ALTER falhar (o SQL Server valida as linhas existentes ao criar a
    # constraint). Falhar aqui é o comportamento certo: apagar documentos
    # clínicos para caber numa constraint antiga não é decisão de migração.
    bind = op.get_bind()
    existentes = bind.execute(
        sa.text("SELECT COUNT(*) FROM clinical_documents WHERE type IN ('PARTIAL_REPORT', 'FINAL_REPORT')")
    ).scalar_one()
    if existentes:
        raise RuntimeError(
            f"Existem {existentes} relatório(s) parcial/final gravados. Remova-os deliberadamente "
            "antes de reverter esta migração — ela não apaga documentos clínicos."
        )
    _recriar(_TIPOS_ANTES)
