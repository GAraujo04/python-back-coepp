-- Imutabilidade e integridade (equivalente T-SQL de prisma/sql/01_immutability.sql,
-- mantido como referência histórica da regra de negócio; ver ADR 0002).
--
-- SQL Server não tem trigger BEFORE (só AFTER e INSTEAD OF). O padrão
-- equivalente a "BEFORE ... RAISE EXCEPTION" do Postgres é um trigger AFTER
-- que, ao detectar a violação, faz ROLLBACK TRANSACTION (desfaz o
-- INSERT/UPDATE/DELETE inteiro) e só depois RAISERROR (informa o cliente).
-- Essa ordem (rollback antes do raise) é a recomendada pela documentação da
-- Microsoft para triggers de bloqueio — o RAISERROR após o ROLLBACK ainda
-- funciona normalmente e devolve a mensagem de erro pro chamador.
--
-- `inserted`/`deleted` são pseudo-tabelas por statement (todo o lote
-- afetado, não linha-a-linha) — os triggers abaixo são set-based, iguais ao
-- espírito do original.
--
-- `EXEC(N'...')` porque CREATE TRIGGER precisa ser o único statement do seu
-- batch, e o migration runner do Prisma não faz split por "GO".

-- 1) Trilha de auditoria APPEND-ONLY: bloqueia UPDATE e DELETE via trigger
--    (independe de GRANT/REVOKE — vale até pro owner/sysadmin da conexão).
EXEC(N'
CREATE TRIGGER dbo.trg_audit_log_append_only ON dbo.audit_log
AFTER UPDATE, DELETE
AS
BEGIN
  SET NOCOUNT ON;
  ROLLBACK TRANSACTION;
  RAISERROR(N''audit_log é append-only: UPDATE/DELETE não permitido.'', 16, 1);
END;
');

-- 2) WORM em documentos clínicos: um documento APROVADO_LOCKED não pode ter
--    o conteúdo alterado (correções exigem nova versão via supersedes_id).
--    `content` agora é NVARCHAR(MAX) (não é mais Json — SQL Server não
--    suporta o tipo Json — mas continua NOT NULL, então <> basta, sem
--    precisar do equivalente a IS DISTINCT FROM do Postgres).
EXEC(N'
CREATE TRIGGER dbo.trg_clinical_documents_lock ON dbo.clinical_documents
AFTER UPDATE
AS
BEGIN
  SET NOCOUNT ON;
  IF EXISTS (
    SELECT 1
    FROM deleted d
    JOIN inserted i ON i.id = d.id
    WHERE d.status = ''APROVADO_LOCKED'' AND i.content <> d.content
  )
  BEGIN
    ROLLBACK TRANSACTION;
    RAISERROR(N''Documento APROVADO_LOCKED é imutável (correções exigem nova versão via supersedes_id).'', 16, 1);
  END
END;
');
