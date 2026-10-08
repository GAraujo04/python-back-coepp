"""Leitura/escrita de vínculos (paciente↔estagiário↔supervisor). Sem RLS
(gestão do Admin).

Porta features/assignments/infrastructure/prisma-assignment-repository.ts.
Sem domain/ nem application/ nesta slice no original — a validação vive
direto na rota; mantido fiel (ver presentation/routes.py).
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime

from sqlalchemy import select
from sqlalchemy.orm import Session

from ....shared.crypto.field_encryption import decrypt_field
from ....shared.db.models import Appointment, Assignment
from ....shared.db.session import with_rls_context
from ....shared.errors.app_error import NotFoundError


@dataclass
class AssignmentView:
    id: str
    patient_name: str
    intern_id: str
    intern_name: str
    supervisor_id: str | None
    supervisor_name: str | None
    active: bool


class SqlAlchemyAssignmentRepository:
    def __init__(self, session: Session) -> None:
        self._session = session

    def list(self) -> list[AssignmentView]:
        rows = self._session.scalars(
            select(Assignment).where(Assignment.active).order_by(Assignment.created_at.desc())
        ).all()
        return [
            AssignmentView(
                id=r.id,
                patient_name=decrypt_field(r.patient.full_name_enc),
                intern_id=r.intern_id,
                intern_name=r.intern.full_name,
                supervisor_id=r.supervisor_id,
                supervisor_name=r.supervisor.full_name if r.supervisor else None,
                active=r.active,
            )
            for r in rows
        ]

    def update(
        self,
        actor_id: str,
        assignment_id: str,
        intern_id: str | None = None,
        supervisor_id: str | None = None,
        active: bool | None = None,
    ) -> dict[str, int]:
        """Altera estagiário e/ou supervisor de um vínculo já existente, ou o
        encerra. O primeiro vínculo nasce do pareamento (automático ou
        manual, ver matching); isto é a correção manual de um vínculo que já
        existe (ex.: estagiário saiu, supervisor mudou) — não cria vínculo
        novo.

        A agenda acompanha o vínculo — as consultas FUTURAS ainda marcadas:
        - troca de estagiário: passam para o novo, no mesmo horário (o
          paciente não perde o horário; se o novo não puder, o
          administrativo remarca);
        - encerramento: são canceladas.
        Consultas passadas ficam como estão: são histórico.

        Devolve quantas consultas foram transferidas/canceladas (auditoria)."""
        row = self._session.get(Assignment, assignment_id)
        if row is None or not row.active:
            raise NotFoundError("Vínculo não encontrado ou já encerrado.", {"assignmentId": assignment_id})
        previous_intern = row.intern_id
        counts = {"transferred": 0, "cancelled": 0}

        def _future(session: Session) -> list[Appointment]:
            now = datetime.now(UTC).replace(tzinfo=None)
            return list(
                session.scalars(
                    select(Appointment).where(
                        Appointment.patient_id == row.patient_id,
                        Appointment.intern_id == previous_intern,
                        Appointment.status == "SCHEDULED",
                        Appointment.scheduled_at >= now,
                    )
                ).all()
            )

        def _apply(session: Session) -> None:
            if active is False:
                for appt in _future(session):
                    appt.status = "CANCELLED"
                    counts["cancelled"] += 1
                row.active = False
            elif intern_id and intern_id != previous_intern:
                for appt in _future(session):
                    appt.intern_id = intern_id
                    counts["transferred"] += 1
                row.intern_id = intern_id
            if supervisor_id:
                row.supervisor_id = supervisor_id
            session.flush()

        # appointments tem RLS: só o contexto ADMIN altera.
        with_rls_context(self._session, actor_id, "ADMIN", _apply)
        return counts
