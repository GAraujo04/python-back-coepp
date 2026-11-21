"""Pares que o RunMatching formaria nesta rodada, mas **sem persistir
nada** — usado pela tela de match manual do admin para mostrar a
sugestão do sistema antes de ele escolher outro par. Mesmo algoritmo do
pareamento real (find_all_candidates), só que só de leitura.

Porta features/matching/application/suggest-matches.ts.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime

from ....shared.http.utc_datetime import to_iso_utc
from ....shared.scheduling.weekly_series import period_start_utc
from ..domain.find_candidates import find_all_candidates
from ..infrastructure.sqlalchemy_matching_repository import SqlAlchemyMatchingRepository


@dataclass
class MatchSuggestion:
    patient_id: str
    patient_code: str
    intern_id: str
    intern_name: str
    room_id: str
    room_name: str
    scheduled_at: str  # ISO


class SuggestMatches:
    def __init__(self, repo: SqlAlchemyMatchingRepository) -> None:
        self._repo = repo

    def execute(self, now: datetime | None = None) -> list[MatchSuggestion]:
        now = now if now is not None else datetime.now(UTC).replace(tzinfo=None)
        # Período de atendimentos ainda por começar: a primeira consulta é
        # calculada a partir do início dele, não de hoje.
        period = self._repo.attendance_period()
        if period:
            now = max(now, period_start_utc(period.start))
        patients = self._repo.candidate_patients()
        interns = self._repo.interns_with_windows()
        rooms = self._repo.active_rooms()
        candidates = find_all_candidates(patients, interns, rooms, now, self._repo.reservations())

        patient_by_id = {p.id: p for p in patients}
        intern_by_id = {i.id: i for i in interns}
        room_by_id = {r.id: r for r in rooms}

        return [
            MatchSuggestion(
                patient_id=c.patient_id,
                patient_code=patient_by_id[c.patient_id].code if c.patient_id in patient_by_id else "",
                intern_id=c.intern_id,
                intern_name=intern_by_id[c.intern_id].name if c.intern_id in intern_by_id else "",
                room_id=c.room_id,
                room_name=room_by_id[c.room_id].name if c.room_id in room_by_id else "",
                scheduled_at=to_iso_utc(c.scheduled_at),
            )
            for c in candidates
        ]
