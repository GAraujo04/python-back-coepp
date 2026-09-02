"""Tipo Pydantic pra serializar datetime como ISO-UTC com `Z` — mesmo
formato que `Date.prototype.toISOString()` produz no Node
(`scheduledAt.toISOString()` em appointments/presentation/routes.ts, e
equivalentes nas outras slices).

Todo datetime armazenado neste projeto é *naive* (sem tzinfo) representando
UTC — decisão tomada na slice auth por causa do SQL Server/pyodbc (ver
shared/db/models.py e sqlalchemy_refresh_token_store.py). Sem este tipo, o
Pydantic serializaria um datetime naive como `"2026-09-02T10:00:00"` (sem
sufixo de fuso) — o `new Date(...)` do JavaScript interpreta uma string
ISO SEM fuso como HORÁRIO LOCAL do navegador, não UTC, deslocando todo
horário exibido pela diferença de fuso. Usar em todo campo de
data/hora exposto num schema de resposta.
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from typing import Annotated

from pydantic import PlainSerializer


def _to_iso_utc(dt: datetime) -> str:
    # Node's Date.prototype.toISOString() sempre usa 3 casas decimais
    # (milissegundos) — Python's isoformat() usa 6 (microssegundos) quando
    # o valor não é exatamente redondo. Arredonda pra milissegundos antes
    # de formatar, pra bater exatamente com o que o Fastify já produz.
    millis = round(dt.microsecond / 1000)
    rounded = dt.replace(microsecond=0, tzinfo=UTC) + timedelta(milliseconds=millis)
    return rounded.isoformat(timespec="milliseconds").replace("+00:00", "Z")


UtcDatetime = Annotated[datetime, PlainSerializer(_to_iso_utc, return_type=str)]
