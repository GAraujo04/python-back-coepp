"""Busca a conta do paciente pelo índice cego do CPF, trazendo a conta de
login vinculada.

Porta features/auth/infrastructure/prisma-patient-auth-repository.ts.
"""

from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.orm import Session

from ....shared.crypto.blind_index import cpf_blind_index
from ....shared.db.models import Patient, User
from ..application.ports import PatientAccount, PatientAuthLookup


class SqlAlchemyPatientAuthRepository(PatientAuthLookup):
    def __init__(self, session: Session) -> None:
        self._session = session

    def find_by_cpf(self, cpf: str) -> PatientAccount | None:
        row = self._session.scalar(select(Patient).where(Patient.cpf_hash == cpf_blind_index(cpf)))
        if not row or not row.user_id:
            return None
        account = self._session.get(User, row.user_id)
        if not account or not account.active:
            return None
        return PatientAccount(
            user_id=account.id,
            email=account.email,
            full_name=account.full_name,
            birth_date=row.birth_date.isoformat() if row.birth_date else None,
        )
