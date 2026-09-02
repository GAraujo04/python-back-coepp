"""Validação de janelas de disponibilidade semanal (paciente OU estagiário
— o conceito é o mesmo pros dois, por isso vive em shared/ em vez de
duplicado em cada slice, evitando que as regras divirjam).

Porta shared/scheduling/availability-window.ts.
"""

from __future__ import annotations

import re
from dataclasses import dataclass

from ..errors.app_error import ValidationError

# "HH:mm", 24h, zero-padded (mesmo formato produzido por <input type="time">).
_TIME_RE = re.compile(r"^([01]\d|2[0-3]):([0-5]\d)$")


@dataclass
class AvailabilityWindowInput:
    weekday: int  # 0=domingo .. 6=sábado
    start_time: str  # "HH:mm"
    end_time: str  # "HH:mm"


def validate_availability_windows(windows: list[AvailabilityWindowInput] | None, label: str) -> None:
    """Regras: pelo menos uma janela; horário no formato HH:mm; fim >
    início; sem sobreposição de janelas no mesmo dia da semana."""
    if not windows:
        raise ValidationError(f"Informe ao menos uma janela de disponibilidade ({label}).")

    by_weekday: dict[int, list[AvailabilityWindowInput]] = {}
    for w in windows:
        if not isinstance(w.weekday, int) or w.weekday < 0 or w.weekday > 6:
            raise ValidationError(f"Dia da semana inválido ({label}): {w.weekday}.")
        if not _TIME_RE.match(w.start_time) or not _TIME_RE.match(w.end_time):
            raise ValidationError(f"Horário inválido ({label}) — use o formato HH:mm.")
        if w.end_time <= w.start_time:
            raise ValidationError(f"O horário final deve ser depois do inicial ({label}).")
        by_weekday.setdefault(w.weekday, []).append(w)

    for group in by_weekday.values():
        sorted_group = sorted(group, key=lambda w: w.start_time)
        for prev, curr in zip(sorted_group, sorted_group[1:], strict=False):
            if curr.start_time < prev.end_time:
                raise ValidationError(f"Janelas de disponibilidade sobrepostas no mesmo dia ({label}).")
