"""Porta features/matching/domain/overlap.ts."""

from __future__ import annotations

from ....shared.scheduling.session_duration import SESSION_DURATION_MINUTES


def _to_minutes(hhmm: str) -> int:
    hours_str, minutes_str = hhmm.split(":")
    return int(hours_str) * 60 + int(minutes_str)


def later_start(a: str, b: str) -> str:
    """Maior horário de início entre duas janelas ("HH:mm" comparável lexicograficamente)."""
    return a if a > b else b


def earlier_end(a: str, b: str) -> str:
    """Menor horário de fim entre duas janelas."""
    return a if a < b else b


def has_minimum_overlap(a_start: str, a_end: str, b_start: str, b_end: str) -> bool:
    """A interseção entre [a_start,a_end) e [b_start,b_end) tem pelo menos
    SESSION_DURATION_MINUTES? É o que define se cabe uma sessão no horário
    em comum entre a disponibilidade do paciente e a do estagiário."""
    start = later_start(a_start, b_start)
    end = earlier_end(a_end, b_end)
    return _to_minutes(end) - _to_minutes(start) >= SESSION_DURATION_MINUTES
