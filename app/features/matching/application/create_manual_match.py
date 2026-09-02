"""Match manual (item 7): admin escolhe paciente + estagiário + horário +
sala (opcional), sobrepondo a sugestão automática. Avisa sobre horário
incompatível com a disponibilidade informada e sobre sala ocupada, mas
não bloqueia — exceto que exige confirmação explícita
(`acknowledge_warnings`) antes de gravar quando há algum aviso. Uma sala
ocupada NUNCA é gravada em conflito: se a sala pedida está ocupada, o
atendimento é criado sem sala (ver docs/specs/match-manual.md).

Porta features/matching/application/create-manual-match.ts.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import UTC, datetime
from typing import Literal

from ....shared.audit.audit_recorder import AuditEvent, AuditRecorder
from ....shared.errors.app_error import NotFoundError, ValidationError
from ....shared.scheduling.time_of_day import js_weekday, to_hhmm
from ..domain.covers_time import covers_time
from ..infrastructure.sqlalchemy_matching_repository import NewMatch, SqlAlchemyMatchingRepository

ManualMatchWarningCode = Literal[
    "TIME_INCOMPATIBLE_PATIENT", "TIME_INCOMPATIBLE_INTERN", "ROOM_OCCUPIED", "PATIENT_ALREADY_ASSIGNED"
]


@dataclass
class ManualMatchWarning:
    code: ManualMatchWarningCode
    message: str


@dataclass
class CreateManualMatchInput:
    actor_id: str
    patient_id: str
    intern_id: str
    scheduled_at: str  # ISO
    room_id: str | None = None
    # Confirma a criação mesmo diante de avisos. Sem isso, avisos bloqueiam (o admin precisa ver e confirmar).
    acknowledge_warnings: bool = False
    correlation_id: str | None = None


@dataclass
class CreateManualMatchOutcome:
    """Resultado estruturado (não lançado como erro): a lista de
    `details` de AppError é só logada no servidor, nunca chega ao
    cliente — por isso os avisos precisam viajar no corpo da resposta,
    não em um erro genérico."""

    confirmed: bool
    warnings: list[ManualMatchWarning] = field(default_factory=list)
    appointment_id: str | None = None


class CreateManualMatch:
    def __init__(self, repo: SqlAlchemyMatchingRepository, audit: AuditRecorder) -> None:
        self._repo = repo
        self._audit = audit

    def execute(self, input: CreateManualMatchInput) -> CreateManualMatchOutcome:
        try:
            parsed = datetime.fromisoformat(input.scheduled_at.replace("Z", "+00:00"))
        except ValueError as exc:
            raise ValidationError("Data/hora do match manual inválida.") from exc
        # `.astimezone(UTC)` funciona tanto pra string COM offset (converte
        # normalmente) quanto SEM offset (Python presume fuso LOCAL do
        # processo antes de converter — mesmo comportamento do `new Date()`
        # do JS pra uma string sem timezone). Resultado: naive-UTC,
        # convenção do projeto pra tudo que é persistido no banco.
        scheduled_at = parsed.astimezone(UTC).replace(tzinfo=None)

        patient = self._repo.find_patient_candidate(input.patient_id)
        intern = self._repo.find_intern_candidate(input.intern_id)
        if not patient:
            raise NotFoundError("Paciente não encontrado.", {"patientId": input.patient_id})
        if not intern:
            raise NotFoundError("Estagiário não encontrado.", {"internId": input.intern_id})

        weekday = js_weekday(scheduled_at)
        hhmm = to_hhmm(scheduled_at)
        warnings: list[ManualMatchWarning] = []

        if not covers_time(patient.windows, weekday, hhmm):
            warnings.append(
                ManualMatchWarning(
                    code="TIME_INCOMPATIBLE_PATIENT",
                    message="O horário escolhido está fora da disponibilidade informada pelo paciente.",
                )
            )
        if not covers_time(intern.windows, weekday, hhmm):
            warnings.append(
                ManualMatchWarning(
                    code="TIME_INCOMPATIBLE_INTERN",
                    message="O horário escolhido está fora da disponibilidade informada pelo estagiário.",
                )
            )
        if patient.active_intern_id and patient.active_intern_id != input.intern_id:
            warnings.append(
                ManualMatchWarning(
                    code="PATIENT_ALREADY_ASSIGNED", message="O paciente já tem um vínculo ativo com outro estagiário."
                )
            )

        room_id = input.room_id
        if room_id and self._repo.room_conflict(room_id, scheduled_at):
            warnings.append(
                ManualMatchWarning(
                    code="ROOM_OCCUPIED",
                    message=(
                        "A sala escolhida já está ocupada nesse horário; o atendimento será criado sem sala definida."
                    ),
                )
            )
            room_id = None

        if warnings and not input.acknowledge_warnings:
            return CreateManualMatchOutcome(confirmed=False, warnings=warnings)

        appointment_id = self._repo.create_match(
            input.actor_id,
            NewMatch(
                patient_id=input.patient_id, intern_id=input.intern_id, room_id=room_id, scheduled_at=scheduled_at
            ),
        )

        self._audit.record(
            AuditEvent(
                actor_id=input.actor_id,
                action="CREATE",
                resource_type="matching",
                resource_id=appointment_id,
                correlation_id=input.correlation_id,
                diff={"source": "manual", "warnings": [w.code for w in warnings]},
            )
        )

        return CreateManualMatchOutcome(confirmed=True, appointment_id=appointment_id, warnings=warnings)
