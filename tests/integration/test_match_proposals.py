"""Proposta de pareamento: salvar cria o vínculo; cancelar não deixa nada."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

import pytest
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.features.matching.application.match_proposals import (
    ConfirmMatchProposal,
    ConfirmProposalInput,
    DiscardMatchProposal,
)
from app.features.matching.infrastructure.sqlalchemy_matching_repository import NewMatch, SqlAlchemyMatchingRepository
from app.shared.audit.audit_recorder import AuditEvent, AuditRecorder
from app.shared.db.models import Assignment
from app.shared.errors.app_error import ConflictError

from .conftest import World, make_patient


class NoAudit(AuditRecorder):
    def record(self, event: AuditEvent) -> None:
        pass


def _future() -> datetime:
    return datetime.now(UTC).replace(tzinfo=None, microsecond=0) + timedelta(days=3)


def _propose(db: Session, w: World) -> tuple[SqlAlchemyMatchingRepository, str, str]:
    repo = SqlAlchemyMatchingRepository(db)
    patient = make_patient(db)
    proposal_id = repo.create_proposal(
        NewMatch(patient_id=patient.id, intern_id=w.other_intern.id, room_id=None, scheduled_at=_future())
    )
    return repo, proposal_id, patient.id


def _active_assignment(db: Session, patient_id: str) -> Assignment | None:
    return db.scalar(select(Assignment).where(Assignment.patient_id == patient_id, Assignment.active))


def test_paciente_com_proposta_nao_e_candidato_de_novo(db: Session, world: World) -> None:
    repo, _, patient_id = _propose(db, world)
    assert patient_id not in {p.id for p in repo.candidate_patients()}


def test_salvar_cria_vinculo_e_tira_a_proposta(db: Session, world: World) -> None:
    repo, proposal_id, patient_id = _propose(db, world)
    novo_horario = _future() + timedelta(hours=2)
    ConfirmMatchProposal(repo, NoAudit()).execute(
        ConfirmProposalInput(world.admin.id, proposal_id, novo_horario.isoformat() + "Z", None)
    )
    assert repo.get_proposal(proposal_id) is None
    vinculo = _active_assignment(db, patient_id)
    assert vinculo is not None and vinculo.intern_id == world.other_intern.id


def test_cancelar_apaga_sem_criar_vinculo(db: Session, world: World) -> None:
    repo, proposal_id, patient_id = _propose(db, world)
    DiscardMatchProposal(repo, NoAudit()).execute(world.admin.id, proposal_id)
    assert repo.get_proposal(proposal_id) is None
    assert _active_assignment(db, patient_id) is None
    assert patient_id in {p.id for p in repo.candidate_patients()}


def test_nao_salva_se_o_paciente_ja_ganhou_vinculo(db: Session, world: World) -> None:
    repo, proposal_id, patient_id = _propose(db, world)
    db.add(Assignment(patient_id=patient_id, intern_id=world.intern.id))
    db.flush()
    with pytest.raises(ConflictError):
        ConfirmMatchProposal(repo, NoAudit()).execute(
            ConfirmProposalInput(world.admin.id, proposal_id, _future().isoformat() + "Z", None)
        )


def test_sem_par_lista_paciente_e_estagiario_livres(db: Session, world: World) -> None:
    repo = SqlAlchemyMatchingRepository(db)
    livre = make_patient(db)
    patients, interns = repo.unmatched()
    ids_pac = {p.id for p in patients}
    ids_est = {i.id for i in interns}
    assert livre.id in ids_pac
    assert world.patient.id not in ids_pac  # tem vínculo ativo
    assert world.other_intern.id in ids_est  # sem nenhum paciente
    assert world.intern.id not in ids_est  # já atende o paciente do mundo


def test_alerta_sem_horario_nao_duplica_e_some_ao_parear(db: Session, world: World) -> None:
    from app.shared.db.models import PendingMatchRequest

    repo = SqlAlchemyMatchingRepository(db)
    livre = make_patient(db)
    repo.create_pending_match_request(livre.id, None)
    repo.create_pending_match_request(livre.id, None)  # segunda rodada
    abertos = db.scalars(
        select(PendingMatchRequest).where(
            PendingMatchRequest.patient_id == livre.id, PendingMatchRequest.status == "pendente_ajuste_manual"
        )
    ).all()
    assert len(abertos) == 1
    [sem_par] = [p for p in repo.unmatched()[0] if p.id == livre.id]
    assert sem_par.no_match_since is not None

    repo.create_match(
        world.admin.id,
        NewMatch(patient_id=livre.id, intern_id=world.other_intern.id, room_id=None, scheduled_at=_future()),
    )
    db.refresh(abertos[0])
    assert abertos[0].status == "resolvido"
