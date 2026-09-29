"""Ambiente do Alembic.

Ponto de atenção herdado: até aqui, o schema deste banco era propriedade
das migrations do Prisma, no repositório Node (`pep/apps/api/prisma/
migrations`). O backend Python declarava `alembic` como dependência mas
nunca o inicializou — na prática, não tinha como aplicar uma mudança de
schema sozinho.

A partir desta revisão, o Alembic assume. As migrations do Prisma
permanecem como o histórico de tudo que já foi aplicado (não são
reescritas nem re-executadas). A revisão 0000_baseline_prisma_schema
reproduz o resultado delas (SQL copiado em `alembic/baseline/`) para
montar um banco do zero; num banco que já veio do Prisma ela não faz nada.

A URL vem do mesmo `load_env()` que a aplicação usa — não de
`alembic.ini` — pra não haver duas fontes de verdade para a credencial do
banco (e pra nenhuma credencial ficar versionada no .ini).
"""

from __future__ import annotations

from logging.config import fileConfig

from alembic import context
from sqlalchemy import engine_from_config, pool

from app.shared.config.env import load_env
from app.shared.db.models import Base

config = context.config
config.set_main_option("sqlalchemy.url", load_env().DATABASE_URL)

if config.config_file_name is not None:
    fileConfig(config.config_file_name)

# Usado por `alembic revision --autogenerate`. As migrations que mexem em
# TRIGGER/SECURITY POLICY são escritas à mão (o autogenerate só enxerga
# tabelas/colunas/índices).
target_metadata = Base.metadata


def run_migrations_offline() -> None:
    context.configure(
        url=config.get_main_option("sqlalchemy.url"),
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
    )
    with context.begin_transaction():
        context.run_migrations()


def run_migrations_online() -> None:
    connectable = engine_from_config(
        config.get_section(config.config_ini_section, {}),
        prefix="sqlalchemy.",
        poolclass=pool.NullPool,
    )
    with connectable.connect() as connection:
        context.configure(connection=connection, target_metadata=target_metadata)
        with context.begin_transaction():
            context.run_migrations()


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
