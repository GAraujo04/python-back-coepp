"""Preferência de sala por necessidade do paciente."""

from __future__ import annotations

from dataclasses import dataclass

from app.shared.scheduling.room_category import preferred_room_category, rank_rooms_for


@dataclass
class R:
    id: str
    category: str


def test_deficiencia_vem_antes_da_idade() -> None:
    assert preferred_room_category(has_disability=True, is_minor=True) == "ACESSIVEL"
    assert preferred_room_category(has_disability=False, is_minor=True) == "INFANTIL"
    assert preferred_room_category(has_disability=False, is_minor=False) is None


def test_categoria_preferida_primeiro_depois_padrao() -> None:
    rooms = [R("1", "INFANTIL"), R("2", "PADRAO"), R("3", "ACESSIVEL"), R("4", "PADRAO")]
    assert [r.id for r in rank_rooms_for(rooms, "ACESSIVEL")] == ["3", "2", "4", "1"]


def test_sem_preferencia_poupa_salas_especiais() -> None:
    rooms = [R("1", "INFANTIL"), R("2", "PADRAO"), R("3", "ACESSIVEL")]
    assert [r.id for r in rank_rooms_for(rooms, None)] == ["2", "1", "3"]


def test_todas_padrao_mantem_a_ordem_de_entrada() -> None:
    # O banco antes da migration 0004: comportamento idêntico ao anterior.
    rooms = [R(str(i), "PADRAO") for i in range(5)]
    assert rank_rooms_for(rooms, "ACESSIVEL") == rooms
