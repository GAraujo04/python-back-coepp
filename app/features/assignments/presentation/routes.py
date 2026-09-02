"""Rotas de vínculos: listar e alterar estagiário/supervisor de um
vínculo já existente (gestão do Administrativo). O vínculo em si nasce
do pareamento (automático ou manual, ver slice matching) — isto é só a
correção manual de um vínculo que já existe (estagiário saiu, supervisor
mudou etc.).

Porta features/assignments/presentation/routes.ts. Sem domain/ nem
application/ nesta slice no original — a validação (campo obrigatório,
existência/papel/atividade do estagiário e supervisor) vive direto na
rota; mantido fiel, mesmo sendo uma exceção à regra geral do projeto
(lógica de domínio não deveria morar em presentation/) — não é escopo
desta migração redesenhar a slice, só reproduzir o contrato.
"""

from __future__ import annotations

from collections.abc import Iterator

from fastapi import APIRouter, Depends, Request
from sqlalchemy.orm import Session

from ....shared.audit.audit_recorder import AuditEvent, AuditRecorder
from ....shared.audit.sql_audit_recorder import SqlAuditRecorder
from ....shared.auth.jwt_auth import CurrentUser, require_role
from ....shared.db.models import User
from ....shared.db.session import get_session
from ....shared.errors.app_error import ValidationError
from ..infrastructure.sqlalchemy_assignment_repository import SqlAlchemyAssignmentRepository
from .schemas import AssignmentViewOut, UpdateAssignmentRequest

router = APIRouter(prefix="/api", tags=["assignments"])


def _get_db() -> Iterator[Session]:
    with get_session() as session:
        yield session


def _get_repo(db: Session = Depends(_get_db)) -> SqlAlchemyAssignmentRepository:
    return SqlAlchemyAssignmentRepository(db)


def _get_audit(db: Session = Depends(_get_db)) -> AuditRecorder:
    return SqlAuditRecorder(db)


@router.get(
    "/assignments",
    response_model=list[AssignmentViewOut],
    summary="Lista vínculos (paciente↔estagiário↔supervisor) — Admin",
)
def list_assignments(
    current: CurrentUser = Depends(require_role(["ADMIN"])),
    repo: SqlAlchemyAssignmentRepository = Depends(_get_repo),
) -> list[AssignmentViewOut]:
    return [
        AssignmentViewOut(
            id=a.id,
            patient_name=a.patient_name,
            intern_id=a.intern_id,
            intern_name=a.intern_name,
            supervisor_id=a.supervisor_id,
            supervisor_name=a.supervisor_name,
            active=a.active,
        )
        for a in repo.list()
    ]


@router.patch(
    "/assignments/{assignment_id}",
    status_code=204,
    summary="Altera estagiário e/ou supervisor de um vínculo já existente — Admin",
)
def update_assignment(
    assignment_id: str,
    body: UpdateAssignmentRequest,
    request: Request,
    current: CurrentUser = Depends(require_role(["ADMIN"])),
    db: Session = Depends(_get_db),
    repo: SqlAlchemyAssignmentRepository = Depends(_get_repo),
    audit: AuditRecorder = Depends(_get_audit),
) -> None:
    if not body.intern_id and not body.supervisor_id:
        raise ValidationError("Informe ao menos um campo para alterar (estagiário ou supervisor).")
    if body.intern_id:
        intern = db.get(User, body.intern_id)
        if not intern or intern.role != "INTERN" or not intern.active:
            raise ValidationError("Estagiário inválido ou inativo.", {"internId": body.intern_id})
    if body.supervisor_id:
        supervisor = db.get(User, body.supervisor_id)
        if not supervisor or supervisor.role != "SUPERVISOR" or not supervisor.active:
            raise ValidationError("Supervisor inválido ou inativo.", {"supervisorId": body.supervisor_id})

    repo.update(assignment_id, intern_id=body.intern_id, supervisor_id=body.supervisor_id)
    audit.record(
        AuditEvent(
            actor_id=current.sub,
            action="UPDATE",
            resource_type="assignment",
            resource_id=assignment_id,
            correlation_id=getattr(request.state, "correlation_id", None),
            diff={"internId": body.intern_id, "supervisorId": body.supervisor_id},
        )
    )
