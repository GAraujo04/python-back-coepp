"""Rotas de autocadastro. A maioria é pública (sem autenticação) — exceção
é PATCH /enrollment/complete-profile e as rotas de disponibilidade, que
exigem sessão de estagiário (só mexem no PRÓPRIO cadastro, nunca no de
outra pessoa). As públicas ficam sob o rate limit por IP do middleware
(shared/http/rate_limit.py), com um balde próprio e mais estreito —
aqui o abuso é o volume de cadastros, não a tentativa de adivinhar
credencial.

Porta features/enrollment/presentation/routes.ts.
"""

from __future__ import annotations

from collections.abc import Iterator

from fastapi import APIRouter, Depends, Request
from sqlalchemy.orm import Session

from ....shared.audit.audit_recorder import AuditRecorder
from ....shared.audit.sql_audit_recorder import SqlAuditRecorder
from ....shared.auth.jwt_auth import CurrentUser, require_role
from ....shared.db.session import get_session
from ....shared.scheduling.availability_window import AvailabilityWindowInput
from ..application.availability_lock import RequestAvailabilityChange, utcnow
from ..application.complete_intern_profile import CompleteInternProfile, CompleteInternProfileInput
from ..application.register_patient_public import RegisterPatientPublic, RegisterPatientPublicInput
from ..application.register_student_public import RegisterStudentPublic, RegisterStudentPublicInput
from ..application.update_availability_windows import UpdateAvailabilityWindows, UpdateAvailabilityWindowsInput
from ..infrastructure.responsibility_term import read_responsibility_term
from ..infrastructure.sqlalchemy_availability_lock_repository import SqlAlchemyAvailabilityLockRepository
from ..infrastructure.sqlalchemy_enrollment_repository import GuardianInput, SqlAlchemyEnrollmentRepository
from .schemas import (
    AvailabilityChangeRequestIn,
    AvailabilityLockOut,
    AvailabilityWindowIn,
    AvailabilityWindowOut,
    CompleteInternProfileRequest,
    DisciplinaOptionOut,
    RegisterPatientRequest,
    RegisterPatientResponse,
    RegisterStudentRequest,
    RegisterStudentResponse,
    RegistrationOptionsOut,
    ResponsibilityTermOut,
    SupervisorOptionOut,
    UpdateAvailabilityWindowsRequest,
)

router = APIRouter(prefix="/api", tags=["enrollment"])


def _get_db() -> Iterator[Session]:
    with get_session() as session:
        yield session


def _get_repo(db: Session = Depends(_get_db)) -> SqlAlchemyEnrollmentRepository:
    return SqlAlchemyEnrollmentRepository(db)


def _get_audit(db: Session = Depends(_get_db)) -> AuditRecorder:
    return SqlAuditRecorder(db)


def _get_lock_repo(db: Session = Depends(_get_db)) -> SqlAlchemyAvailabilityLockRepository:
    return SqlAlchemyAvailabilityLockRepository(db)


def _to_domain_windows(windows: list[AvailabilityWindowIn]) -> list[AvailabilityWindowInput]:
    return [AvailabilityWindowInput(weekday=w.weekday, start_time=w.start_time, end_time=w.end_time) for w in windows]


@router.post(
    "/register/patient",
    response_model=RegisterPatientResponse,
    status_code=201,
    summary="Autocadastro público de paciente (dados + login + disponibilidade)",
)
def register_patient(
    body: RegisterPatientRequest,
    request: Request,
    repo: SqlAlchemyEnrollmentRepository = Depends(_get_repo),
    audit: AuditRecorder = Depends(_get_audit),
) -> RegisterPatientResponse:
    use_case = RegisterPatientPublic(repo, audit)
    patient_id, code = use_case.execute(
        RegisterPatientPublicInput(
            full_name=body.full_name,
            email=body.email,
            cpf=body.cpf,
            birth_date=body.birth_date,
            windows=_to_domain_windows(body.windows),
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
            correlation_id=getattr(request.state, "correlation_id", None),
        )
    )
    return RegisterPatientResponse(id=patient_id, code=code)


@router.post(
    "/register/student",
    response_model=RegisterStudentResponse,
    status_code=201,
    summary="Autocadastro público de aluno/estagiário (dados + disponibilidade)",
)
def register_student(
    body: RegisterStudentRequest,
    request: Request,
    repo: SqlAlchemyEnrollmentRepository = Depends(_get_repo),
    audit: AuditRecorder = Depends(_get_audit),
) -> RegisterStudentResponse:
    use_case = RegisterStudentPublic(repo, audit, read_responsibility_term)
    user_id = use_case.execute(
        RegisterStudentPublicInput(
            full_name=body.full_name,
            email=body.email,
            ra=body.ra,
            password=body.password,
            disciplina_id=body.disciplina_id,
            windows=_to_domain_windows(body.windows),
            accepted_term_version=body.accepted_term_version,
            phone=body.phone,
            academic_supervisor_id=body.academic_supervisor_id,
            pending_supervisor_name=body.pending_supervisor_name,
            periodo=body.periodo,
            turma=body.turma,
            correlation_id=getattr(request.state, "correlation_id", None),
        )
    )
    return RegisterStudentResponse(id=user_id)


@router.get(
    "/register/options",
    response_model=RegistrationOptionsOut,
    summary="Opções para o autocadastro de aluno (supervisores + disciplinas)",
)
def registration_options(repo: SqlAlchemyEnrollmentRepository = Depends(_get_repo)) -> RegistrationOptionsOut:
    options = repo.list_options()
    return RegistrationOptionsOut(
        supervisors=[SupervisorOptionOut(id=s.id, full_name=s.full_name) for s in options.supervisors],
        disciplinas=[DisciplinaOptionOut(id=d.id, name=d.name) for d in options.disciplinas],
    )


@router.get(
    "/register/responsibility-term",
    response_model=ResponsibilityTermOut,
    summary="Termo de responsabilidade vigente (versão + conteúdo), exibido no cadastro do aluno",
)
def responsibility_term() -> ResponsibilityTermOut:
    term = read_responsibility_term()
    return ResponsibilityTermOut(version=term.version, content=term.content)


@router.patch(
    "/enrollment/complete-profile",
    status_code=204,
    summary="Completa o cadastro do estagiário autenticado (1º acesso via TOTVS ou enquanto perfil incompleto)",
)
def complete_profile(
    body: CompleteInternProfileRequest,
    request: Request,
    current: CurrentUser = Depends(require_role(["INTERN"])),
    repo: SqlAlchemyEnrollmentRepository = Depends(_get_repo),
    audit: AuditRecorder = Depends(_get_audit),
) -> None:
    use_case = CompleteInternProfile(repo, audit, read_responsibility_term)
    use_case.execute(
        CompleteInternProfileInput(
            user_id=current.sub,
            disciplina_id=body.disciplina_id,
            windows=_to_domain_windows(body.windows),
            accepted_term_version=body.accepted_term_version,
            academic_supervisor_id=body.academic_supervisor_id,
            pending_supervisor_name=body.pending_supervisor_name,
            periodo=body.periodo,
            turma=body.turma,
            ra=body.ra,
            phone=body.phone,
            email=body.email,
            correlation_id=getattr(request.state, "correlation_id", None),
        )
    )


@router.get(
    "/enrollment/availability-windows",
    response_model=list[AvailabilityWindowOut],
    summary="Disponibilidade recorrente atual do estagiário logado",
)
def get_availability_windows(
    current: CurrentUser = Depends(require_role(["INTERN"])),
    repo: SqlAlchemyEnrollmentRepository = Depends(_get_repo),
) -> list[AvailabilityWindowOut]:
    windows = repo.get_availability_windows(current.sub)
    return [AvailabilityWindowOut(weekday=w.weekday, start_time=w.start_time, end_time=w.end_time) for w in windows]


@router.put(
    "/enrollment/availability-windows",
    status_code=204,
    summary="Substitui a disponibilidade do estagiário logado — só com liberação do supervisor (403 se travada)",
)
def put_availability_windows(
    body: UpdateAvailabilityWindowsRequest,
    request: Request,
    current: CurrentUser = Depends(require_role(["INTERN"])),
    repo: SqlAlchemyEnrollmentRepository = Depends(_get_repo),
    lock: SqlAlchemyAvailabilityLockRepository = Depends(_get_lock_repo),
    audit: AuditRecorder = Depends(_get_audit),
) -> None:
    use_case = UpdateAvailabilityWindows(repo, lock, audit)
    use_case.execute(
        UpdateAvailabilityWindowsInput(
            user_id=current.sub,
            windows=_to_domain_windows(body.windows),
            correlation_id=getattr(request.state, "correlation_id", None),
        )
    )


@router.get(
    "/enrollment/availability-lock",
    response_model=AvailabilityLockOut,
    summary="Situação da trava de disponibilidade do estagiário logado (editável? pedido pendente?)",
)
def get_availability_lock(
    current: CurrentUser = Depends(require_role(["INTERN"])),
    lock: SqlAlchemyAvailabilityLockRepository = Depends(_get_lock_repo),
) -> AvailabilityLockOut:
    state = lock.get_state(current.sub)
    now = utcnow()
    if state is None:  # token de INTERN sem linha INTERN: trata como travado, sem pedido
        return AvailabilityLockOut(editable=False, unlocked_until=None, requested_at=None, request_reason=None)
    return AvailabilityLockOut(
        editable=state.editable(now),
        unlocked_until=state.unlocked_until if state.editable(now) else None,
        requested_at=state.requested_at,
        request_reason=state.request_reason,
    )


@router.post(
    "/enrollment/availability-change-request",
    status_code=204,
    summary="Estagiário pede ao supervisor a liberação para alterar a disponibilidade",
)
def request_availability_change(
    body: AvailabilityChangeRequestIn,
    request: Request,
    current: CurrentUser = Depends(require_role(["INTERN"])),
    lock: SqlAlchemyAvailabilityLockRepository = Depends(_get_lock_repo),
    audit: AuditRecorder = Depends(_get_audit),
) -> None:
    RequestAvailabilityChange(lock, audit).execute(
        current.sub, body.reason, getattr(request.state, "correlation_id", None)
    )
