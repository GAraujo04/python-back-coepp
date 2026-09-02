"""Porta features/matching/domain/find-nearest-fallback.ts."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime

from ....shared.scheduling.next_occurrence import next_occurrence
from .find_candidates import PersonWithWindows

_MINUTES_PER_WEEK = 7 * 24 * 60


@dataclass
class FallbackSuggestion:
    patient_id: str
    intern_id: str
    suggested_at: datetime


def _week_minute(weekday: int, hhmm: str) -> int:
    hours_str, minutes_str = hhmm.split(":")
    return weekday * 1440 + int(hours_str) * 60 + int(minutes_str)


def _circular_distance(a: int, b: int) -> int:
    """Distância circular na semana (a semana "dá a volta" — sábado à
    noite está perto de domingo de manhã)."""
    diff = abs(a - b) % _MINUTES_PER_WEEK
    return min(diff, _MINUTES_PER_WEEK - diff)


def find_nearest_fallback(
    patient: PersonWithWindows, interns: list[PersonWithWindows], now: datetime
) -> FallbackSuggestion | None:
    """Quando RunMatching não acha nenhum estagiário com sobreposição de
    horário suficiente pro paciente (item 5, fallback por aproximação),
    busca o estagiário/janela mais PRÓXIMO no tempo — menor distância
    circular entre o início da janela do paciente e o início da janela do
    estagiário. Não garante nenhum overlap de duração — é só a sugestão
    mais parecida disponível, pra alguém da equipe negociar manualmente
    com o paciente. Função pura, sem acesso a banco — mesma convenção de
    find_candidates.py."""
    best: tuple[str, datetime, int] | None = None  # (intern_id, suggested_at, distance)

    for patient_window in patient.windows:
        patient_minute = _week_minute(patient_window.weekday, patient_window.start_time)
        for intern in interns:
            for intern_window in intern.windows:
                intern_minute = _week_minute(intern_window.weekday, intern_window.start_time)
                distance = _circular_distance(patient_minute, intern_minute)
                if best is None or distance < best[2]:
                    best = (
                        intern.id,
                        next_occurrence(intern_window.weekday, intern_window.start_time, now),
                        distance,
                    )

    if best is None:
        return None
    return FallbackSuggestion(patient_id=patient.id, intern_id=best[0], suggested_at=best[1])
