"""Rotas de pacientes: cadastro (Admin), leitura escopada e portal do
paciente.

Porta features/patients/presentation/routes.ts.
"""

from __future__ import annotations

from collections.abc import Iterator

from fastapi import APIRouter, Depends, Request
from sqlalchemy.orm import Session

from ....shared.audit.audit_recorder import AuditRecorder
from ....shared.audit.sql_audit_recorder import SqlAuditRecorder
from ....shared.auth.jwt_auth import CurrentUser, get_current_user, require_role
from ....shared.db.session import get_session
from ....shared.errors.app_error import NotFoundError
from ....shared.privacy.patient_name import patient_name_for
from ..application.create_patient import CreatePatient, CreatePatientInput
from ..infrastructure.sqlalchemy_patient_repository import (
    AccessContext,
    GuardianInput,
    PatientSummary,
    SqlAlchemyPatientRepository,
)
from .schemas import CreatePatientRequest, DisabilitySummaryOut, PatientSummaryOut, PortalAppointmentOut, PortalDataOut

router = APIRouter(prefix="/api", tags=["patients"])


def _get_db() -> Iterator[Session]:
    with get_session() as session:
        yield session


def _get_repo(db: Session = Depends(_get_db)) -> SqlAlchemyPatientRepository:
    return SqlAlchemyPatientRepository(db)


def _get_audit(db: Session = Depends(_get_db)) -> AuditRecorder:
    return SqlAuditRecorder(db)


def _serialize_summary(p: PatientSummary, role: str) -> PatientSummaryOut:
    return PatientSummaryOut(
        id=p.id,
        code=p.code,
        full_name=patient_name_for(role, p.full_name),
        birth_date=p.birth_date,
        is_minor=p.is_minor,
        has_disability=p.has_disability,
        disabilities=[DisabilitySummaryOut(type=d.type, other_text=d.other_text) for d in p.disabilities],
    )


@router.get(
    "/patients",
    response_model=list[PatientSummaryOut],
    summary="Lista pacientes vinculados ao usuário (nome descriptografado)",
)
def list_patients(
    current: CurrentUser = Depends(get_current_user), repo: SqlAlchemyPatientRepository = Depends(_get_repo)
) -> list[PatientSummaryOut]:
    ctx = AccessContext(user_id=current.sub, role=current.role)
    return [_serialize_summary(p, current.role) for p in repo.list_for_actor(ctx)]


@router.post(
    "/patients",
    response_model=PatientSummaryOut,
    status_code=201,
    summary="Cadastra um paciente (Administrativo). Responsável obrigatório se menor.",
)
def create_patient(
    body: CreatePatientRequest,
    request: Request,
    current: CurrentUser = Depends(require_role(["ADMIN"])),
    repo: SqlAlchemyPatientRepository = Depends(_get_repo),
    audit: AuditRecorder = Depends(_get_audit),
) -> PatientSummaryOut:
    use_case = CreatePatient(repo, audit)
    patient = use_case.execute(
        CreatePatientInput(
            full_name=body.full_name,
            cpf=body.cpf,
            birth_date=body.birth_date,
            phone=body.phone,
            guardian=GuardianInput(
                name=body.guardian.name,
                cpf=body.guardian.cpf,
                relationship=body.guardian.relationship,
                phone=body.guardian.phone,
            )
            if body.guardian
            else None,
            has_disability=body.has_disability,
            disability_types=list(body.disability_types),
            disability_other_text=body.disability_other_text,
            actor_id=current.sub,
            correlation_id=getattr(request.state, "correlation_id", None),
        )
    )
    return _serialize_summary(patient, current.role)


@router.get(
    "/portal/me", response_model=PortalDataOut, summary="Portal do paciente: suas consultas e horários pendentes"
)
def portal_me(
    current: CurrentUser = Depends(require_role(["PATIENT"])), repo: SqlAlchemyPatientRepository = Depends(_get_repo)
) -> PortalDataOut:
    data = repo.portal_data(current.sub)
    if not data:
        raise NotFoundError("Cadastro de paciente não encontrado.")
    return PortalDataOut(
        code=data.code,
        full_name=data.full_name,
        appointments=[
            PortalAppointmentOut(scheduled_at=a.scheduled_at, status=a.status, intern_name=a.intern_name)
            for a in data.appointments
        ],
        pending_slots=list(data.pending_slots),
    )
