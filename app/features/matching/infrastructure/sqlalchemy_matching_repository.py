"""Persistência do pareamento. Escritas de agendamento correm sob
contexto ADMIN (RLS).

Porta features/matching/infrastructure/prisma-matching-repository.ts.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from datetime import UTC, datetime

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from ....shared.crypto.field_encryption import decrypt_field
from ....shared.db.models import Appointment, Assignment, MatchProposal, PendingMatchRequest, Room, User
from ....shared.db.models import AvailabilityWindow as AvailabilityWindowRow
from ....shared.db.models import Patient as PatientRow
from ....shared.db.session import with_rls_context
from ....shared.errors.app_error import ConflictError
from ....shared.scheduling.room_category import preferred_room_category
from ....shared.scheduling.room_conflict import find_room_conflict
from ....shared.scheduling.series_writer import PeriodRange, current_period, schedule_weekly_series
from ...patients.infrastructure.sqlalchemy_patient_repository import age_in_years
from ..domain.find_candidates import PersonWithWindows, Reservation, RoomOption, WindowSlot


@dataclass
class PatientCandidate(PersonWithWindows):
    """Estagiário do vínculo ativo atual, se houver (para o aviso PATIENT_ALREADY_ASSIGNED)."""

    active_intern_id: str | None = None


@dataclass
class MatchView:
    appointment_id: str
    scheduled_at: datetime
    status: str
    intern_id: str
    intern_name: str
    patient_name: str
    patient_code: str
    room_name: str | None


@dataclass
class MatchProposalView:
    id: str
    patient_id: str
    patient_code: str
    intern_id: str
    intern_name: str
    room_id: str | None
    room_name: str | None
    scheduled_at: datetime


@dataclass
class UnmatchedPatient:
    id: str
    code: str
    is_minor: bool
    has_disability: bool
    windows: list[WindowSlot]
    registered_at: datetime
    # Desde quando o pareamento automático não acha horário compatível
    # (None = ainda não passou por uma rodada).
    no_match_since: datetime | None


@dataclass
class UnmatchedIntern:
    id: str
    name: str
    ra: str | None
    windows: list[WindowSlot]


@dataclass
class PendingMatchRequestView:
    id: str
    patient_code: str
    suggested_intern_name: str | None
    suggested_at: datetime | None
    status: str
    created_at: datetime


@dataclass
class NewMatch:
    patient_id: str
    intern_id: str
    room_id: str | None
    scheduled_at: datetime


@dataclass
class FallbackSuggestionInput:
    intern_id: str
    suggested_at: datetime


def _natural_key(room: Room) -> list[int | str]:
    """Trechos numéricos comparados como número: o banco ordena o nome como texto."""
    return [int(part) if part.isdigit() else part.lower() for part in re.split(r"(\d+)", room.name)]


def _windows_of(rows: list[AvailabilityWindowRow]) -> list[WindowSlot]:
    return [WindowSlot(weekday=w.weekday, start_time=w.start_time, end_time=w.end_time) for w in rows]


def _is_minor(p: PatientRow) -> bool:
    return age_in_years(decrypt_field(p.birth_date_enc)) < 18 if p.birth_date_enc else False


class SqlAlchemyMatchingRepository:
    def __init__(self, session: Session) -> None:
        self._session = session

    def candidate_patients(self) -> list[PersonWithWindows]:
        """Pacientes sem vínculo ativo nem proposta em aberto (candidatos ao
        pareamento automático), com sua disponibilidade."""
        active_patient_ids = select(Assignment.patient_id).where(Assignment.active)
        proposed_patient_ids = select(MatchProposal.patient_id)
        rows = self._session.scalars(
            select(PatientRow).where(
                PatientRow.id.not_in(active_patient_ids), PatientRow.id.not_in(proposed_patient_ids)
            )
        ).all()
        return [
            PersonWithWindows(
                id=p.id,
                name=decrypt_field(p.full_name_enc),
                code=p.code,
                windows=_windows_of(p.availability_windows),
                preferred_room_category=preferred_room_category(p.has_disability, _is_minor(p)),
            )
            for p in rows
        ]

    def interns_with_windows(self) -> list[PersonWithWindows]:
        """Estagiários ativos com sua disponibilidade recorrente."""
        rows = self._session.scalars(select(User).where(User.role == "INTERN", User.active)).all()
        return [PersonWithWindows(id=u.id, name=u.full_name, windows=_windows_of(u.availability_windows)) for u in rows]

    def active_rooms(self) -> list[RoomOption]:
        """Salas ativas em ordem natural de nome ("Sala 2" antes de "Sala 10") —
        ordem estável de busca da primeira livre."""
        rows = self._session.scalars(select(Room).where(Room.active)).all()
        return [RoomOption(id=r.id, name=r.name, category=r.category) for r in sorted(rows, key=_natural_key)]

    def find_patient_candidate(self, patient_id: str) -> PatientCandidate | None:
        """Paciente específico (para o match manual), com disponibilidade e vínculo ativo atual, se houver."""
        patient = self._session.get(PatientRow, patient_id)
        if not patient:
            return None
        active = self._session.scalar(
            select(Assignment.intern_id).where(Assignment.patient_id == patient_id, Assignment.active)
        )
        return PatientCandidate(
            id=patient.id,
            name=decrypt_field(patient.full_name_enc),
            windows=_windows_of(patient.availability_windows),
            active_intern_id=active,
        )

    def find_intern_candidate(self, intern_id: str) -> PersonWithWindows | None:
        """Estagiário específico (para o match manual). Só encontra usuários com role=INTERN."""
        user = self._session.get(User, intern_id)
        if not user or user.role != "INTERN":
            return None
        return PersonWithWindows(id=user.id, name=user.full_name, windows=_windows_of(user.availability_windows))

    def room_conflict(self, room_id: str, scheduled_at: datetime) -> bool:
        """Existe outro agendamento (não cancelado) nessa sala que colide
        com o horário? Checagem avulsa (fora de transação), para compor
        avisos."""
        return find_room_conflict(self._session, room_id, scheduled_at) is not None

    def attendance_period(self) -> PeriodRange | None:
        """Período de atendimentos vigente, se o administrativo configurou."""
        return current_period(self._session)

    def create_match(self, actor_id: str, m: NewMatch) -> str:
        """Cria o vínculo (se necessário) + a consulta na sala calculada.
        Reconfirma o conflito de sala dentro da transação (defesa em
        profundidade — o algoritmo/use case já checou antes, mas a
        escrita real precisa confirmar). Usada ao salvar uma proposta do
        pareamento automático e pelo match manual."""

        def _do(session: Session) -> str:
            if m.room_id:
                conflict_id = find_room_conflict(session, m.room_id, m.scheduled_at)
                if conflict_id:
                    raise ConflictError(
                        "A sala escolhida ficou ocupada antes de confirmar o pareamento.",
                        {"roomId": m.room_id, "conflictingAppointmentId": conflict_id},
                    )
            existing = session.scalar(
                select(Assignment).where(
                    Assignment.patient_id == m.patient_id, Assignment.intern_id == m.intern_id, Assignment.active
                )
            )
            if not existing:
                # Supervisor do vínculo = supervisor acadêmico que o aluno escolheu no cadastro.
                intern = session.get(User, m.intern_id)
                session.add(
                    Assignment(
                        patient_id=m.patient_id,
                        intern_id=m.intern_id,
                        supervisor_id=intern.academic_supervisor_id if intern else None,
                    )
                )
            appt = Appointment(
                patient_id=m.patient_id,
                intern_id=m.intern_id,
                room_id=m.room_id,
                scheduled_at=m.scheduled_at,
                status="SCHEDULED",
            )
            session.add(appt)
            # O paciente ganhou par: o alerta de "sem horário compatível", se
            # havia, deixa de valer.
            for pending in session.scalars(
                select(PendingMatchRequest).where(
                    PendingMatchRequest.patient_id == m.patient_id,
                    PendingMatchRequest.status == "pendente_ajuste_manual",
                )
            ):
                pending.status = "resolvido"
                pending.resolved_at = datetime.now(UTC).replace(tzinfo=None)
            session.flush()
            # Com período configurado, o par já sai com a agenda do ciclo:
            # toda semana, mesmo dia e horário, até o fim do período. Sem
            # período, só a primeira consulta — o comportamento de antes.
            period = current_period(session)
            if period:
                schedule_weekly_series(
                    session,
                    patient_id=m.patient_id,
                    intern_id=m.intern_id,
                    room_id=m.room_id,
                    anchor=m.scheduled_at,
                    period=period,
                    not_before=m.scheduled_at,
                )
            return appt.id

        return with_rls_context(self._session, actor_id, "ADMIN", _do)

    def reservations(self) -> list[Reservation]:
        """Horários (estagiário/sala) já tomados por propostas em aberto."""
        rows = self._session.scalars(select(MatchProposal)).all()
        return [Reservation(intern_id=r.intern_id, room_id=r.room_id, scheduled_at=r.scheduled_at) for r in rows]

    def create_proposal(self, m: NewMatch) -> str:
        row = MatchProposal(
            patient_id=m.patient_id, intern_id=m.intern_id, room_id=m.room_id, scheduled_at=m.scheduled_at
        )
        self._session.add(row)
        self._session.flush()
        return row.id

    def list_proposals(self) -> list[MatchProposalView]:
        rows = self._session.scalars(select(MatchProposal).order_by(MatchProposal.scheduled_at.asc())).all()
        return [
            MatchProposalView(
                id=r.id,
                patient_id=r.patient_id,
                patient_code=r.patient.code,
                intern_id=r.intern_id,
                intern_name=r.intern.full_name,
                room_id=r.room_id,
                room_name=r.room.name if r.room else None,
                scheduled_at=r.scheduled_at,
            )
            for r in rows
        ]

    def get_proposal(self, proposal_id: str) -> MatchProposal | None:
        return self._session.get(MatchProposal, proposal_id)

    def delete_proposal(self, proposal: MatchProposal) -> None:
        self._session.delete(proposal)
        self._session.flush()

    def patient_has_active_assignment(self, patient_id: str) -> bool:
        return (
            self._session.scalar(select(Assignment.id).where(Assignment.patient_id == patient_id, Assignment.active))
            is not None
        )

    def create_pending_match_request(self, patient_id: str, suggestion: FallbackSuggestionInput | None) -> None:
        """Grava a sugestão de fallback (item 5) — paciente sem match
        exato nesta rodada. Não cria Assignment nem Appointment (não é um
        match de verdade); é só o alerta pra alguém do administrativo
        negociar manualmente. intern_id pode ser None se não havia
        nenhum estagiário com disponibilidade cadastrada (nada pra
        sugerir, mas o paciente ainda assim fica registrado como
        pendente de ajuste manual).

        Um alerta em aberto por paciente: rodar o pareamento de novo só
        atualiza a sugestão do alerta que já existe (antes, cada rodada
        duplicava o paciente na lista e no sininho)."""
        existing = self._session.scalar(
            select(PendingMatchRequest).where(
                PendingMatchRequest.patient_id == patient_id,
                PendingMatchRequest.status == "pendente_ajuste_manual",
            )
        )
        row = existing or PendingMatchRequest(patient_id=patient_id)
        row.suggested_intern_id = suggestion.intern_id if suggestion else None
        row.suggested_at = suggestion.suggested_at if suggestion else None
        if not existing:
            self._session.add(row)
        self._session.flush()

    def unmatched(self) -> tuple[list[UnmatchedPatient], list[UnmatchedIntern]]:
        """Quem está sem par, para o administrativo conversar e parear à mão:
        pacientes sem vínculo ativo nem proposta em aberto (quem espera há
        mais tempo primeiro) e estagiários ativos sem nenhum paciente."""
        active = select(Assignment).where(Assignment.active)
        proposals = select(MatchProposal)
        patients = self._session.scalars(
            select(PatientRow)
            .where(
                PatientRow.id.not_in(active.with_only_columns(Assignment.patient_id)),
                PatientRow.id.not_in(proposals.with_only_columns(MatchProposal.patient_id)),
            )
            .order_by(PatientRow.created_at.asc())
        ).all()
        rows = self._session.execute(
            select(PendingMatchRequest.patient_id, func.min(PendingMatchRequest.created_at))
            .where(PendingMatchRequest.status == "pendente_ajuste_manual")
            .group_by(PendingMatchRequest.patient_id)
        ).all()
        no_match_since: dict[str, datetime] = {patient_id: since for patient_id, since in rows}
        interns = self._session.scalars(
            select(User)
            .where(
                User.role == "INTERN",
                User.active,
                User.id.not_in(active.with_only_columns(Assignment.intern_id)),
                User.id.not_in(proposals.with_only_columns(MatchProposal.intern_id)),
            )
            .order_by(User.full_name.asc())
        ).all()
        return (
            [
                UnmatchedPatient(
                    id=p.id,
                    code=p.code,
                    is_minor=_is_minor(p),
                    has_disability=p.has_disability,
                    windows=sorted(_windows_of(p.availability_windows), key=lambda w: (w.weekday, w.start_time)),
                    registered_at=p.created_at,
                    no_match_since=no_match_since.get(p.id),
                )
                for p in patients
            ],
            [
                UnmatchedIntern(
                    id=u.id,
                    name=u.full_name,
                    ra=u.ra,
                    windows=sorted(_windows_of(u.availability_windows), key=lambda w: (w.weekday, w.start_time)),
                )
                for u in interns
            ],
        )

    def list_pending_match_requests(self) -> list[PendingMatchRequestView]:
        """Alertas de fallback pendentes (visão do admin — sem RLS, mesma exceção de assignments)."""
        rows = self._session.scalars(
            select(PendingMatchRequest)
            .where(PendingMatchRequest.status == "pendente_ajuste_manual")
            .order_by(PendingMatchRequest.created_at.asc())
        ).all()
        return [
            PendingMatchRequestView(
                id=r.id,
                patient_code=r.patient.code,
                suggested_intern_name=r.suggested_intern.full_name if r.suggested_intern else None,
                suggested_at=r.suggested_at,
                status=r.status,
                created_at=r.created_at,
            )
            for r in rows
        ]

    def resolve_pending_match_request(self, request_id: str) -> None:
        """Marca o alerta como resolvido (equipe já entrou em contato com o paciente). Idempotente."""
        row = self._session.scalar(
            select(PendingMatchRequest).where(
                PendingMatchRequest.id == request_id, PendingMatchRequest.status == "pendente_ajuste_manual"
            )
        )
        if row:
            row.status = "resolvido"
            row.resolved_at = datetime.now(UTC).replace(tzinfo=None)
            self._session.flush()

    def list_matches(self, actor_id: str) -> list[MatchView]:
        """Lista as consultas/pareamentos (visão de coordenação — admin/supervisor)."""

        def _do(session: Session) -> list[MatchView]:
            rows = session.scalars(select(Appointment).order_by(Appointment.scheduled_at.asc())).all()
            return [
                MatchView(
                    appointment_id=r.id,
                    scheduled_at=r.scheduled_at,
                    status=r.status,
                    intern_id=r.intern_id,
                    intern_name=r.intern.full_name,
                    patient_name=decrypt_field(r.patient.full_name_enc),
                    patient_code=r.patient.code,
                    room_name=r.room.name if r.room else None,
                )
                for r in rows
            ]

        return with_rls_context(self._session, actor_id, "ADMIN", _do)
