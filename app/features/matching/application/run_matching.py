"""Motor de pareamento (item 2 + item 6): casa a disponibilidade
recorrente de um paciente com a de um estagiário (mesmo dia da semana,
sobreposição >= duração da sessão), calcula a data/hora concreta da
primeira consulta e só confirma se houver sala livre nesse horário. No
máximo um pareamento por paciente por execução; pacientes com vínculo
ativo não entram como candidatos. O supervisor é atribuído depois.

Fallback por aproximação (item 5): paciente sem nenhum match exato nesta
rodada não é mais simplesmente ignorado — grava um PendingMatchRequest
com o estagiário/horário mais PRÓXIMO disponível (sem garantir overlap
de verdade), pra o administrativo ver e negociar manualmente. Não altera
em nada o resultado do match exato — é só o que passa a acontecer no
caminho que antes não deixava rastro nenhum.

Porta features/matching/application/run-matching.ts.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime

from ....shared.audit.audit_recorder import AuditEvent, AuditRecorder
from ....shared.http.utc_datetime import to_iso_utc
from ....shared.scheduling.weekly_series import period_start_utc
from ..domain.find_candidates import find_all_candidates
from ..domain.find_nearest_fallback import find_nearest_fallback
from ..infrastructure.sqlalchemy_matching_repository import (
    FallbackSuggestionInput,
    NewMatch,
    SqlAlchemyMatchingRepository,
)


@dataclass
class MatchResult:
    appointment_id: str
    intern_id: str
    patient_id: str
    room_id: str | None
    scheduled_at: str  # ISO


class RunMatching:
    def __init__(self, repo: SqlAlchemyMatchingRepository, audit: AuditRecorder) -> None:
        self._repo = repo
        self._audit = audit

    def execute(
        self, actor_id: str, correlation_id: str | None = None, now: datetime | None = None
    ) -> list[MatchResult]:
        now = now if now is not None else datetime.now(UTC).replace(tzinfo=None)
        # Período de atendimentos ainda por começar: a primeira consulta é
        # calculada a partir do início dele, não de hoje.
        period = self._repo.attendance_period()
        if period:
            now = max(now, period_start_utc(period.start))
        patients = self._repo.candidate_patients()
        interns = self._repo.interns_with_windows()
        rooms = self._repo.active_rooms()
        candidates = find_all_candidates(patients, interns, rooms, now)

        results: list[MatchResult] = []
        for candidate in candidates:
            appointment_id = self._repo.create_match(
                actor_id,
                NewMatch(
                    patient_id=candidate.patient_id,
                    intern_id=candidate.intern_id,
                    room_id=candidate.room_id,
                    scheduled_at=candidate.scheduled_at,
                ),
            )
            results.append(
                MatchResult(
                    appointment_id=appointment_id,
                    intern_id=candidate.intern_id,
                    patient_id=candidate.patient_id,
                    room_id=candidate.room_id,
                    scheduled_at=to_iso_utc(candidate.scheduled_at),
                )
            )

        matched_ids = {r.patient_id for r in results}
        fallbacks = 0
        for patient in patients:
            if patient.id in matched_ids:
                continue
            suggestion = find_nearest_fallback(patient, interns, now)
            self._repo.create_pending_match_request(
                patient.id,
                FallbackSuggestionInput(intern_id=suggestion.intern_id, suggested_at=suggestion.suggested_at)
                if suggestion
                else None,
            )
            fallbacks += 1

        self._audit.record(
            AuditEvent(
                actor_id=actor_id,
                action="CREATE",
                resource_type="matching",
                correlation_id=correlation_id,
                diff={"matched": len(results), "fallbacks": fallbacks, "source": "automatic"},
            )
        )

        return results
