"""O pareamento escolhe a sala conforme a necessidade do paciente."""

from __future__ import annotations

from datetime import datetime

from app.features.matching.domain.find_candidates import PersonWithWindows, RoomOption, WindowSlot, find_all_candidates
from app.shared.scheduling.room_category import RoomCategory

NOW = datetime(2026, 10, 5, 12, 0)  # segunda-feira, naive-UTC
WINDOW = [WindowSlot(weekday=3, start_time="14:00", end_time="16:00")]
ROOMS = [
    RoomOption(id="sala-1", name="Sala 1", category="PADRAO"),
    RoomOption(id="sala-2", name="Sala 2", category="ACESSIVEL"),
    RoomOption(id="sala-3", name="Sala 3", category="INFANTIL"),
]


def _match_room(preferred: RoomCategory | None) -> str:
    patient = PersonWithWindows(id="p", name="P", windows=WINDOW, preferred_room_category=preferred)
    intern = PersonWithWindows(id="i", name="I", windows=WINDOW)
    [candidate] = find_all_candidates([patient], [intern], ROOMS, NOW)
    return candidate.room_id


def test_paciente_pcd_vai_para_sala_adaptada() -> None:
    assert _match_room("ACESSIVEL") == "sala-2"


def test_crianca_vai_para_sala_infantil() -> None:
    assert _match_room("INFANTIL") == "sala-3"


def test_sem_necessidade_fica_na_sala_padrao() -> None:
    assert _match_room(None) == "sala-1"


def test_sem_sala_da_categoria_usa_outra_livre() -> None:
    patient = PersonWithWindows(id="p", name="P", windows=WINDOW, preferred_room_category="ACESSIVEL")
    intern = PersonWithWindows(id="i", name="I", windows=WINDOW)
    [candidate] = find_all_candidates([patient], [intern], [ROOMS[0]], NOW)
    assert candidate.room_id == "sala-1"


def test_horario_de_proposta_em_aberto_nao_e_proposto_de_novo() -> None:
    from app.features.matching.domain.find_candidates import Reservation

    patient = PersonWithWindows(id="p", name="P", windows=WINDOW)
    intern = PersonWithWindows(id="i", name="I", windows=WINDOW)
    [livre] = find_all_candidates([patient], [intern], ROOMS, NOW)
    # O mesmo estagiário já está proposto nesse horário para outro paciente.
    reservado = Reservation(intern_id="i", room_id="sala-1", scheduled_at=livre.scheduled_at)
    assert find_all_candidates([patient], [intern], ROOMS, NOW, [reservado]) == []


def test_sem_sala_nao_ha_candidato() -> None:
    patient = PersonWithWindows(id="p", name="P", windows=WINDOW)
    intern = PersonWithWindows(id="i", name="I", windows=WINDOW)
    assert find_all_candidates([patient], [intern], [], NOW) == []
