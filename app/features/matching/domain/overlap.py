"""Porta features/matching/domain/overlap.ts."""

from __future__ import annotations

from ....shared.scheduling.session_duration import SESSION_DURATION_MINUTES, SLOT_MINUTES


def _to_minutes(hhmm: str) -> int:
    hours_str, minutes_str = hhmm.split(":")
    return int(hours_str) * 60 + int(minutes_str)


def later_start(a: str, b: str) -> str:
    """Maior horário de início entre duas janelas ("HH:mm" comparável lexicograficamente)."""
    return a if a > b else b


def earlier_end(a: str, b: str) -> str:
    """Menor horário de fim entre duas janelas."""
    return a if a < b else b


def has_minimum_overlap(patient_start: str, patient_end: str, intern_start: str, intern_end: str) -> bool:
    """Cabe uma sessão no horário em comum, começando no maior dos inícios?
    O paciente precisa da consulta (SESSION_DURATION_MINUTES); o estagiário,
    da consulta + o intervalo para organizar a sala (SLOT_MINUTES)."""
    start = _to_minutes(later_start(patient_start, intern_start))
    return start + SESSION_DURATION_MINUTES <= _to_minutes(patient_end) and start + SLOT_MINUTES <= _to_minutes(
        intern_end
    )
