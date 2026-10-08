"""Contagem do sininho: pendências pela quantidade, informativos até serem vistos."""

from __future__ import annotations

from datetime import datetime, timedelta

from app.features.notifications.domain.notification import Notification, sort_for_display, unread_count

T0 = datetime(2026, 10, 8, 12, 0)


def test_pendencias_contam_pela_quantidade_e_nunca_ficam_vistas() -> None:
    items = [Notification(kind="REVIEW_QUEUE", actionable=True, at=T0, count=12)]
    assert unread_count(items, seen_at=None) == 12
    assert unread_count(items, seen_at=T0 + timedelta(days=1)) == 12


def test_informativo_conta_ate_ser_visto() -> None:
    items = [Notification(kind="DOCUMENT_APPROVED", actionable=False, at=T0)]
    assert unread_count(items, seen_at=None) == 1
    assert unread_count(items, seen_at=T0 - timedelta(minutes=1)) == 1
    assert unread_count(items, seen_at=T0) == 0


def test_pendencias_primeiro_e_mais_recentes_no_topo() -> None:
    old_info = Notification(kind="DOCUMENT_APPROVED", actionable=False, at=T0)
    new_info = Notification(kind="DOCUMENT_REJECTED", actionable=False, at=T0 + timedelta(hours=1))
    task = Notification(kind="CHANGES_REQUESTED", actionable=True, at=T0 - timedelta(days=3))
    assert sort_for_display([old_info, task, new_info]) == [task, new_info, old_info]
