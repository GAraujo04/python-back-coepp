"""Consultas que dependem do SQL Server e da RLS — fakes não as cobrem."""

from __future__ import annotations

from sqlalchemy.orm import Session

from app.features.enrollment.infrastructure.sqlalchemy_availability_lock_repository import (
    SqlAlchemyAvailabilityLockRepository,
)
from app.features.screening.domain.screening_repository import AccessContext
from app.features.screening.infrastructure.sqlalchemy_screening_repository import SqlAlchemyScreeningRepository

from .conftest import World, make_patient


def test_responsavel_pela_disponibilidade(db: Session, world: World) -> None:
    # Regressão: a 1ª versão usava SELECT EXISTS(...) OR EXISTS(...), que o
    # SQL Server recusa — os testes com fake passavam.
    repo = SqlAlchemyAvailabilityLockRepository(db)
    assert repo.is_responsible(world.sup_a.id, world.intern.id)
    assert not repo.is_responsible(world.sup_b.id, world.intern.id)


def test_triagem_de_outro_estagiario_conta(db: Session, world: World) -> None:
    repo = SqlAlchemyScreeningRepository(db)
    other = AccessContext(world.other_intern.id, "INTERN")
    # O outro estagiário não ENXERGA a triagem (RLS)…
    assert repo.find_by_id(other, world.doc.id) is None
    # …mas a regra de triagem única a encontra mesmo assim.
    assert repo.patient_has_screening(other, world.patient.id)
    assert not repo.patient_has_screening(other, make_patient(db).id)


def test_estagiario_ve_so_os_proprios_documentos(db: Session, world: World) -> None:
    repo = SqlAlchemyScreeningRepository(db)
    assert world.doc.id in {d.id for d in repo.list_for_actor(AccessContext(world.intern.id, "INTERN"))}
    assert world.doc.id not in {d.id for d in repo.list_for_actor(AccessContext(world.other_intern.id, "INTERN"))}
