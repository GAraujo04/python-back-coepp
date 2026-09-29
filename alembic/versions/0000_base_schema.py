"""Cria o schema do banco do zero.

Revision ID: 0000_base_schema
Revises:
Create Date: 2026-09-29

Até aqui o schema vinha das migrations do Prisma, no repo `pep` — este
backend só o alterava (0001..0003). O `pep` é a versão antiga do projeto e
saiu do fluxo de desenvolvimento, então o schema passa a nascer aqui.

POR QUE SQL CRU, E NÃO `op.create_table()` A PARTIR DOS MODELOS
---------------------------------------------------------------

Os arquivos em `alembic/sql/baseline/` são as 8 migrations do Prisma
copiadas VERBATIM, na ordem original. Reescrevê-las em SQLAlchemy seria
retraduzir, à mão, coisas que não têm representação em modelo ORM e cuja
sutileza é o ponto:

- as `SECURITY POLICY` de RLS, com FILTER e BLOCK PREDICATE, e as funções
  `WITH SCHEMABINDING` que elas usam (04, 07);
- os triggers WORM que impedem alterar documento `APROVADO_LOCKED` (05);
- o `EXEC(N'...')` em volta de cada `CREATE FUNCTION`/`CREATE SECURITY
  POLICY`/`CREATE TRIGGER`, necessário porque esses comandos têm que ser o
  único statement do batch — e nem o runner do Prisma nem o pyodbc fazem
  split por `GO`.

Um erro de transcrição aqui não apareceria como erro: apareceria como uma
policy que filtra a linha errada, que é exatamente o tipo de bug que a RLS
existe para impedir. Replicar o SQL que já rodou em produção é mais seguro
do que reescrevê-lo bonito.

DUAS ARMADILHAS DE EXECUÇÃO
---------------------------

1. Transação. O `01_init_sqlserver.sql` traz o próprio
   `BEGIN TRAN`/`COMMIT TRAN`/`BEGIN CATCH ... ROLLBACK TRAN` — era como o
   Prisma rodava, cada arquivo atômico por si. Dentro da transação que o
   Alembic abre, esse aninhamento não funciona: o `COMMIT TRAN` de dentro
   não commita nada (só decrementa `@@TRANCOUNT`) e um `ROLLBACK TRAN`
   desfaria também o que o Alembic já tinha feito. Resultado observado:
   o `upgrade` terminava anunciando sucesso e o banco ficava VAZIO — nem
   a `alembic_version` sobrava. Por isso o `autocommit_block()`: cada
   arquivo volta a ser seu próprio batch, como sempre foi.

2. Erro silencioso. O pyodbc só levanta o erro do PRIMEIRO statement de um
   batch; o de qualquer statement seguinte fica retido até alguém pedir o
   próximo result set. Um arquivo destes tem centenas de statements — sem
   o `while cursor.nextset()` abaixo, uma falha no meio passaria
   despercebida e viraria "migration aplicada" com metade do schema.

Um banco que já existia (criado pelo Prisma, com 0001..0003 aplicadas)
está em `0003` e nunca executa esta migration — o Alembic só caminha da
revisão atual até a head.
"""

from __future__ import annotations

from pathlib import Path

from alembic import op

revision = "0000_base_schema"
down_revision = None
branch_labels = None
depends_on = None

_SQL_DIR = Path(__file__).resolve().parent.parent / "sql" / "baseline"


def _executar(sql: str) -> None:
    """Roda um arquivo inteiro como um batch só, checando o batch inteiro.

    Ver armadilha 2 no cabeçalho: sem drenar os result sets, um erro que não
    seja do primeiro statement nunca chega até aqui.
    """
    cursor = op.get_bind().connection.cursor()
    try:
        cursor.execute(sql)
        while cursor.nextset():
            pass
    finally:
        cursor.close()


def upgrade() -> None:
    # autocommit_block: cada arquivo no seu próprio batch/transação, fora da
    # transação do Alembic (ver armadilha 1 no cabeçalho).
    with op.get_context().autocommit_block():
        for arquivo in sorted(_SQL_DIR.glob("*.sql")):
            _executar(arquivo.read_text(encoding="utf-8"))


def downgrade() -> None:
    """Apagar o schema inteiro é `DROP DATABASE`, não uma migration.

    Um downgrade "correto" aqui seria derrubar 16 tabelas, 2 security
    policies, os triggers e as functions na ordem certa de dependência —
    código que ninguém roda, que ninguém testa, e que existiria só para
    apagar todos os dados do banco de uma vez. Para recomeçar do zero:
    `docker compose down -v`.
    """
    raise NotImplementedError(
        "Downgrade do schema base não é suportado. Para recriar o banco do zero, "
        "use `docker compose down -v` e rode `alembic upgrade head` de novo."
    )
