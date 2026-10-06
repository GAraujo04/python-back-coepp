"""Categoria de sala de atendimento e a preferência de sala por paciente.

Em shared/ porque é usada por duas slices: rooms (cadastro) e matching
(escolha da sala no pareamento) — mesmo motivo de room_conflict.py.

A categoria existe para casar a sala com a necessidade do atendimento:
paciente com deficiência vai para sala adaptada, criança para a sala
infantil. É PREFERÊNCIA, não exigência — sem sala da categoria livre no
horário, o pareamento usa outra sala livre em vez de deixar o paciente sem
atendimento (decisão de produto: quem escolhe recusar é o administrativo,
na realocação manual).
"""

from __future__ import annotations

from typing import Literal, Protocol, get_args

RoomCategory = Literal["PADRAO", "ACESSIVEL", "INFANTIL", "GRUPO"]
ROOM_CATEGORIES: tuple[RoomCategory, ...] = get_args(RoomCategory)

# Sala sem categoria informada (as 11 salas originais, inclusive) é padrão.
DEFAULT_ROOM_CATEGORY: RoomCategory = "PADRAO"


def preferred_room_category(has_disability: bool, is_minor: bool) -> RoomCategory | None:
    """Categoria que o atendimento deste paciente pede, se alguma.
    Deficiência vem antes da idade: uma criança com deficiência precisa
    primeiro da sala adaptada (acessibilidade é barreira; a sala infantil
    é conforto)."""
    if has_disability:
        return "ACESSIVEL"
    if is_minor:
        return "INFANTIL"
    return None


class _HasCategory(Protocol):
    category: str


def rank_rooms_for[R: _HasCategory](rooms: list[R], preferred: RoomCategory | None) -> list[R]:
    """Ordena as salas para a busca da primeira livre: as da categoria
    preferida primeiro, depois as padrão, depois as demais. Quem não tem
    preferência começa pelas padrão — assim uma sala adaptada ou infantil
    só é ocupada por quem não precisa dela quando não sobrou outra.

    `sorted` é estável: dentro de cada faixa, a ordem de entrada (por nome)
    se mantém. Com todas as salas padrão — o banco antes desta categoria
    existir — a ordem resultante é exatamente a de entrada."""

    def rank(room: R) -> int:
        if preferred and room.category == preferred:
            return 0
        if room.category == DEFAULT_ROOM_CATEGORY:
            return 1
        return 2

    return sorted(rooms, key=rank)
