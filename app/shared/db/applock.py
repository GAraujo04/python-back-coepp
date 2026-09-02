"""Lock de aplicação nomeado (sp_getapplock), escopado à transação.

Porta shared/db/applock.ts. Usado nos contadores sequenciais e na trilha
de auditoria pra serializar sequências check-then-act que, sem lock,
teriam corrida — mesmo motivo do TS (MERGE tem corrida documentada pela
própria Microsoft sob concorrência).
"""

from __future__ import annotations

from collections.abc import Callable

from sqlalchemy import text
from sqlalchemy.orm import Session

DEFAULT_LOCK_TIMEOUT_MS = 30_000


def with_app_lock[T](session: Session, resource: str, fn: Callable[[], T]) -> T:
    result = session.execute(
        text(
            "DECLARE @rc INT;"
            "EXEC @rc = sp_getapplock @Resource = :resource, @LockMode = N'Exclusive', "
            "@LockOwner = N'Transaction', @LockTimeout = :timeout;"
            "SELECT @rc AS result;"
        ),
        {"resource": resource, "timeout": DEFAULT_LOCK_TIMEOUT_MS},
    ).scalar()
    if result is None or result < 0:
        raise RuntimeError(f'Não foi possível obter o lock "{resource}" (sp_getapplock retornou {result}).')
    return fn()
