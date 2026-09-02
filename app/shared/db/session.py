"""Engine/sessão SQLAlchemy + contexto de RLS.

Porta shared/db/prisma.ts. `engine`/`SessionLocal` substituem o `PrismaClient`
singleton; `with_rls_context` substitui `withRlsContext`.

Diferença importante em relação ao Postgres (não muda entre TS e Python,
já valia lá): SESSION_CONTEXT do SQL Server é escopado à CONEXÃO, não à
transação — o valor sobrevive ao fim da transação enquanto a conexão ficar
aberta no pool. Por isso `with_rls_context` reseta os dois valores como as
duas primeiras instruções da transação, antes de rodar `fn` — mesmo que a
conexão seja reaproveitada de uma requisição anterior, o contexto de quem
quer que tenha usado a conexão antes é sobrescrito antes de qualquer leitura
sensível a RLS acontecer. A garantia depende de TODA query sensível a RLS
passar por aqui — nunca ler `appointments`/`clinical_documents` fora deste
contexto.
"""

from __future__ import annotations

from collections.abc import Callable, Iterator
from contextlib import contextmanager

from sqlalchemy import Engine, create_engine, text
from sqlalchemy.orm import Session, sessionmaker

from ..config.env import load_env


def _make_engine() -> Engine:
    return create_engine(load_env().DATABASE_URL, pool_pre_ping=True)


engine = _make_engine()
SessionLocal = sessionmaker(bind=engine, autoflush=False, expire_on_commit=False)


@contextmanager
def get_session() -> Iterator[Session]:
    """Sessão de escopo curto (uma por request) — equivalente ao dependency
    injection do Fastify de reusar `prisma`, mas aqui cada request ganha sua
    própria Session (padrão SQLAlchemy: Session não é segura pra concorrência,
    diferente do client do Prisma, que é um pool compartilhado — por isso os
    repositórios/casos de uso são instanciados por REQUEST aqui, não uma vez
    só no boot como no `authRoutes()` original).

    Commit automático ao sair do `with` sem erro (equivalente ao Prisma, que
    não exige commit explícito fora de `$transaction`); rollback automático
    em caso de exceção — nenhuma escrita parcial fica pendurada."""
    session = SessionLocal()
    try:
        yield session
        session.commit()
    except Exception:
        session.rollback()
        raise
    finally:
        session.close()


def with_rls_context[T](session: Session, user_id: str, role: str, fn: Callable[[Session], T]) -> T:
    """Executa `fn` dentro de uma transação com o contexto de RLS setado
    (app_user_id / app_role). As SECURITY POLICIES do SQL Server leem esses
    valores via SESSION_CONTEXT() — última linha de defesa de autorização:
    mesmo uma falha na aplicação não vaza linhas de outro vínculo."""
    with session.begin():
        session.execute(
            text("EXEC sp_set_session_context @key = N'app_user_id', @value = :user_id"),
            {"user_id": user_id},
        )
        session.execute(
            text("EXEC sp_set_session_context @key = N'app_role', @value = :role"),
            {"role": role},
        )
        return fn(session)
