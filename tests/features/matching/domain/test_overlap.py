"""Duração: o paciente precisa da consulta (50 min); o estagiário, da
consulta + 10 min para organizar a sala (1 h)."""

from __future__ import annotations

from app.features.matching.domain.overlap import has_minimum_overlap


def test_caso_da_tela_segunda_feira_encaixa() -> None:
    # Paciente 18:30–20:30, estagiário 13:00–20:30.
    assert has_minimum_overlap("18:30", "20:30", "13:00", "20:30")


def test_paciente_precisa_so_dos_50_minutos() -> None:
    assert has_minimum_overlap("18:30", "19:20", "13:00", "20:30")
    assert not has_minimum_overlap("18:30", "19:19", "13:00", "20:30")


def test_estagiario_precisa_da_hora_cheia() -> None:
    assert has_minimum_overlap("18:30", "20:30", "13:00", "19:30")
    # 50 min livres no estagiário não bastam: falta o intervalo da sala.
    assert not has_minimum_overlap("18:30", "20:30", "13:00", "19:20")
