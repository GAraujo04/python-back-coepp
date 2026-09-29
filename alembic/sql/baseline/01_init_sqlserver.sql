BEGIN TRY

BEGIN TRAN;

-- CreateTable
CREATE TABLE [dbo].[users] (
    [id] UNIQUEIDENTIFIER NOT NULL,
    [role] NVARCHAR(1000) NOT NULL,
    [full_name] NVARCHAR(1000) NOT NULL,
    [email] NVARCHAR(1000) NOT NULL,
    [crp] NVARCHAR(1000),
    [ra] NVARCHAR(1000),
    [phone] NVARCHAR(1000),
    [department] NVARCHAR(1000),
    [password_hash] NVARCHAR(1000),
    [mfa_secret_enc] VARBINARY(max),
    [active] BIT NOT NULL CONSTRAINT [users_active_df] DEFAULT 1,
    [created_at] DATETIME2 NOT NULL CONSTRAINT [users_created_at_df] DEFAULT CURRENT_TIMESTAMP,
    [updated_at] DATETIME2 NOT NULL,
    [enrollment_verified] BIT NOT NULL CONSTRAINT [users_enrollment_verified_df] DEFAULT 0,
    [academic_supervisor_id] UNIQUEIDENTIFIER,
    [pending_supervisor_name] NVARCHAR(1000),
    [disciplina_id] UNIQUEIDENTIFIER,
    [periodo] NVARCHAR(1000),
    [turma] NVARCHAR(1000),
    CONSTRAINT [users_pkey] PRIMARY KEY CLUSTERED ([id]),
    CONSTRAINT [users_email_key] UNIQUE NONCLUSTERED ([email])
);

-- CreateTable
CREATE TABLE [dbo].[term_acceptances] (
    [id] UNIQUEIDENTIFIER NOT NULL,
    [user_id] UNIQUEIDENTIFIER NOT NULL,
    [term_version] NVARCHAR(1000) NOT NULL,
    [accepted_at] DATETIME2 NOT NULL CONSTRAINT [term_acceptances_accepted_at_df] DEFAULT CURRENT_TIMESTAMP,
    CONSTRAINT [term_acceptances_pkey] PRIMARY KEY CLUSTERED ([id])
);

-- CreateTable
CREATE TABLE [dbo].[disciplinas] (
    [id] UNIQUEIDENTIFIER NOT NULL,
    [name] NVARCHAR(1000) NOT NULL,
    [active] BIT NOT NULL CONSTRAINT [disciplinas_active_df] DEFAULT 1,
    [created_at] DATETIME2 NOT NULL CONSTRAINT [disciplinas_created_at_df] DEFAULT CURRENT_TIMESTAMP,
    CONSTRAINT [disciplinas_pkey] PRIMARY KEY CLUSTERED ([id]),
    CONSTRAINT [disciplinas_name_key] UNIQUE NONCLUSTERED ([name])
);

-- CreateTable
CREATE TABLE [dbo].[refresh_sessions] (
    [id] UNIQUEIDENTIFIER NOT NULL,
    [user_id] UNIQUEIDENTIFIER NOT NULL,
    [token_hash] NVARCHAR(1000) NOT NULL,
    [user_agent] NVARCHAR(1000),
    [ip] NVARCHAR(1000),
    [expires_at] DATETIME2 NOT NULL,
    [revoked_at] DATETIME2,
    [created_at] DATETIME2 NOT NULL CONSTRAINT [refresh_sessions_created_at_df] DEFAULT CURRENT_TIMESTAMP,
    CONSTRAINT [refresh_sessions_pkey] PRIMARY KEY CLUSTERED ([id]),
    CONSTRAINT [refresh_sessions_token_hash_key] UNIQUE NONCLUSTERED ([token_hash])
);

-- CreateTable
CREATE TABLE [dbo].[patients] (
    [id] UNIQUEIDENTIFIER NOT NULL,
    [code] NVARCHAR(1000) NOT NULL,
    [user_id] UNIQUEIDENTIFIER,
    [full_name_enc] VARBINARY(max) NOT NULL,
    [cpf_enc] VARBINARY(max),
    [cpf_hash] NVARCHAR(1000),
    [birth_date] DATE,
    [phone] NVARCHAR(1000),
    [guardian_name_enc] VARBINARY(max),
    [guardian_cpf_enc] VARBINARY(max),
    [guardian_relationship] NVARCHAR(1000),
    [guardian_phone] NVARCHAR(1000),
    [has_disability] BIT NOT NULL CONSTRAINT [patients_has_disability_df] DEFAULT 0,
    [created_at] DATETIME2 NOT NULL CONSTRAINT [patients_created_at_df] DEFAULT CURRENT_TIMESTAMP,
    [updated_at] DATETIME2 NOT NULL,
    CONSTRAINT [patients_pkey] PRIMARY KEY CLUSTERED ([id]),
    CONSTRAINT [patients_code_key] UNIQUE NONCLUSTERED ([code]),
    CONSTRAINT [patients_user_id_key] UNIQUE NONCLUSTERED ([user_id]),
    CONSTRAINT [patients_cpf_hash_key] UNIQUE NONCLUSTERED ([cpf_hash])
);

-- CreateTable
CREATE TABLE [dbo].[patient_disabilities] (
    [id] UNIQUEIDENTIFIER NOT NULL,
    [patient_id] UNIQUEIDENTIFIER NOT NULL,
    [type] NVARCHAR(1000) NOT NULL,
    [other_text_enc] VARBINARY(max),
    [created_at] DATETIME2 NOT NULL CONSTRAINT [patient_disabilities_created_at_df] DEFAULT CURRENT_TIMESTAMP,
    CONSTRAINT [patient_disabilities_pkey] PRIMARY KEY CLUSTERED ([id]),
    CONSTRAINT [patient_disabilities_patient_id_type_key] UNIQUE NONCLUSTERED ([patient_id],[type])
);

-- CreateTable
CREATE TABLE [dbo].[availability_slots] (
    [id] UNIQUEIDENTIFIER NOT NULL,
    [patient_id] UNIQUEIDENTIFIER,
    [intern_id] UNIQUEIDENTIFIER,
    [slot_at] DATETIME2 NOT NULL,
    [matched] BIT NOT NULL CONSTRAINT [availability_slots_matched_df] DEFAULT 0,
    [created_at] DATETIME2 NOT NULL CONSTRAINT [availability_slots_created_at_df] DEFAULT CURRENT_TIMESTAMP,
    CONSTRAINT [availability_slots_pkey] PRIMARY KEY CLUSTERED ([id])
);

-- CreateTable
CREATE TABLE [dbo].[availability_windows] (
    [id] UNIQUEIDENTIFIER NOT NULL,
    [patient_id] UNIQUEIDENTIFIER,
    [intern_id] UNIQUEIDENTIFIER,
    [weekday] INT NOT NULL,
    [start_time] NVARCHAR(1000) NOT NULL,
    [end_time] NVARCHAR(1000) NOT NULL,
    [created_at] DATETIME2 NOT NULL CONSTRAINT [availability_windows_created_at_df] DEFAULT CURRENT_TIMESTAMP,
    CONSTRAINT [availability_windows_pkey] PRIMARY KEY CLUSTERED ([id])
);

-- CreateTable
CREATE TABLE [dbo].[assignments] (
    [id] UNIQUEIDENTIFIER NOT NULL,
    [patient_id] UNIQUEIDENTIFIER NOT NULL,
    [intern_id] UNIQUEIDENTIFIER NOT NULL,
    [supervisor_id] UNIQUEIDENTIFIER,
    [active] BIT NOT NULL CONSTRAINT [assignments_active_df] DEFAULT 1,
    [created_at] DATETIME2 NOT NULL CONSTRAINT [assignments_created_at_df] DEFAULT CURRENT_TIMESTAMP,
    CONSTRAINT [assignments_pkey] PRIMARY KEY CLUSTERED ([id])
);

-- CreateTable
CREATE TABLE [dbo].[appointments] (
    [id] UNIQUEIDENTIFIER NOT NULL,
    [patient_id] UNIQUEIDENTIFIER NOT NULL,
    [intern_id] UNIQUEIDENTIFIER NOT NULL,
    [room_id] UNIQUEIDENTIFIER,
    [scheduled_at] DATETIME2 NOT NULL,
    [status] NVARCHAR(1000) NOT NULL CONSTRAINT [appointments_status_df] DEFAULT 'SCHEDULED',
    [notes] NVARCHAR(max),
    [created_at] DATETIME2 NOT NULL CONSTRAINT [appointments_created_at_df] DEFAULT CURRENT_TIMESTAMP,
    [updated_at] DATETIME2 NOT NULL,
    CONSTRAINT [appointments_pkey] PRIMARY KEY CLUSTERED ([id])
);

-- CreateTable
CREATE TABLE [dbo].[rooms] (
    [id] UNIQUEIDENTIFIER NOT NULL,
    [name] NVARCHAR(1000) NOT NULL,
    [active] BIT NOT NULL CONSTRAINT [rooms_active_df] DEFAULT 1,
    [created_at] DATETIME2 NOT NULL CONSTRAINT [rooms_created_at_df] DEFAULT CURRENT_TIMESTAMP,
    CONSTRAINT [rooms_pkey] PRIMARY KEY CLUSTERED ([id]),
    CONSTRAINT [rooms_name_key] UNIQUE NONCLUSTERED ([name])
);

-- CreateTable
CREATE TABLE [dbo].[clinical_documents] (
    [id] UNIQUEIDENTIFIER NOT NULL,
    [numero] NVARCHAR(1000),
    [patient_id] UNIQUEIDENTIFIER NOT NULL,
    [appointment_id] UNIQUEIDENTIFIER,
    [author_id] UNIQUEIDENTIFIER NOT NULL,
    [type] NVARCHAR(1000) NOT NULL,
    [status] NVARCHAR(1000) NOT NULL CONSTRAINT [clinical_documents_status_df] DEFAULT 'RASCUNHO',
    [version] INT NOT NULL CONSTRAINT [clinical_documents_version_df] DEFAULT 1,
    [content] NVARCHAR(max) NOT NULL CONSTRAINT [clinical_documents_content_df] DEFAULT '{}',
    [supersedes_id] UNIQUEIDENTIFIER,
    [locked_at] DATETIME2,
    [created_at] DATETIME2 NOT NULL CONSTRAINT [clinical_documents_created_at_df] DEFAULT CURRENT_TIMESTAMP,
    [updated_at] DATETIME2 NOT NULL,
    CONSTRAINT [clinical_documents_pkey] PRIMARY KEY CLUSTERED ([id]),
    CONSTRAINT [clinical_documents_numero_key] UNIQUE NONCLUSTERED ([numero])
);

-- CreateTable
CREATE TABLE [dbo].[document_counters] (
    [year] INT NOT NULL,
    [last_value] INT NOT NULL CONSTRAINT [document_counters_last_value_df] DEFAULT 0,
    CONSTRAINT [document_counters_pkey] PRIMARY KEY CLUSTERED ([year])
);

-- CreateTable
CREATE TABLE [dbo].[patient_counters] (
    [year] INT NOT NULL,
    [last_value] INT NOT NULL CONSTRAINT [patient_counters_last_value_df] DEFAULT 0,
    CONSTRAINT [patient_counters_pkey] PRIMARY KEY CLUSTERED ([year])
);

-- CreateTable
CREATE TABLE [dbo].[document_signatures] (
    [id] UNIQUEIDENTIFIER NOT NULL,
    [document_id] UNIQUEIDENTIFIER NOT NULL,
    [signer_id] UNIQUEIDENTIFIER NOT NULL,
    [signer_role] NVARCHAR(1000) NOT NULL,
    [signer_name] NVARCHAR(1000) NOT NULL,
    [signer_ref] NVARCHAR(1000),
    [content_hash] NVARCHAR(1000) NOT NULL,
    [signature_hash] NVARCHAR(1000) NOT NULL,
    [provider] NVARCHAR(1000) NOT NULL CONSTRAINT [document_signatures_provider_df] DEFAULT 'internal',
    [signed_at] DATETIME2 NOT NULL CONSTRAINT [document_signatures_signed_at_df] DEFAULT CURRENT_TIMESTAMP,
    CONSTRAINT [document_signatures_pkey] PRIMARY KEY CLUSTERED ([id])
);

-- CreateTable
CREATE TABLE [dbo].[document_approvals] (
    [id] UNIQUEIDENTIFIER NOT NULL,
    [document_id] UNIQUEIDENTIFIER NOT NULL,
    [supervisor_id] UNIQUEIDENTIFIER NOT NULL,
    [signature] NVARCHAR(max) NOT NULL,
    [content_hash] NVARCHAR(1000) NOT NULL,
    [approved_at] DATETIME2 NOT NULL CONSTRAINT [document_approvals_approved_at_df] DEFAULT CURRENT_TIMESTAMP,
    CONSTRAINT [document_approvals_pkey] PRIMARY KEY CLUSTERED ([id])
);

-- CreateTable
CREATE TABLE [dbo].[review_comments] (
    [id] UNIQUEIDENTIFIER NOT NULL,
    [document_id] UNIQUEIDENTIFIER NOT NULL,
    [reviewer_id] UNIQUEIDENTIFIER NOT NULL,
    [anchor] NVARCHAR(max),
    [body] NVARCHAR(max) NOT NULL,
    [created_at] DATETIME2 NOT NULL CONSTRAINT [review_comments_created_at_df] DEFAULT CURRENT_TIMESTAMP,
    CONSTRAINT [review_comments_pkey] PRIMARY KEY CLUSTERED ([id])
);

-- CreateTable
CREATE TABLE [dbo].[audit_log] (
    [id] BIGINT NOT NULL IDENTITY(1,1),
    [occurred_at] DATETIME2 NOT NULL CONSTRAINT [audit_log_occurred_at_df] DEFAULT CURRENT_TIMESTAMP,
    [actor_id] UNIQUEIDENTIFIER,
    [action] NVARCHAR(1000) NOT NULL,
    [resource_type] NVARCHAR(1000) NOT NULL,
    [resource_id] NVARCHAR(1000),
    [correlation_id] UNIQUEIDENTIFIER,
    [ip] NVARCHAR(1000),
    [user_agent] NVARCHAR(1000),
    [diff] NVARCHAR(max),
    [prev_hash] NVARCHAR(1000),
    [row_hash] NVARCHAR(1000) NOT NULL,
    CONSTRAINT [audit_log_pkey] PRIMARY KEY CLUSTERED ([id])
);

-- CreateTable
CREATE TABLE [dbo].[_DocumentCoAuthors] (
    [A] UNIQUEIDENTIFIER NOT NULL,
    [B] UNIQUEIDENTIFIER NOT NULL,
    CONSTRAINT [_DocumentCoAuthors_AB_unique] UNIQUE NONCLUSTERED ([A],[B])
);

-- CreateIndex
CREATE NONCLUSTERED INDEX [users_role_idx] ON [dbo].[users]([role]);

-- CreateIndex
CREATE NONCLUSTERED INDEX [term_acceptances_user_id_idx] ON [dbo].[term_acceptances]([user_id]);

-- CreateIndex
CREATE NONCLUSTERED INDEX [refresh_sessions_user_id_idx] ON [dbo].[refresh_sessions]([user_id]);

-- CreateIndex
CREATE NONCLUSTERED INDEX [patient_disabilities_patient_id_idx] ON [dbo].[patient_disabilities]([patient_id]);

-- CreateIndex
CREATE NONCLUSTERED INDEX [availability_slots_slot_at_idx] ON [dbo].[availability_slots]([slot_at]);

-- CreateIndex
CREATE NONCLUSTERED INDEX [availability_slots_patient_id_idx] ON [dbo].[availability_slots]([patient_id]);

-- CreateIndex
CREATE NONCLUSTERED INDEX [availability_slots_intern_id_idx] ON [dbo].[availability_slots]([intern_id]);

-- CreateIndex
CREATE NONCLUSTERED INDEX [availability_windows_patient_id_idx] ON [dbo].[availability_windows]([patient_id]);

-- CreateIndex
CREATE NONCLUSTERED INDEX [availability_windows_intern_id_idx] ON [dbo].[availability_windows]([intern_id]);

-- CreateIndex
CREATE NONCLUSTERED INDEX [availability_windows_weekday_idx] ON [dbo].[availability_windows]([weekday]);

-- CreateIndex
CREATE NONCLUSTERED INDEX [assignments_intern_id_idx] ON [dbo].[assignments]([intern_id]);

-- CreateIndex
CREATE NONCLUSTERED INDEX [assignments_supervisor_id_idx] ON [dbo].[assignments]([supervisor_id]);

-- CreateIndex
CREATE NONCLUSTERED INDEX [assignments_patient_id_idx] ON [dbo].[assignments]([patient_id]);

-- CreateIndex
CREATE NONCLUSTERED INDEX [appointments_intern_id_scheduled_at_idx] ON [dbo].[appointments]([intern_id], [scheduled_at]);

-- CreateIndex
CREATE NONCLUSTERED INDEX [appointments_patient_id_idx] ON [dbo].[appointments]([patient_id]);

-- CreateIndex
CREATE NONCLUSTERED INDEX [appointments_room_id_scheduled_at_idx] ON [dbo].[appointments]([room_id], [scheduled_at]);

-- CreateIndex
CREATE NONCLUSTERED INDEX [clinical_documents_patient_id_idx] ON [dbo].[clinical_documents]([patient_id]);

-- CreateIndex
CREATE NONCLUSTERED INDEX [clinical_documents_author_id_idx] ON [dbo].[clinical_documents]([author_id]);

-- CreateIndex
CREATE NONCLUSTERED INDEX [clinical_documents_status_idx] ON [dbo].[clinical_documents]([status]);

-- CreateIndex
CREATE NONCLUSTERED INDEX [document_signatures_document_id_idx] ON [dbo].[document_signatures]([document_id]);

-- CreateIndex
CREATE NONCLUSTERED INDEX [document_approvals_document_id_idx] ON [dbo].[document_approvals]([document_id]);

-- CreateIndex
CREATE NONCLUSTERED INDEX [review_comments_document_id_idx] ON [dbo].[review_comments]([document_id]);

-- CreateIndex
CREATE NONCLUSTERED INDEX [audit_log_resource_type_resource_id_idx] ON [dbo].[audit_log]([resource_type], [resource_id]);

-- CreateIndex
CREATE NONCLUSTERED INDEX [audit_log_actor_id_idx] ON [dbo].[audit_log]([actor_id]);

-- CreateIndex
CREATE NONCLUSTERED INDEX [audit_log_occurred_at_idx] ON [dbo].[audit_log]([occurred_at]);

-- CreateIndex
CREATE NONCLUSTERED INDEX [_DocumentCoAuthors_B_index] ON [dbo].[_DocumentCoAuthors]([B]);

-- AddForeignKey
ALTER TABLE [dbo].[users] ADD CONSTRAINT [users_academic_supervisor_id_fkey] FOREIGN KEY ([academic_supervisor_id]) REFERENCES [dbo].[users]([id]) ON DELETE NO ACTION ON UPDATE NO ACTION;

-- AddForeignKey
ALTER TABLE [dbo].[users] ADD CONSTRAINT [users_disciplina_id_fkey] FOREIGN KEY ([disciplina_id]) REFERENCES [dbo].[disciplinas]([id]) ON DELETE NO ACTION ON UPDATE NO ACTION;

-- AddForeignKey
ALTER TABLE [dbo].[term_acceptances] ADD CONSTRAINT [term_acceptances_user_id_fkey] FOREIGN KEY ([user_id]) REFERENCES [dbo].[users]([id]) ON DELETE CASCADE ON UPDATE NO ACTION;

-- AddForeignKey
ALTER TABLE [dbo].[refresh_sessions] ADD CONSTRAINT [refresh_sessions_user_id_fkey] FOREIGN KEY ([user_id]) REFERENCES [dbo].[users]([id]) ON DELETE CASCADE ON UPDATE NO ACTION;

-- AddForeignKey
ALTER TABLE [dbo].[patients] ADD CONSTRAINT [patients_user_id_fkey] FOREIGN KEY ([user_id]) REFERENCES [dbo].[users]([id]) ON DELETE NO ACTION ON UPDATE NO ACTION;

-- AddForeignKey
ALTER TABLE [dbo].[patient_disabilities] ADD CONSTRAINT [patient_disabilities_patient_id_fkey] FOREIGN KEY ([patient_id]) REFERENCES [dbo].[patients]([id]) ON DELETE CASCADE ON UPDATE NO ACTION;

-- AddForeignKey
ALTER TABLE [dbo].[availability_slots] ADD CONSTRAINT [availability_slots_patient_id_fkey] FOREIGN KEY ([patient_id]) REFERENCES [dbo].[patients]([id]) ON DELETE CASCADE ON UPDATE NO ACTION;

-- AddForeignKey
ALTER TABLE [dbo].[availability_slots] ADD CONSTRAINT [availability_slots_intern_id_fkey] FOREIGN KEY ([intern_id]) REFERENCES [dbo].[users]([id]) ON DELETE CASCADE ON UPDATE NO ACTION;

-- AddForeignKey
ALTER TABLE [dbo].[availability_windows] ADD CONSTRAINT [availability_windows_patient_id_fkey] FOREIGN KEY ([patient_id]) REFERENCES [dbo].[patients]([id]) ON DELETE CASCADE ON UPDATE NO ACTION;

-- AddForeignKey
ALTER TABLE [dbo].[availability_windows] ADD CONSTRAINT [availability_windows_intern_id_fkey] FOREIGN KEY ([intern_id]) REFERENCES [dbo].[users]([id]) ON DELETE CASCADE ON UPDATE NO ACTION;

-- AddForeignKey
ALTER TABLE [dbo].[assignments] ADD CONSTRAINT [assignments_patient_id_fkey] FOREIGN KEY ([patient_id]) REFERENCES [dbo].[patients]([id]) ON DELETE NO ACTION ON UPDATE NO ACTION;

-- AddForeignKey
ALTER TABLE [dbo].[assignments] ADD CONSTRAINT [assignments_intern_id_fkey] FOREIGN KEY ([intern_id]) REFERENCES [dbo].[users]([id]) ON DELETE NO ACTION ON UPDATE NO ACTION;

-- AddForeignKey
ALTER TABLE [dbo].[assignments] ADD CONSTRAINT [assignments_supervisor_id_fkey] FOREIGN KEY ([supervisor_id]) REFERENCES [dbo].[users]([id]) ON DELETE NO ACTION ON UPDATE NO ACTION;

-- AddForeignKey
ALTER TABLE [dbo].[appointments] ADD CONSTRAINT [appointments_patient_id_fkey] FOREIGN KEY ([patient_id]) REFERENCES [dbo].[patients]([id]) ON DELETE NO ACTION ON UPDATE NO ACTION;

-- AddForeignKey
ALTER TABLE [dbo].[appointments] ADD CONSTRAINT [appointments_intern_id_fkey] FOREIGN KEY ([intern_id]) REFERENCES [dbo].[users]([id]) ON DELETE NO ACTION ON UPDATE NO ACTION;

-- AddForeignKey
ALTER TABLE [dbo].[appointments] ADD CONSTRAINT [appointments_room_id_fkey] FOREIGN KEY ([room_id]) REFERENCES [dbo].[rooms]([id]) ON DELETE NO ACTION ON UPDATE NO ACTION;

-- AddForeignKey
ALTER TABLE [dbo].[clinical_documents] ADD CONSTRAINT [clinical_documents_patient_id_fkey] FOREIGN KEY ([patient_id]) REFERENCES [dbo].[patients]([id]) ON DELETE NO ACTION ON UPDATE NO ACTION;

-- AddForeignKey
ALTER TABLE [dbo].[clinical_documents] ADD CONSTRAINT [clinical_documents_appointment_id_fkey] FOREIGN KEY ([appointment_id]) REFERENCES [dbo].[appointments]([id]) ON DELETE NO ACTION ON UPDATE NO ACTION;

-- AddForeignKey
ALTER TABLE [dbo].[clinical_documents] ADD CONSTRAINT [clinical_documents_author_id_fkey] FOREIGN KEY ([author_id]) REFERENCES [dbo].[users]([id]) ON DELETE NO ACTION ON UPDATE NO ACTION;

-- AddForeignKey
ALTER TABLE [dbo].[clinical_documents] ADD CONSTRAINT [clinical_documents_supersedes_id_fkey] FOREIGN KEY ([supersedes_id]) REFERENCES [dbo].[clinical_documents]([id]) ON DELETE NO ACTION ON UPDATE NO ACTION;

-- AddForeignKey
ALTER TABLE [dbo].[document_signatures] ADD CONSTRAINT [document_signatures_document_id_fkey] FOREIGN KEY ([document_id]) REFERENCES [dbo].[clinical_documents]([id]) ON DELETE NO ACTION ON UPDATE NO ACTION;

-- AddForeignKey
ALTER TABLE [dbo].[document_signatures] ADD CONSTRAINT [document_signatures_signer_id_fkey] FOREIGN KEY ([signer_id]) REFERENCES [dbo].[users]([id]) ON DELETE NO ACTION ON UPDATE NO ACTION;

-- AddForeignKey
ALTER TABLE [dbo].[document_approvals] ADD CONSTRAINT [document_approvals_document_id_fkey] FOREIGN KEY ([document_id]) REFERENCES [dbo].[clinical_documents]([id]) ON DELETE NO ACTION ON UPDATE NO ACTION;

-- AddForeignKey
ALTER TABLE [dbo].[document_approvals] ADD CONSTRAINT [document_approvals_supervisor_id_fkey] FOREIGN KEY ([supervisor_id]) REFERENCES [dbo].[users]([id]) ON DELETE NO ACTION ON UPDATE NO ACTION;

-- AddForeignKey
ALTER TABLE [dbo].[review_comments] ADD CONSTRAINT [review_comments_document_id_fkey] FOREIGN KEY ([document_id]) REFERENCES [dbo].[clinical_documents]([id]) ON DELETE NO ACTION ON UPDATE NO ACTION;

-- AddForeignKey
ALTER TABLE [dbo].[review_comments] ADD CONSTRAINT [review_comments_reviewer_id_fkey] FOREIGN KEY ([reviewer_id]) REFERENCES [dbo].[users]([id]) ON DELETE NO ACTION ON UPDATE NO ACTION;

-- AddForeignKey
ALTER TABLE [dbo].[_DocumentCoAuthors] ADD CONSTRAINT [_DocumentCoAuthors_A_fkey] FOREIGN KEY ([A]) REFERENCES [dbo].[clinical_documents]([id]) ON DELETE CASCADE ON UPDATE CASCADE;

-- AddForeignKey
ALTER TABLE [dbo].[_DocumentCoAuthors] ADD CONSTRAINT [_DocumentCoAuthors_B_fkey] FOREIGN KEY ([B]) REFERENCES [dbo].[users]([id]) ON DELETE CASCADE ON UPDATE CASCADE;

COMMIT TRAN;

END TRY
BEGIN CATCH

IF @@TRANCOUNT > 0
BEGIN
    ROLLBACK TRAN;
END;
THROW

END CATCH
