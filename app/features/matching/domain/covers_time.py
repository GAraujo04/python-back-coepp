"""Porta features/matching/domain/covers-time.ts."""

from __future__ import annotations

from .find_candidates import WindowSlot


def covers_time(windows: list[WindowSlot], weekday: int, hhmm: str) -> bool:
    """A pessoa informou alguma janela de disponibilidade que cobre este dia/horário?"""
    return any(w.weekday == weekday and w.start_time <= hhmm < w.end_time for w in windows)
