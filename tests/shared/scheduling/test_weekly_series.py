"""Série semanal dentro do período, sempre no mesmo horário local."""

from __future__ import annotations

from datetime import date, datetime, timedelta

from app.shared.scheduling.time_of_day import js_weekday, to_hhmm, to_local
from app.shared.scheduling.weekly_series import MAX_OCCURRENCES, period_start_utc, weekly_occurrences


def _anchor(day: date, hour: int = 14) -> datetime:
    """Naive-UTC correspondente a `day` às `hour`h no fuso local."""
    from datetime import UTC

    return datetime(day.year, day.month, day.day, hour).astimezone().astimezone(UTC).replace(tzinfo=None)


def test_mesmo_dia_e_horario_toda_semana_ate_o_fim_inclusivo() -> None:
    anchor = _anchor(date(2026, 10, 6))  # terça
    series = weekly_occurrences(anchor, date(2026, 10, 1), date(2026, 10, 27), not_before=anchor)
    assert [to_local(s).date() for s in series] == [date(2026, 10, 13), date(2026, 10, 20), date(2026, 10, 27)]
    assert {js_weekday(s) for s in series} == {js_weekday(anchor)}
    assert {to_hhmm(s) for s in series} == {to_hhmm(anchor)}


def test_ancora_antes_do_periodo_entra_na_primeira_semana_dele() -> None:
    anchor = _anchor(date(2026, 3, 3))  # terça, meses antes
    series = weekly_occurrences(anchor, date(2026, 10, 1), date(2026, 10, 10), not_before=anchor)
    assert [to_local(s).date() for s in series] == [date(2026, 10, 6)]


def test_nao_repete_o_que_ja_passou() -> None:
    anchor = _anchor(date(2026, 10, 6))
    not_before = anchor + timedelta(days=8)
    series = weekly_occurrences(anchor, date(2026, 10, 1), date(2026, 10, 27), not_before=not_before)
    assert [to_local(s).date() for s in series] == [date(2026, 10, 20), date(2026, 10, 27)]


def test_periodo_encerrado_nao_gera_nada() -> None:
    anchor = _anchor(date(2026, 10, 6))
    assert weekly_occurrences(anchor, date(2026, 1, 1), date(2026, 6, 30), not_before=anchor) == []


def test_teto_de_ocorrencias() -> None:
    anchor = _anchor(date(2026, 1, 6))
    series = weekly_occurrences(anchor, date(2026, 1, 1), date(2030, 1, 1), not_before=datetime(2000, 1, 1))
    assert len(series) == MAX_OCCURRENCES


def test_inicio_do_periodo_e_meia_noite_local() -> None:
    start = period_start_utc(date(2026, 10, 1))
    assert to_local(start).date() == date(2026, 10, 1)
    assert to_hhmm(start) == "00:00"
