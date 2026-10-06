"""Cifra clinical_documents.content em repouso.

Revision ID: 0001_encrypt_clinical_content
Revises: 0000_baseline_prisma_schema
Create Date: 2026-09-10

`content` guardava o relato clínico (triagem, evolução, laudo) em
NVARCHAR(MAX) em claro. Passa a `content_enc` VARBINARY(MAX), cifrado com
AES-256-GCM, mais `content_hash` (SHA-256 do texto claro).

TRÊS ARMADILHAS QUE ESTA MIGRAÇÃO PRECISA DESVIAR
-------------------------------------------------

1. RLS. `clinical_documents` tem SECURITY POLICY com FILTER PREDICATE. Uma
   conexão sem `app_role` no SESSION_CONTEXT enxerga ZERO linhas — e um
   backfill que lê zero linhas não falha: ele termina, informa sucesso, e
   deixa o banco inteiro por converter. Por isso o `app_role = 'ADMIN'`
   abaixo, e por isso a verificação explícita no fim: é a diferença entre
   uma migração que funcionou e uma que só disse que funcionou.

2. Trigger WORM. `trg_clinical_documents_lock` compara `i.content <>
   d.content` pra impedir alteração de documento APROVADO_LOCKED. O
   backfill não toca em `content` (só escreve as colunas novas), então o
   trigger não dispara durante a conversão — mas depois, comparar o
   ciphertext seria inútil: o IV é aleatório, então reescrever o MESMO
   conteúdo produz bytes diferentes e o trigger acusaria alteração onde
   não houve. O trigger é recriado comparando `content_hash`.

3. Ordem. O trigger referencia `content`; a coluna só pode ser removida
   depois que ele deixar de citá-la.

O downgrade decifra de volta para NVARCHAR(MAX) — a migração é
reversível, mas o inverso devolve o prontuário ao estado em claro, que é
justamente o que se quis eliminar. Use só para desfazer um deploy que
falhou, nunca como estado de repouso.

DEPENDÊNCIA DE CÓDIGO: este arquivo importa `app.shared.crypto`. O
formato de payload é versionado (v1, com id de chave no cabeçalho), então
uma mudança futura de formato não reinterpreta o que foi gravado aqui —
mas a chave em ENCRYPTION_KEY precisa ser a mesma no momento de rodar.
"""

from __future__ import annotations

import json

import sqlalchemy as sa
from alembic import op

from app.shared.crypto.json_field import canonical_json, content_digest, decrypt_json, encrypt_json

revision = "0001_encrypt_clinical_content"
down_revision = "0000_base_schema"
branch_labels = None
depends_on = None

_ADMIN_CONTEXT = sa.text("EXEC sp_set_session_context @key = N'app_role', @value = N'ADMIN'")

_OLD_TRIGGER = """
CREATE TRIGGER dbo.trg_clinical_documents_lock ON dbo.clinical_documents
AFTER UPDATE
AS
BEGIN
  SET NOCOUNT ON;
  IF EXISTS (
    SELECT 1
    FROM deleted d
    JOIN inserted i ON i.id = d.id
    WHERE d.status = 'APROVADO_LOCKED' AND i.content <> d.content
  )
  BEGIN
    ROLLBACK TRANSACTION;
    RAISERROR(N'Documento APROVADO_LOCKED é imutável (correções exigem nova versão via supersedes_id).', 16, 1);
  END
END;
"""

_NEW_TRIGGER = """
CREATE TRIGGER dbo.trg_clinical_documents_lock ON dbo.clinical_documents
AFTER UPDATE
AS
BEGIN
  SET NOCOUNT ON;
  IF EXISTS (
    SELECT 1
    FROM deleted d
    JOIN inserted i ON i.id = d.id
    WHERE d.status = 'APROVADO_LOCKED' AND i.content_hash <> d.content_hash
  )
  BEGIN
    ROLLBACK TRANSACTION;
    RAISERROR(N'Documento APROVADO_LOCKED é imutável (correções exigem nova versão via supersedes_id).', 16, 1);
  END
END;
"""


def _drop_default_constraint(bind: sa.engine.Connection, tabela: str, coluna: str) -> None:
    """Remove a constraint DEFAULT da coluna, se existir.

    QUARTA ARMADILHA (não estava no cabeçalho): o schema foi criado pelo
    Prisma, que materializa cada `@default` como uma constraint nomeada
    (`clinical_documents_content_df`). O SQL Server recusa DROP COLUMN
    enquanto qualquer default referencia a coluna, e o erro (5074) cita a
    constraint sem dizer como removê-la — nada em `content` sugere que ela
    exista.

    O nome é buscado no catálogo em vez de escrito à mão: em um banco
    criado pelo próprio SQL Server (sem o Prisma) ele seria um
    `DF__clinical__conte__<hash>` diferente, e um nome fixo faria a
    migração falhar só nesse ambiente.
    """
    nome = bind.execute(
        sa.text(
            "SELECT dc.name FROM sys.default_constraints dc "
            "JOIN sys.columns c ON c.object_id = dc.parent_object_id "
            "AND c.column_id = dc.parent_column_id "
            "WHERE dc.parent_object_id = OBJECT_ID(:tabela) AND c.name = :coluna"
        ),
        {"tabela": tabela, "coluna": coluna},
    ).scalar()
    if nome:
        op.execute(f"ALTER TABLE {tabela} DROP CONSTRAINT [{nome}]")


def upgrade() -> None:
    bind = op.get_bind()

    op.add_column("clinical_documents", sa.Column("content_enc", sa.LargeBinary(), nullable=True))
    op.add_column("clinical_documents", sa.Column("content_hash", sa.String(length=64), nullable=True))

    bind.execute(_ADMIN_CONTEXT)

    rows = bind.execute(sa.text("SELECT id, content FROM clinical_documents")).fetchall()
    for row in rows:
        conteudo = json.loads(row.content)
        bind.execute(
            sa.text("UPDATE clinical_documents SET content_enc = :enc, content_hash = :hash WHERE id = :id"),
            {"enc": encrypt_json(conteudo), "hash": content_digest(conteudo), "id": row.id},
        )

    # Sem isto, uma conexão sem contexto de RLS converteria zero linhas e a
    # migração terminaria "com sucesso". O ALTER ... NOT NULL abaixo até
    # falharia (DDL não passa pela RLS e enxergaria os NULLs), mas com uma
    # mensagem do driver que não diz o que aconteceu de verdade.
    pendentes = bind.execute(sa.text("SELECT COUNT(*) FROM clinical_documents WHERE content_enc IS NULL")).scalar_one()
    if pendentes:
        raise RuntimeError(
            f"{pendentes} documento(s) não foram convertidos. Causa provável: a conexão da migração não "
            "enxergou as linhas por causa da RLS (SESSION_CONTEXT app_role). Nada foi perdido — a "
            "transação será revertida."
        )

    op.alter_column("clinical_documents", "content_enc", existing_type=sa.LargeBinary(), nullable=False)
    op.alter_column("clinical_documents", "content_hash", existing_type=sa.String(length=64), nullable=False)

    op.execute("DROP TRIGGER dbo.trg_clinical_documents_lock")
    op.execute(_NEW_TRIGGER)
    _drop_default_constraint(bind, "clinical_documents", "content")
    op.drop_column("clinical_documents", "content")


def downgrade() -> None:
    bind = op.get_bind()

    op.add_column("clinical_documents", sa.Column("content", sa.UnicodeText(), nullable=True))
    bind.execute(_ADMIN_CONTEXT)

    rows = bind.execute(sa.text("SELECT id, content_enc FROM clinical_documents")).fetchall()
    for row in rows:
        bind.execute(
            sa.text("UPDATE clinical_documents SET content = :content WHERE id = :id"),
            {"content": canonical_json(decrypt_json(row.content_enc)), "id": row.id},
        )

    pendentes = bind.execute(sa.text("SELECT COUNT(*) FROM clinical_documents WHERE content IS NULL")).scalar_one()
    if pendentes:
        raise RuntimeError(f"{pendentes} documento(s) não foram revertidos (ver nota de RLS no upgrade).")

    op.alter_column("clinical_documents", "content", existing_type=sa.UnicodeText(), nullable=False)
    op.execute("DROP TRIGGER dbo.trg_clinical_documents_lock")
    op.execute(_OLD_TRIGGER)
    op.drop_column("clinical_documents", "content_hash")
    op.drop_column("clinical_documents", "content_enc")
