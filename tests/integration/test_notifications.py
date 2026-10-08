"""Avisos por papel, com os mesmos escopos das telas."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

from sqlalchemy.orm import Session

from app.features.notifications.domain.notification import unread_count
from app.features.notifications.infrastructure.sqlalchemy_notification_source import SqlAlchemyNotificationSource
from app.shared.db.session import with_rls_context

from .conftest import World


def _now() -> datetime:
    return datetime.now(UTC).replace(tzinfo=None)


def _kinds(db: Session, user_id: str, role: str) -> dict[str, int]:
    return {n.kind: n.count for n in SqlAlchemyNotificationSource(db).for_user(user_id, role, _now())}


def test_fila_avisa_so_o_supervisor_do_paciente(db: Session, world: World) -> None:
    assert _kinds(db, world.sup_a.id, "SUPERVISOR").get("REVIEW_QUEUE", 0) >= 1
    own = SqlAlchemyNotificationSource(db).for_user(world.sup_b.id, "SUPERVISOR", _now())
    assert all(n.kind != "REVIEW_QUEUE" for n in own)


def _set_status(db: Session, w: World, status: str) -> None:
    def _do(s: Session) -> None:
        w.doc.status = status
        w.doc.updated_at = _now()
        s.flush()

    with_rls_context(db, w.admin.id, "ADMIN", _do)


def test_estagiario_ve_ajustes_e_aprovacao(db: Session, world: World) -> None:
    _set_status(db, world, "REVISAO_SOLICITADA")
    assert "CHANGES_REQUESTED" in _kinds(db, world.intern.id, "INTERN")
    # Outro estagiário não é avisado sobre o documento que não é dele.
    assert "CHANGES_REQUESTED" not in _kinds(db, world.other_intern.id, "INTERN")

    _set_status(db, world, "APROVADO_LOCKED")
    source = SqlAlchemyNotificationSource(db)
    items = source.for_user(world.intern.id, "INTERN", _now())
    assert [n.kind for n in items] == ["DOCUMENT_APPROVED"]
    assert unread_count(items, source.seen_at(world.intern.id)) == 1
    source.mark_seen(world.intern.id, _now() + timedelta(seconds=1))
    assert unread_count(items, source.seen_at(world.intern.id)) == 0


def test_admin_ve_vinculo_sem_supervisor(db: Session, world: World) -> None:
    before = _kinds(db, world.admin.id, "ADMIN").get("ASSIGNMENTS_WITHOUT_SUPERVISOR", 0)
    from app.shared.db.models import Assignment

    db.add(Assignment(patient_id=world.patient.id, intern_id=world.other_intern.id, supervisor_id=None))
    db.flush()
    assert _kinds(db, world.admin.id, "ADMIN")["ASSIGNMENTS_WITHOUT_SUPERVISOR"] == before + 1
