"""Rotas de disciplinas (gerenciadas pelo Administrativo; escolhidas pelo
aluno no autocadastro).

Porta features/disciplinas/presentation/routes.ts. Sem domain/application
no original (é CRUD direto do Prisma na rota) — mesma estrutura simples
aqui, direto no SQLAlchemy.
"""

from __future__ import annotations

from collections.abc import Iterator

from fastapi import APIRouter, Depends
from pydantic import Field
from sqlalchemy import select
from sqlalchemy.orm import Session

from ....shared.auth.jwt_auth import require_role
from ....shared.db.models import Disciplina as DisciplinaRow
from ....shared.db.session import get_session
from ....shared.http.camel_model import CamelModel

router = APIRouter(prefix="/api", tags=["disciplinas"], dependencies=[Depends(require_role(["ADMIN"]))])


class DisciplinaOut(CamelModel):
    id: str
    name: str
    active: bool


class CreateDisciplinaRequest(CamelModel):
    name: str = Field(min_length=2)


def _get_db() -> Iterator[Session]:
    with get_session() as session:
        yield session


@router.get("/disciplinas", response_model=list[DisciplinaOut], summary="Lista disciplinas (Admin)")
def list_disciplinas(db: Session = Depends(_get_db)) -> list[DisciplinaOut]:
    rows = db.scalars(select(DisciplinaRow).where(DisciplinaRow.active).order_by(DisciplinaRow.name.asc()))
    return [DisciplinaOut(id=r.id, name=r.name, active=r.active) for r in rows]


@router.post("/disciplinas", response_model=DisciplinaOut, status_code=201, summary="Cadastra uma disciplina (Admin)")
def create_disciplina(body: CreateDisciplinaRequest, db: Session = Depends(_get_db)) -> DisciplinaOut:
    row = DisciplinaRow(name=body.name)
    db.add(row)
    db.flush()
    return DisciplinaOut(id=row.id, name=row.name, active=row.active)
