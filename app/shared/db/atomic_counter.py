"""Incrementa atomicamente o contador do ano em `table` e devolve o novo
valor. Usado tanto pelo código do paciente (next_patient_code) quanto pelo
Nº dos documentos clínicos — mesmo padrão, tabelas diferentes.

Porta shared/db/atomic-counter.ts. sp_getapplock (via with_app_lock)
serializa as chamadas pra um dado (table, year); dentro da seção crítica,
um UPDATE...OUTPUT tenta incrementar a linha existente, e só faz
INSERT...OUTPUT se não havia linha pro ano ainda.
"""

from __future__ import annotations

from typing import Literal

from sqlalchemy import text
from sqlalchemy.orm import Session

from .applock import with_app_lock

CounterTable = Literal["patient_counters", "document_counters"]


def next_counter_value(session: Session, table: CounterTable, year: int) -> int:
    def _do() -> int:
        # `table` é um Literal fechado (não vem de input do usuário) — seguro
        # interpolar no SQL, já que identificadores de tabela não são
        # parametrizáveis via placeholder no T-SQL.
        updated = session.execute(
            text(f"UPDATE {table} SET last_value = last_value + 1 OUTPUT INSERTED.last_value WHERE year = :year"),
            {"year": year},
        ).first()
        if updated:
            return int(updated[0])
        inserted = session.execute(
            text(f"INSERT INTO {table} (year, last_value) OUTPUT INSERTED.last_value VALUES (:year, 1)"),
            {"year": year},
        ).first()
        if not inserted:
            raise RuntimeError(
                f"Falha ao inicializar o contador {table} para o ano {year} (INSERT não retornou linha)."
            )
        return int(inserted[0])

    return with_app_lock(session, f"{table}:{year}", _do)
