-- Row-Level Security via SQL Server Security Policies — equivalente das
-- políticas RLS do Postgres (ver prisma/sql/02_rls_appointments.sql e
-- 03_rls_clinical_documents.sql, mantidos como referência histórica da regra
-- de negócio, e ADR 0002 seção "Segurança — RLS").
--
-- Diferenças de mecanismo em relação ao Postgres:
--   - Postgres: CREATE POLICY ... FOR SELECT/INSERT/UPDATE/DELETE, várias
--     policies por tabela combinadas com OR; FORCE ROW LEVEL SECURITY faz
--     valer até para o owner da tabela.
--   - SQL Server: CREATE SECURITY POLICY com FILTER PREDICATE (rege
--     SELECT/UPDATE/DELETE — linhas invisíveis somem silenciosamente) e
--     BLOCK PREDICATE (rege INSERT/UPDATE/DELETE — operação é rejeitada com
--     erro). Cada tipo de operação só pode ter UM predicate function por
--     tabela, então a lógica "OR entre roles" do Postgres foi consolidada
--     dentro de uma única function por operação, em vez de várias policies.
--   - Testado empiricamente nesta fase: a Security Policy vale mesmo para a
--     conexão `sa` (sysadmin) usada pela aplicação — não há bypass de
--     owner/sysadmin no SQL Server como have o "sem FORCE" do Postgres.
--     Sem SESSION_CONTEXT setado, o FILTER nega tudo (fail-closed).
--   - `EXEC(N'...')` envolve os CREATE FUNCTION/CREATE SECURITY POLICY
--     porque esses comandos precisam ser o único statement do seu batch, e
--     o migration runner do Prisma não faz split por "GO" (só entende
--     statements separados por ";", enviados como um único batch T-SQL).
--
-- Nota sobre TRY_CAST: SESSION_CONTEXT(N'app_user_id') pode vir NULL (sem
-- contexto setado) ou, em tese, um valor não-GUID; TRY_CAST devolve NULL em
-- vez de estourar erro, então uma query "não sensível a RLS" nunca quebra
-- por causa da function de segurança.

-- =====================================================================
-- appointments
-- =====================================================================

EXEC(N'
CREATE FUNCTION dbo.fn_appointments_select(@patient_id UNIQUEIDENTIFIER, @intern_id UNIQUEIDENTIFIER)
RETURNS TABLE
WITH SCHEMABINDING
AS
RETURN SELECT 1 AS fn_securitypredicate_result
WHERE
  CAST(SESSION_CONTEXT(N''app_role'') AS NVARCHAR(50)) = ''ADMIN''
  OR (
    CAST(SESSION_CONTEXT(N''app_role'') AS NVARCHAR(50)) = ''INTERN''
    AND @intern_id = TRY_CAST(SESSION_CONTEXT(N''app_user_id'') AS UNIQUEIDENTIFIER)
  )
  OR (
    CAST(SESSION_CONTEXT(N''app_role'') AS NVARCHAR(50)) = ''SUPERVISOR''
    AND EXISTS (
      SELECT 1 FROM dbo.assignments a
      WHERE a.patient_id = @patient_id
        AND a.supervisor_id = TRY_CAST(SESSION_CONTEXT(N''app_user_id'') AS UNIQUEIDENTIFIER)
        AND a.active = 1
    )
  );
');

-- INSERT/DELETE: só ADMIN (o Postgres original não tinha policy de INSERT
-- nem DELETE pra INTERN/SUPERVISOR — agendamento é criado pelo algoritmo de
-- match ou pelo match manual, ambos rodando em contexto ADMIN).
EXEC(N'
CREATE FUNCTION dbo.fn_appointments_admin_only(@patient_id UNIQUEIDENTIFIER, @intern_id UNIQUEIDENTIFIER)
RETURNS TABLE
WITH SCHEMABINDING
AS
RETURN SELECT 1 AS fn_securitypredicate_result
WHERE CAST(SESSION_CONTEXT(N''app_role'') AS NVARCHAR(50)) = ''ADMIN'';
');

-- UPDATE: ADMIN ou o próprio estagiário (registrar presença/status). O
-- WITH CHECK original também exigia intern_id = self no valor NOVO (não
-- deixa reatribuir o agendamento a outro estagiário via UPDATE) — por isso
-- esta function é usada tanto em BEFORE quanto em AFTER UPDATE.
EXEC(N'
CREATE FUNCTION dbo.fn_appointments_update(@patient_id UNIQUEIDENTIFIER, @intern_id UNIQUEIDENTIFIER)
RETURNS TABLE
WITH SCHEMABINDING
AS
RETURN SELECT 1 AS fn_securitypredicate_result
WHERE
  CAST(SESSION_CONTEXT(N''app_role'') AS NVARCHAR(50)) = ''ADMIN''
  OR (
    CAST(SESSION_CONTEXT(N''app_role'') AS NVARCHAR(50)) = ''INTERN''
    AND @intern_id = TRY_CAST(SESSION_CONTEXT(N''app_user_id'') AS UNIQUEIDENTIFIER)
  );
');

EXEC(N'
CREATE SECURITY POLICY dbo.appointments_rls_policy
  ADD FILTER PREDICATE dbo.fn_appointments_select(patient_id, intern_id) ON dbo.appointments,
  ADD BLOCK PREDICATE dbo.fn_appointments_admin_only(patient_id, intern_id) ON dbo.appointments AFTER INSERT,
  ADD BLOCK PREDICATE dbo.fn_appointments_admin_only(patient_id, intern_id) ON dbo.appointments BEFORE DELETE,
  ADD BLOCK PREDICATE dbo.fn_appointments_update(patient_id, intern_id) ON dbo.appointments BEFORE UPDATE,
  ADD BLOCK PREDICATE dbo.fn_appointments_update(patient_id, intern_id) ON dbo.appointments AFTER UPDATE
WITH (STATE = ON);
');

-- =====================================================================
-- clinical_documents
-- =====================================================================

-- SELECT: ADMIN, ou INTERN autor/coautor, ou SUPERVISOR do paciente
-- (vínculo ativo em assignments).
EXEC(N'
CREATE FUNCTION dbo.fn_documents_select(@patient_id UNIQUEIDENTIFIER, @author_id UNIQUEIDENTIFIER, @id UNIQUEIDENTIFIER)
RETURNS TABLE
WITH SCHEMABINDING
AS
RETURN SELECT 1 AS fn_securitypredicate_result
WHERE
  CAST(SESSION_CONTEXT(N''app_role'') AS NVARCHAR(50)) = ''ADMIN''
  OR (
    CAST(SESSION_CONTEXT(N''app_role'') AS NVARCHAR(50)) = ''INTERN''
    AND (
      @author_id = TRY_CAST(SESSION_CONTEXT(N''app_user_id'') AS UNIQUEIDENTIFIER)
      OR EXISTS (
        SELECT 1 FROM dbo._DocumentCoAuthors ca
        WHERE ca.A = @id AND ca.B = TRY_CAST(SESSION_CONTEXT(N''app_user_id'') AS UNIQUEIDENTIFIER)
      )
    )
  )
  OR (
    CAST(SESSION_CONTEXT(N''app_role'') AS NVARCHAR(50)) = ''SUPERVISOR''
    AND EXISTS (
      SELECT 1 FROM dbo.assignments a
      WHERE a.patient_id = @patient_id
        AND a.supervisor_id = TRY_CAST(SESSION_CONTEXT(N''app_user_id'') AS UNIQUEIDENTIFIER)
        AND a.active = 1
    )
  );
');

-- INSERT: ADMIN ou o próprio estagiário criando como autor (author_id = self).
EXEC(N'
CREATE FUNCTION dbo.fn_documents_insert(@author_id UNIQUEIDENTIFIER)
RETURNS TABLE
WITH SCHEMABINDING
AS
RETURN SELECT 1 AS fn_securitypredicate_result
WHERE
  CAST(SESSION_CONTEXT(N''app_role'') AS NVARCHAR(50)) = ''ADMIN''
  OR (
    CAST(SESSION_CONTEXT(N''app_role'') AS NVARCHAR(50)) = ''INTERN''
    AND @author_id = TRY_CAST(SESSION_CONTEXT(N''app_user_id'') AS UNIQUEIDENTIFIER)
  );
');

-- UPDATE: ADMIN ou autor/coautor (mesma condição do USING original). O
-- Postgres original tinha WITH CHECK (true) pro estagiário — sem restrição
-- adicional sobre os valores novos — por isso aqui só existe BLOCK
-- PREDICATE BEFORE UPDATE (valida a linha antes do update), sem AFTER.
EXEC(N'
CREATE FUNCTION dbo.fn_documents_update(@author_id UNIQUEIDENTIFIER, @id UNIQUEIDENTIFIER)
RETURNS TABLE
WITH SCHEMABINDING
AS
RETURN SELECT 1 AS fn_securitypredicate_result
WHERE
  CAST(SESSION_CONTEXT(N''app_role'') AS NVARCHAR(50)) = ''ADMIN''
  OR (
    CAST(SESSION_CONTEXT(N''app_role'') AS NVARCHAR(50)) = ''INTERN''
    AND (
      @author_id = TRY_CAST(SESSION_CONTEXT(N''app_user_id'') AS UNIQUEIDENTIFIER)
      OR EXISTS (
        SELECT 1 FROM dbo._DocumentCoAuthors ca
        WHERE ca.A = @id AND ca.B = TRY_CAST(SESSION_CONTEXT(N''app_user_id'') AS UNIQUEIDENTIFIER)
      )
    )
  );
');

-- DELETE: só ADMIN (não havia policy de DELETE pra INTERN/SUPERVISOR —
-- documento é substituído via nova versão/supersedes_id, nunca apagado).
EXEC(N'
CREATE FUNCTION dbo.fn_documents_admin_only(@patient_id UNIQUEIDENTIFIER)
RETURNS TABLE
WITH SCHEMABINDING
AS
RETURN SELECT 1 AS fn_securitypredicate_result
WHERE CAST(SESSION_CONTEXT(N''app_role'') AS NVARCHAR(50)) = ''ADMIN'';
');

EXEC(N'
CREATE SECURITY POLICY dbo.clinical_documents_rls_policy
  ADD FILTER PREDICATE dbo.fn_documents_select(patient_id, author_id, id) ON dbo.clinical_documents,
  ADD BLOCK PREDICATE dbo.fn_documents_insert(author_id) ON dbo.clinical_documents AFTER INSERT,
  ADD BLOCK PREDICATE dbo.fn_documents_update(author_id, id) ON dbo.clinical_documents BEFORE UPDATE,
  ADD BLOCK PREDICATE dbo.fn_documents_admin_only(patient_id) ON dbo.clinical_documents BEFORE DELETE
WITH (STATE = ON);
');
