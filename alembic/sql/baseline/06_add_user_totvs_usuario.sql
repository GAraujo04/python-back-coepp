-- Campo de vínculo do estagiário com o TOTVS RM (login por usuário RM).
-- Nulo para PATIENT/SUPERVISOR/ADMIN e para INTERN ainda não vinculado —
-- por isso, igual a patients.user_id/cpf_hash e clinical_documents.numero
-- (ver migração 20260817195423_fix_nullable_unique_indexes), usamos índice
-- único FILTRADO em vez de UNIQUE constraint: SQL Server rejeita múltiplos
-- NULL numa UNIQUE constraint comum (Postgres não).

-- EXEC(N'...') na 2ª instrução: dentro de um único batch (o migration runner
-- do Prisma não faz split por "GO"), SQL Server resolve nomes de coluna no
-- momento da compilação do batch inteiro — uma coluna adicionada pelo ALTER
-- TABLE acima ainda não é visível para um CREATE INDEX no mesmo batch
-- (erro "Invalid column name"). Dynamic SQL compila em tempo de execução,
-- quando a coluna já existe (mesma técnica usada nas migrações de RLS/WORM
-- da Fase 8, lá por causa de CREATE FUNCTION precisar ser o único statement
-- do batch — motivo diferente, mesma solução).

SET QUOTED_IDENTIFIER ON;

ALTER TABLE [dbo].[users] ADD [totvs_usuario] NVARCHAR(1000) NULL;

EXEC(N'CREATE UNIQUE NONCLUSTERED INDEX [users_totvs_usuario_key] ON [dbo].[users]([totvs_usuario]) WHERE [totvs_usuario] IS NOT NULL;');
