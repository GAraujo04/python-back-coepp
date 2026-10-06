-- SQL Server's UNIQUE constraint rejects multiple NULLs (Postgres allows any
-- number of NULLs in a UNIQUE column). Three columns here are optional and
-- legitimately NULL for most rows:
--   - patients.user_id   (só paciente com login no portal tem conta)
--   - patients.cpf_hash  (só é preenchido quando o paciente informa CPF)
--   - clinical_documents.numero (só é gerado quando o documento é enviado
--     para supervisão — RASCUNHO ainda não tem número)
--
-- A segunda linha com qualquer um desses campos NULL derrubava o INSERT com
-- "Violation of UNIQUE KEY constraint" — bug encontrado durante o teste de
-- RLS desta mesma fase (ver ADR 0002, seção "Descobertas empíricas").
--
-- Fix: trocar o UNIQUE constraint por um índice único FILTRADO
-- (WHERE col IS NOT NULL), que é o equivalente funcional do comportamento
-- padrão do Postgres para essas três colunas.
--
-- Nota: sem "GO" — o migration runner do Prisma executa o arquivo inteiro
-- como statements separados por ";", não entende batch separators de
-- sqlcmd/SSMS.

SET QUOTED_IDENTIFIER ON;

ALTER TABLE [dbo].[patients] DROP CONSTRAINT [patients_user_id_key];

CREATE UNIQUE NONCLUSTERED INDEX [patients_user_id_key] ON [dbo].[patients]([user_id]) WHERE [user_id] IS NOT NULL;

ALTER TABLE [dbo].[patients] DROP CONSTRAINT [patients_cpf_hash_key];

CREATE UNIQUE NONCLUSTERED INDEX [patients_cpf_hash_key] ON [dbo].[patients]([cpf_hash]) WHERE [cpf_hash] IS NOT NULL;

ALTER TABLE [dbo].[clinical_documents] DROP CONSTRAINT [clinical_documents_numero_key];

CREATE UNIQUE NONCLUSTERED INDEX [clinical_documents_numero_key] ON [dbo].[clinical_documents]([numero]) WHERE [numero] IS NOT NULL;
