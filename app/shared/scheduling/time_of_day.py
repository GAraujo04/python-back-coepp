"""Formata um datetime como "HH:mm" no fuso local do processo.

Porta shared/scheduling/time-of-day.ts.
"""

from __future__ import annotations

from datetime import datetime


def to_hhmm(dt: datetime) -> str:
    return f"{dt.hour:02d}:{dt.minute:02d}"
