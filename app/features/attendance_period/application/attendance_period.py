"""Período de atendimentos do ciclo: o administrativo define início e fim;
o sistema agenda as consultas semanais dos pares dentro dele.

- SetAttendancePeriod grava a configuração (a mais recente vale).
- GenerateSeries aplica a série aos pares que JÁ existiam — os criados
  depois da configuração já nascem com ela (ver create_match no
  pareamento). Roda sozinho ao salvar o período (rota PUT). Usa a consulta mais recente de cada vínculo ativo como
  referência de dia/horário/sala: é o horário combinado do par.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, date, datetime

from sqlalchemy import select
from sqlalchemy.orm import Session

from ....shared.audit.audit_recorder import AuditEvent, AuditRecorder
from ....shared.db.models import Appointment, Assignment, AttendancePeriod
from ....shared.db.session import with_rls_context
from ....shared.errors.app_error import ValidationError
from ....shared.scheduling.series_writer import PeriodRange, current_period, schedule_weekly_series

MAX_PERIOD_DAYS = 366


def validate_period(start: date, end: date) -> None:
    if end < start:
        raise ValidationError("A data de fim deve ser igual ou posterior à de início.")
    if (end - start).days > MAX_PERIOD_DAYS:
        raise ValidationError("O período de atendimentos pode ter no máximo um ano.")


class SetAttendancePeriod:
    def __init__(self, session: Session, audit: AuditRecorder) -> None:
        self._session = session
        self._audit = audit

    def execute(self, actor_id: str, start: date, end: date, correlation_id: str | None = None) -> PeriodRange:
        validate_period(start, end)
        row = AttendancePeriod(start_date=start, end_date=end, created_by=actor_id)
        self._session.add(row)
        self._session.flush()
        self._audit.record(
            AuditEvent(
                actor_id=actor_id,
                action="UPDATE",
                resource_type="attendance_period",
                resource_id=row.id,
                correlation_id=correlation_id,
                diff={"startDate": start.isoformat(), "endDate": end.isoformat()},
            )
        )
        return PeriodRange(start=start, end=end)


@dataclass
class SeriesResult:
    created: int
    pairs: int
    # Vínculo ativo sem nenhuma consulta: não há horário combinado para
    # repetir — o par precisa passar pelo match manual primeiro.
    pairs_without_anchor: int


class GenerateSeries:
    def __init__(self, session: Session, audit: AuditRecorder) -> None:
        self._session = session
        self._audit = audit

    def execute(self, actor_id: str, correlation_id: str | None = None, now: datetime | None = None) -> SeriesResult:
        now = now if now is not None else datetime.now(UTC).replace(tzinfo=None)
        period = current_period(self._session)
        if not period:
            raise ValidationError("Configure o período de atendimentos antes de gerar a agenda.")

        def _do(session: Session) -> SeriesResult:
            pairs = session.execute(
                select(Assignment.patient_id, Assignment.intern_id).where(Assignment.active).distinct()
            ).all()
            created = without_anchor = 0
            for patient_id, intern_id in pairs:
                anchor = session.scalar(
                    select(Appointment)
                    .where(
                        Appointment.patient_id == patient_id,
                        Appointment.intern_id == intern_id,
                        Appointment.status != "CANCELLED",
                    )
                    .order_by(Appointment.scheduled_at.desc())
                )
                if not anchor:
                    without_anchor += 1
                    continue
                created += schedule_weekly_series(
                    session,
                    patient_id=patient_id,
                    intern_id=intern_id,
                    room_id=anchor.room_id,
                    anchor=anchor.scheduled_at,
                    period=period,
                    not_before=max(now, anchor.scheduled_at),
                )
            return SeriesResult(created=created, pairs=len(pairs), pairs_without_anchor=without_anchor)

        result = with_rls_context(self._session, actor_id, "ADMIN", _do)
        self._audit.record(
            AuditEvent(
                actor_id=actor_id,
                action="CREATE",
                resource_type="appointment",
                correlation_id=correlation_id,
                diff={"event": "weekly_series", "created": result.created, "pairs": result.pairs},
            )
        )
        return result
