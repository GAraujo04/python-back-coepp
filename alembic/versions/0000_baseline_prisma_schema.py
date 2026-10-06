"""Schema base (tabelas, CHECKs, RLS, triggers WORM) herdado do Prisma.

Revision ID: 0000_baseline_prisma_schema
Revises:
Create Date: 2026-09-29

Até aqui o Alembic partia de um banco JÁ criado pelas migrations do Prisma
(`pep/apps/api/prisma/migrations`) — não havia como montar um banco do
zero sem o repositório Node. Esta revisão fecha esse buraco: os SQLs de
`alembic/baseline/` são cópia literal, na mesma ordem, das 7 migrations do
Prisma, executados cada um como um batch T-SQL (igual ao runner do
Prisma, que não faz split por "GO" — por isso os `EXEC(N'...')` neles).

Banco que já veio do Prisma: as tabelas existem, então esta revisão só é
marcada como aplicada, sem executar nada. Isso vale tanto para um banco
nunca tocado pelo Alembic quanto para um que já esteja em 0001+ (nesse
caso o Alembic nem chega a rodá-la).

Os arquivos de baseline são histórico congelado: mudança de schema nova
vai numa revisão nova, nunca editando eles.
"""

from __future__ import annotations

from pathlib import Path

from alembic import op

revision = "0000_baseline_prisma_schema"
down_revision = None
branch_labels = None
depends_on = None

_BASELINE_DIR = Path(__file__).resolve().parent.parent / "baseline"


def upgrade() -> None:
    bind = op.get_bind()
    if bind.exec_driver_sql("SELECT OBJECT_ID(N'dbo.users', N'U')").scalar() is not None:
        return
    # Cursor cru, não op.execute: sa.text() interpretaria ":palavra" dos
    # comentários como bind parameter. E o pyodbc só executa o resto de um
    # batch com vários statements conforme os resultados são consumidos —
    # sem drenar com nextset(), o COMMIT TRAN do fim do 01 nunca roda, a
    # transação fica aninhada (@@TRANCOUNT 2) e o commit do Alembic não
    # persiste nada, sem erro nenhum.
    cursor = bind.connection.dbapi_connection.cursor()
    try:
        for sql_file in sorted(_BASELINE_DIR.glob("*.sql")):
            cursor.execute(sql_file.read_text(encoding="utf-8"))
            while cursor.nextset():
                pass
    finally:
        cursor.close()
    trancount = bind.exec_driver_sql("SELECT @@TRANCOUNT").scalar()
    if trancount != 1:
        raise RuntimeError(f"Baseline deixou @@TRANCOUNT = {trancount} (esperado 1)")


def downgrade() -> None:
    raise NotImplementedError(
        "Baseline não tem downgrade: desfazer significaria apagar o banco inteiro. "
        "Para recomeçar do zero, recrie o banco (DROP/CREATE DATABASE)."
    )
