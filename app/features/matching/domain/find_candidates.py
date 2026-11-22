"""Porta features/matching/domain/find-candidates.ts."""

from __future__ import annotations

from collections.abc import Iterable
from dataclasses import dataclass, field
from datetime import datetime

from ....shared.scheduling.next_occurrence import next_occurrence
from ....shared.scheduling.room_category import DEFAULT_ROOM_CATEGORY, RoomCategory, rank_rooms_for
from .overlap import has_minimum_overlap, later_start


@dataclass
class WindowSlot:
    weekday: int
    start_time: str
    end_time: str


@dataclass
class PersonWithWindows:
    id: str
    name: str
    windows: list[WindowSlot] = field(default_factory=list)
    # Só faz sentido para paciente (ver room_category.preferred_room_category).
    preferred_room_category: RoomCategory | None = None
    # Só paciente: o número que identifica o paciente nas telas do administrativo.
    code: str = ""


@dataclass
class RoomOption:
    id: str
    name: str
    category: str = DEFAULT_ROOM_CATEGORY


@dataclass
class Reservation:
    """Horário já tomado por uma proposta em aberto: não pode ser proposto de novo."""

    intern_id: str
    room_id: str | None
    scheduled_at: datetime


@dataclass
class Candidate:
    patient_id: str
    intern_id: str
    room_id: str
    scheduled_at: datetime


def find_all_candidates(
    patients: list[PersonWithWindows],
    interns: list[PersonWithWindows],
    rooms: list[RoomOption],
    now: datetime,
    reserved: Iterable[Reservation] = (),
) -> list[Candidate]:
    """Busca todos os pares (paciente, estagiário, sala, horário) válidos
    nesta "rodada": mesmo dia da semana, sobreposição >= duração da sessão,
    sala livre, sem reutilizar sala/estagiário no mesmo instante dentro da
    própria rodada nem os de `reserved` (propostas ainda em aberto). Função pura — usada tanto pelo pareamento real
    (RunMatching, que persiste) quanto pela sugestão somente-leitura
    (SuggestMatches), para as duas nunca divergirem."""
    matched_patients: set[str] = set()
    intern_busy: set[str] = set()  # f"{intern_id}|{iso_datetime}"
    room_busy: set[str] = set()  # f"{room_id}|{iso_datetime}"
    for r in reserved:
        intern_busy.add(f"{r.intern_id}|{r.scheduled_at.isoformat()}")
        if r.room_id:
            room_busy.add(f"{r.room_id}|{r.scheduled_at.isoformat()}")
    results: list[Candidate] = []

    for patient in patients:
        if patient.id in matched_patients:
            continue
        candidate = _find_candidate(patient, interns, rooms, intern_busy, room_busy, now)
        if not candidate:
            continue

        key = candidate.scheduled_at.isoformat()
        matched_patients.add(candidate.patient_id)
        intern_busy.add(f"{candidate.intern_id}|{key}")
        room_busy.add(f"{candidate.room_id}|{key}")
        results.append(candidate)

    return results


def _find_candidate(
    patient: PersonWithWindows,
    interns: list[PersonWithWindows],
    rooms: list[RoomOption],
    intern_busy: set[str],
    room_busy: set[str],
    now: datetime,
) -> Candidate | None:
    rooms = rank_rooms_for(rooms, patient.preferred_room_category)
    for intern in interns:
        for patient_window in patient.windows:
            for intern_window in intern.windows:
                scheduled_at = _candidate_time(patient_window, intern_window, now)
                if not scheduled_at:
                    continue

                key = scheduled_at.isoformat()
                if f"{intern.id}|{key}" in intern_busy:
                    continue

                room = next((r for r in rooms if f"{r.id}|{key}" not in room_busy), None)
                if not room:
                    continue

                return Candidate(patient_id=patient.id, intern_id=intern.id, room_id=room.id, scheduled_at=scheduled_at)
    return None


def _candidate_time(patient: WindowSlot, intern: WindowSlot, now: datetime) -> datetime | None:
    if patient.weekday != intern.weekday:
        return None
    if not has_minimum_overlap(patient.start_time, patient.end_time, intern.start_time, intern.end_time):
        return None
    return next_occurrence(patient.weekday, later_start(patient.start_time, intern.start_time), now)
