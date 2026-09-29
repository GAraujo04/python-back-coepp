-- O conector SQL Server do Prisma não suporta `enum` (ver comentário no topo
-- de schema.prisma) — os campos que eram enum viraram String simples.
-- Esta migração reforça o mesmo conjunto fechado de valores a nível de
-- banco, via CHECK constraint — defesa em profundidade (mesmo raciocínio já
-- usado para RLS/WORM: uma falha na aplicação não deve conseguir gravar um
-- valor fora do conjunto válido).

ALTER TABLE [dbo].[users]
  ADD CONSTRAINT [users_role_check] CHECK ([role] IN ('PATIENT', 'INTERN', 'SUPERVISOR', 'ADMIN'));

ALTER TABLE [dbo].[clinical_documents]
  ADD CONSTRAINT [clinical_documents_type_check] CHECK ([type] IN (
    'SCREENING_ADULT', 'SCREENING_CHILD', 'EVOLUTION', 'WEEKLY_REPORT', 'PSYCH_REPORT', 'PSYCH_ASSESSMENT'
  ));

ALTER TABLE [dbo].[clinical_documents]
  ADD CONSTRAINT [clinical_documents_status_check] CHECK ([status] IN (
    'RASCUNHO', 'ENVIADO_PARA_SUPERVISAO', 'EM_REVISAO', 'REVISAO_SOLICITADA', 'REJEITADO', 'APROVADO_LOCKED'
  ));

ALTER TABLE [dbo].[appointments]
  ADD CONSTRAINT [appointments_status_check] CHECK ([status] IN ('SCHEDULED', 'ATTENDED', 'NO_SHOW', 'CANCELLED'));

ALTER TABLE [dbo].[patient_disabilities]
  ADD CONSTRAINT [patient_disabilities_type_check] CHECK ([type] IN (
    'FISICA', 'VISUAL', 'AUDITIVA', 'INTELECTUAL', 'PSICOSSOCIAL', 'MULTIPLA', 'OUTRA'
  ));
