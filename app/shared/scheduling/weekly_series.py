"""Série semanal de consultas dentro do período de atendimentos.

Toda consulta de um par paciente↔estagiário acontece no MESMO dia da
semana e horário da primeira. As datas avançam de 7 em 7 dias no horário
LOCAL da clínica (não em UTC): se o fuso tiver horário de verão, "toda
terça às 14h" continua às 14h na parede — mesma convenção de
next_occurrence.py, cujo resultado é o ponto de partida daqui.

Funções puras: recebem e devolvem datetimes naive-UTC (convenção do
projeto para o que vai ao banco); `start`/`end` são datas do calendário
local, inclusivas.
"""

from __future__ import annotations

from datetime import UTC, date, datetime, timedelta

from .time_of_day import to_local

# Teto de segurança: um período mal digitado (ano errado) não pode gerar
# centenas de consultas. O período em si já é limitado a 1 ano.
MAX_OCCURRENCES = 60


def _to_utc(local: datetime) -> datetime:
    return local.astimezone(UTC).replace(tzinfo=None)


def weekly_occurrences(anchor: datetime, start: date, end: date, not_before: datetime) -> list[datetime]:
    """Ocorrências semanais do horário de `anchor` dentro de [start, end] e
    estritamente depois de `not_before` (naive-UTC). `anchor` dá o dia da
    semana e a hora; pode estar antes do período (consulta de um par
    formado antes de o período ser configurado) — a série anda de semana
    em semana até entrar nele."""
    local = to_local(anchor)
    # Pula semanas inteiras até a primeira ocorrência >= start (sem laço
    # longo para âncoras antigas).
    if local.date() < start:
        weeks = -(-(start - local.date()).days // 7)  # teto
        local = (local.replace(tzinfo=None) + timedelta(weeks=weeks)).astimezone()
    out: list[datetime] = []
    while local.date() <= end and len(out) < MAX_OCCURRENCES:
        utc = _to_utc(local)
        if utc > not_before:
            out.append(utc)
        # Soma na hora de parede e só então reconverte: preserva "14h".
        local = (local.replace(tzinfo=None) + timedelta(weeks=1)).astimezone()
    return out


def period_start_utc(start: date) -> datetime:
    """Meia-noite local do primeiro dia do período, em naive-UTC — o
    "agora" mínimo para o pareamento calcular a primeira consulta."""
    return _to_utc(datetime(start.year, start.month, start.day).astimezone())
