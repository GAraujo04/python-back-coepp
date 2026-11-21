"""Salvar ou cancelar uma proposta do pareamento automático.

- ConfirmMatchProposal: o administrativo salva a proposta — com o horário e
  a sala que ela trouxe ou com os que ele ajustou. Aí nasce o vínculo e a
  agenda semanal até o fim do período (create_match), e a proposta some:
  dali em diante o par é gerido na tela de Vínculos.
- DiscardMatchProposal: cancelada sem salvar, a proposta é apagada e não
  deixa vínculo nem consulta. O paciente volta a ser candidato na próxima
  rodada.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime

from ....shared.audit.audit_recorder import AuditEvent, AuditRecorder
from ....shared.errors.app_error import ConflictError, NotFoundError, ValidationError
from ..infrastructure.sqlalchemy_matching_repository import NewMatch, SqlAlchemyMatchingRepository


@dataclass
class ConfirmProposalInput:
    actor_id: str
    proposal_id: str
    # O que o administrativo salvou: o proposto, ou o que ele ajustou no card.
    scheduled_at: str  # ISO
    room_id: str | None
    correlation_id: str | None = None


def _parse_iso(value: str) -> datetime:
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError as exc:
        raise ValidationError("Data/hora inválida.") from exc
    return parsed.astimezone(UTC).replace(tzinfo=None)


class ConfirmMatchProposal:
    def __init__(self, repo: SqlAlchemyMatchingRepository, audit: AuditRecorder) -> None:
        self._repo = repo
        self._audit = audit

    def execute(self, input: ConfirmProposalInput, now: datetime | None = None) -> str:
        now = now if now is not None else datetime.now(UTC).replace(tzinfo=None)
        proposal = self._repo.get_proposal(input.proposal_id)
        if not proposal:
            raise NotFoundError("Proposta de pareamento não encontrada.", {"proposalId": input.proposal_id})
        if self._repo.patient_has_active_assignment(proposal.patient_id):
            raise ConflictError("O paciente já tem vínculo ativo.", {"patientId": proposal.patient_id})

        scheduled_at = _parse_iso(input.scheduled_at)
        if scheduled_at <= now:
            raise ValidationError("A primeira consulta precisa estar no futuro.")
        room_id = input.room_id
        patient_id, intern_id = proposal.patient_id, proposal.intern_id

        # Apaga antes de gravar o vínculo: libera a reserva de sala/horário
        # da própria proposta. Tudo na mesma transação — se create_match
        # falhar (sala ocupada), o rollback devolve a proposta.
        self._repo.delete_proposal(proposal)
        appointment_id = self._repo.create_match(
            input.actor_id,
            NewMatch(patient_id=patient_id, intern_id=intern_id, room_id=room_id, scheduled_at=scheduled_at),
        )
        self._audit.record(
            AuditEvent(
                actor_id=input.actor_id,
                action="CREATE",
                resource_type="matching",
                resource_id=appointment_id,
                correlation_id=input.correlation_id,
                diff={"source": "proposal", "proposalId": input.proposal_id},
            )
        )
        return appointment_id


class DiscardMatchProposal:
    def __init__(self, repo: SqlAlchemyMatchingRepository, audit: AuditRecorder) -> None:
        self._repo = repo
        self._audit = audit

    def execute(self, actor_id: str, proposal_id: str, correlation_id: str | None = None) -> None:
        proposal = self._repo.get_proposal(proposal_id)
        if not proposal:
            return  # já descartada/salva: idempotente
        self._repo.delete_proposal(proposal)
        self._audit.record(
            AuditEvent(
                actor_id=actor_id,
                action="DELETE",
                resource_type="match_proposal",
                resource_id=proposal_id,
                correlation_id=correlation_id,
            )
        )
