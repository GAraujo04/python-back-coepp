-- Estagiário passa a poder remover o PRÓPRIO documento (ou de que é
-- coautor) enquanto ainda é RASCUNHO — depois de enviado para supervisão,
-- só ADMIN continua podendo remover (mesma regra de sempre). Substitui
-- fn_documents_admin_only (admin-only, sem exceção) por fn_documents_delete
-- no predicado BEFORE DELETE da security policy de clinical_documents.
--
-- Testado ao vivo contra o banco antes de virar migração (protótipo com
-- sufixo _test, descartado): autor deleta RASCUNHO próprio → passa; autor
-- tenta deletar ENVIADO_PARA_SUPERVISAO próprio → bloqueia; admin deleta
-- qualquer status → sempre passa; outro estagiário (não autor/coautor)
-- tenta deletar → nem enxerga a linha (FILTER predicate), 0 linhas afetadas
-- sem erro — mesmo comportamento silencioso já documentado no ADR 0002 para
-- UPDATE fora do escopo de quem não tem vínculo.
--
-- EXEC(N'...') porque CREATE FUNCTION precisa ser o único statement do
-- batch, e ALTER SECURITY POLICY, por segurança, segue o mesmo tratamento
-- (o migration runner do Prisma não faz split por "GO" — ver ADR 0002).

EXEC(N'
ALTER SECURITY POLICY dbo.clinical_documents_rls_policy
  DROP BLOCK PREDICATE ON dbo.clinical_documents BEFORE DELETE;
');

EXEC(N'DROP FUNCTION dbo.fn_documents_admin_only;');

EXEC(N'
CREATE FUNCTION dbo.fn_documents_delete(@patient_id UNIQUEIDENTIFIER, @author_id UNIQUEIDENTIFIER, @id UNIQUEIDENTIFIER, @status NVARCHAR(50))
RETURNS TABLE
WITH SCHEMABINDING
AS
RETURN SELECT 1 AS fn_securitypredicate_result
WHERE
  CAST(SESSION_CONTEXT(N''app_role'') AS NVARCHAR(50)) = ''ADMIN''
  OR (
    CAST(SESSION_CONTEXT(N''app_role'') AS NVARCHAR(50)) = ''INTERN''
    AND @status = ''RASCUNHO''
    AND (
      @author_id = TRY_CAST(SESSION_CONTEXT(N''app_user_id'') AS UNIQUEIDENTIFIER)
      OR EXISTS (
        SELECT 1 FROM dbo._DocumentCoAuthors ca
        WHERE ca.A = @id AND ca.B = TRY_CAST(SESSION_CONTEXT(N''app_user_id'') AS UNIQUEIDENTIFIER)
      )
    )
  );
');

EXEC(N'
ALTER SECURITY POLICY dbo.clinical_documents_rls_policy
  ADD BLOCK PREDICATE dbo.fn_documents_delete(patient_id, author_id, id, status) ON dbo.clinical_documents BEFORE DELETE;
');
