"""Converte um dia da semana + horário recorrente ("HH:mm") na próxima
data/hora concreta a partir de `now` (pode ser hoje, se o horário ainda
não tiver passado). Usa o fuso horário LOCAL do processo — o sistema não
tem uma configuração de fuso "da clínica" hoje (mesma simplificação já
assumida no original).

Porta shared/scheduling/next-occurrence.ts. Duas diferenças de
implementação, NÃO de comportamento (ambas exigidas pela ausência, em
Python, do "Date é sempre um instante absoluto com getters locais" do
JS):

1. Convenção de dia da semana: `weekday` aqui é 0=domingo..6=sábado
   (igual ao `Date.getDay()`), NÃO o `date.weekday()` do Python
   (0=segunda..6=domingo) — a conversão vem de time_of_day.js_weekday().

2. Conversão de fuso EXPLÍCITA. O TS usa `new Date(); result.setHours(...)`
   — como `Date` é internamente um instante UTC com getters/setters que
   operam no fuso LOCAL do processo, o resultado "parece" hora local mas
   é, na verdade, o instante UTC correspondente. Quando o Prisma grava
   esse `Date` numa coluna DATETIME2 (sem timezone), o driver mssql
   CONVERTE pra UTC antes de escrever — confirmado empiricamente: um
   `Date` construído com `setHours(14, 30)` às 11h59 em São Paulo
   (UTC-3) foi lido de volta do banco, via `SELECT CONVERT(...)` cru,
   como `17:30:00` (14:30 − (−3h) = 17:30 UTC). Ou seja, o "HH:mm" da
   janela de disponibilidade é hora LOCAL da clínica, mas o valor
   persistido é UTC. Python não tem essa conversão automática embutida
   num tipo naive — por isso aqui ela é feita à mão: `now` recebido é
   naive-UTC (convenção do projeto para todo datetime que entra/sai do
   banco), convertido pra hora local só para o cálculo de
   dia-da-semana/horário, e o resultado é convertido de volta pra
   naive-UTC antes de retornar (é isso que acaba gravado em
   Appointment.scheduled_at).
"""

from __future__ import annotations

from datetime import UTC, timedelta
from datetime import datetime as _datetime

from .time_of_day import js_weekday, to_local


def next_occurrence(weekday: int, time_hhmm: str, now: _datetime) -> _datetime:
    """`now`: naive, representando o instante atual em UTC (convenção do
    projeto). Retorna um datetime também naive-UTC, pronto pra persistir
    direto num campo do banco."""
    now_local = to_local(now)

    hours_str, minutes_str = time_hhmm.split(":")
    hours, minutes = int(hours_str), int(minutes_str)
    result_local = now_local.replace(hour=hours, minute=minutes, second=0, microsecond=0)

    days_until = weekday - js_weekday(now)
    if days_until < 0:
        days_until += 7
    if days_until == 0 and result_local <= now_local:
        days_until = 7  # hoje, mas já passou
    result_local += timedelta(days=days_until)

    return result_local.astimezone(UTC).replace(tzinfo=None)
