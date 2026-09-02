"""Formata um instante como "HH:mm" no fuso LOCAL do processo (inverso de
next_occurrence) e converte pro dia da semana na mesma convenção do JS.

Porta shared/scheduling/time-of-day.ts. Diferença de implementação (não
de comportamento): o TS recebe um `Date` já com getters locais; aqui o
valor de entrada é naive-UTC (convenção do projeto para tudo que
transita pelo banco — ver next_occurrence.py para o porquê, confirmado
empiricamente), então a conversão UTC→local é feita aqui dentro.
"""

from __future__ import annotations

from datetime import UTC, datetime


def to_local(dt_utc: datetime) -> datetime:
    """Converte um datetime naive-UTC pro fuso LOCAL do processo/SO
    (aware) — mesmo mecanismo usado por next_occurrence.py, exposto aqui
    pra não duplicar a conversão em cada chamador."""
    return dt_utc.replace(tzinfo=UTC).astimezone()


def to_hhmm(dt_utc: datetime) -> str:
    local = to_local(dt_utc)
    return f"{local.hour:02d}:{local.minute:02d}"


def js_weekday(dt_utc: datetime) -> int:
    """0=domingo..6=sábado (Date.getDay() do JS), no fuso LOCAL, a partir
    de um instante naive-UTC."""
    local = to_local(dt_utc)
    return (local.weekday() + 1) % 7
