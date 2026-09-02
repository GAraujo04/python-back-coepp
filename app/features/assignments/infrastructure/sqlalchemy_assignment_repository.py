"""Leitura/escrita de vínculos (paciente↔estagiário↔supervisor). Sem RLS
(gestão do Admin).

Porta features/assignments/infrastructure/prisma-assignment-repository.ts.
Sem domain/ nem application/ nesta slice no original — a validação vive
direto na rota; mantido fiel (ver presentation/routes.py).
"""

from __future__ import annotations

from dataclasses import dataclass

from sqlalchemy import select
from sqlalchemy.orm import Session

from ....shared.crypto.field_encryption import decrypt_field
from ....shared.db.models import Assignment


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

    def update(self, assignment_id: str, intern_id: str | None = None, supervisor_id: str | None = None) -> None:
        """Altera estagiário e/ou supervisor de um vínculo já existente. O
        primeiro vínculo nasce do pareamento (automático ou manual, ver
        matching); isto é a correção manual de um vínculo que já existe
        (ex.: estagiário saiu, supervisor mudou) — não cria vínculo novo."""
        row = self._session.get(Assignment, assignment_id)
        assert row is not None  # existência já checada no boundary antes desta chamada
        if intern_id:
            row.intern_id = intern_id
        if supervisor_id:
            row.supervisor_id = supervisor_id
        self._session.flush()
