"""Gera o código do paciente (AAAA + sequencial de 4 dígitos, ex.:
20260001), de forma atômica dentro da transação.

Porta shared/db/patient-code.ts.
"""

from __future__ import annotations

from datetime import datetime

from sqlalchemy.orm import Session

from .atomic_counter import next_counter_value


def next_patient_code(session: Session) -> str:
    year = datetime.now().year
    seq = next_counter_value(session, "patient_counters", year)
    return f"{year}{seq:04d}"
