-- Fallback do pareamento automático por aproximação (item 5): quando
-- RunMatching não acha nenhum estagiário com sobreposição de horário
-- suficiente pro paciente, grava aqui a sugestão mais PRÓXIMA (não é
-- overlap de verdade) — pra o administrativo negociar manualmente com o
-- paciente. Não é um Appointment real (sem sala, sem confirmação).
--
-- Gerada via `prisma migrate diff` (não `migrate dev`, que exige terminal
-- interativo) contra o banco de dev real, já sem drift. O diff bruto também
-- trouxe 4 ALTER TABLE ADD CONSTRAINT redundantes em tabelas não
-- relacionadas (clinical_documents.numero, patients.user_id/cpf_hash,
-- users.totvs_usuario) — o Prisma não reconhece os índices únicos
-- FILTERED que a migration fix_nullable_unique_indexes já criou pra essas
-- colunas nullable como equivalentes ao @unique do schema, e tentaria
-- adicionar uma constraint de unicidade duplicada por cima. Removidos
-- manualmente daqui — esta migration cobre só pending_match_requests.
--
-- CHECK constraint no status segue o mesmo padrão de
-- add_enum_check_constraints (defesa em profundidade pro conjunto fechado
-- de valores, já que SQL Server não tem enum nativo).

CREATE TABLE [dbo].[pending_match_requests] (
    [id] UNIQUEIDENTIFIER NOT NULL,
    [patient_id] UNIQUEIDENTIFIER NOT NULL,
    [suggested_intern_id] UNIQUEIDENTIFIER,
    [suggested_at] DATETIME2,
    [status] NVARCHAR(1000) NOT NULL CONSTRAINT [pending_match_requests_status_df] DEFAULT 'pendente_ajuste_manual',
    [created_at] DATETIME2 NOT NULL CONSTRAINT [pending_match_requests_created_at_df] DEFAULT CURRENT_TIMESTAMP,
    [resolved_at] DATETIME2,
    CONSTRAINT [pending_match_requests_pkey] PRIMARY KEY CLUSTERED ([id])
);

CREATE NONCLUSTERED INDEX [pending_match_requests_patient_id_idx] ON [dbo].[pending_match_requests]([patient_id]);

CREATE NONCLUSTERED INDEX [pending_match_requests_status_idx] ON [dbo].[pending_match_requests]([status]);

ALTER TABLE [dbo].[pending_match_requests] ADD CONSTRAINT [pending_match_requests_patient_id_fkey] FOREIGN KEY ([patient_id]) REFERENCES [dbo].[patients]([id]) ON DELETE NO ACTION ON UPDATE NO ACTION;

ALTER TABLE [dbo].[pending_match_requests] ADD CONSTRAINT [pending_match_requests_suggested_intern_id_fkey] FOREIGN KEY ([suggested_intern_id]) REFERENCES [dbo].[users]([id]) ON DELETE NO ACTION ON UPDATE NO ACTION;

ALTER TABLE [dbo].[pending_match_requests]
  ADD CONSTRAINT [pending_match_requests_status_check] CHECK ([status] IN ('pendente_ajuste_manual', 'resolvido'));
