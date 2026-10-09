"""Rotas do pareamento: executar (Admin), visualizar (Admin/Supervisor),
sugerir e criar manualmente (Admin).

Porta features/matching/presentation/routes.ts.
"""

from __future__ import annotations

from collections.abc import Iterator

from fastapi import APIRouter, Depends, Request
from fastapi.responses import JSONResponse
from sqlalchemy.orm import Session

from ....shared.audit.audit_recorder import AuditEvent, AuditRecorder
from ....shared.audit.sql_audit_recorder import SqlAuditRecorder
from ....shared.auth.jwt_auth import CurrentUser, require_role
from ....shared.db.session import get_session
from ....shared.http.utc_datetime import to_iso_utc
from ....shared.privacy.patient_name import patient_name_for
from ..application.create_manual_match import CreateManualMatch, CreateManualMatchInput
from ..application.run_matching import RunMatching
from ..application.suggest_matches import SuggestMatches
from ..infrastructure.sqlalchemy_matching_repository import SqlAlchemyMatchingRepository
from .schemas import (
    CreateManualMatchRequest,
    CreateManualMatchResponse,
    MatchResultOut,
    MatchSuggestionOut,
    MatchViewOut,
    PendingMatchRequestOut,
    RunMatchingResponse,
    WarningOut,
)

router = APIRouter(prefix="/api", tags=["matching"])


def _get_db() -> Iterator[Session]:
    with get_session() as session:
        yield session


def _get_repo(db: Session = Depends(_get_db)) -> SqlAlchemyMatchingRepository:
    return SqlAlchemyMatchingRepository(db)


def _get_audit(db: Session = Depends(_get_db)) -> AuditRecorder:
    return SqlAuditRecorder(db)


@router.post(
    "/matching/run",
    response_model=RunMatchingResponse,
    summary="Executa o pareamento por disponibilidade (Administrativo)",
)
def run_matching(
    request: Request,
    current: CurrentUser = Depends(require_role(["ADMIN"])),
    repo: SqlAlchemyMatchingRepository = Depends(_get_repo),
    audit: AuditRecorder = Depends(_get_audit),
) -> RunMatchingResponse:
    use_case = RunMatching(repo, audit)
    results = use_case.execute(current.sub, getattr(request.state, "correlation_id", None))
    return RunMatchingResponse(
        matched=len(results),
        results=[
            MatchResultOut(
                appointment_id=r.appointment_id,
                intern_id=r.intern_id,
                patient_id=r.patient_id,
                room_id=r.room_id,
                scheduled_at=r.scheduled_at,
            )
            for r in results
        ],
    )


@router.get(
    "/matching/matches",
    response_model=list[MatchViewOut],
    summary="Lista as consultas/pareamentos (Admin e Supervisor)",
)
def list_matches(
    current: CurrentUser = Depends(require_role(["ADMIN", "SUPERVISOR"])),
    repo: SqlAlchemyMatchingRepository = Depends(_get_repo),
) -> list[MatchViewOut]:
    matches = repo.list_matches(current.sub)
    return [
        MatchViewOut(
            appointment_id=m.appointment_id,
            scheduled_at=to_iso_utc(m.scheduled_at),
            status=m.status,
            intern_name=m.intern_name,
            patient_name=patient_name_for(current.role, m.patient_name),
            patient_code=m.patient_code,
            room_name=m.room_name,
        )
        for m in matches
    ]


@router.get(
    "/matching/suggestions",
    response_model=list[MatchSuggestionOut],
    summary="Pares que o pareamento automático formaria, sem persistir (Administrativo)",
)
def suggestions(
    current: CurrentUser = Depends(require_role(["ADMIN"])), repo: SqlAlchemyMatchingRepository = Depends(_get_repo)
) -> list[MatchSuggestionOut]:
    use_case = SuggestMatches(repo)
    return [
        MatchSuggestionOut(
            patient_id=s.patient_id,
            patient_name=s.patient_name,
            intern_id=s.intern_id,
            intern_name=s.intern_name,
            room_id=s.room_id,
            room_name=s.room_name,
            scheduled_at=s.scheduled_at,
        )
        for s in use_case.execute()
    ]


@router.get(
    "/matching/pending-requests",
    response_model=list[PendingMatchRequestOut],
    summary="Alertas de fallback por aproximação — pacientes sem match exato nesta rodada (Administrativo)",
)
def pending_requests(
    current: CurrentUser = Depends(require_role(["ADMIN"])), repo: SqlAlchemyMatchingRepository = Depends(_get_repo)
) -> list[PendingMatchRequestOut]:
    rows = repo.list_pending_match_requests()
    return [
        PendingMatchRequestOut(
            id=r.id,
            patient_name=r.patient_name,
            suggested_intern_name=r.suggested_intern_name,
            suggested_at=to_iso_utc(r.suggested_at) if r.suggested_at else None,
            status=r.status,
            created_at=to_iso_utc(r.created_at),
        )
        for r in rows
    ]


@router.patch(
    "/matching/pending-requests/{request_id}/resolve",
    status_code=204,
    summary="Marca o alerta de fallback como resolvido — equipe já contatou o paciente (Administrativo)",
)
def resolve_pending_request(
    request_id: str,
    request: Request,
    current: CurrentUser = Depends(require_role(["ADMIN"])),
    repo: SqlAlchemyMatchingRepository = Depends(_get_repo),
    audit: AuditRecorder = Depends(_get_audit),
) -> None:
    repo.resolve_pending_match_request(request_id)
    audit.record(
        AuditEvent(
            actor_id=current.sub,
            action="UPDATE",
            resource_type="pending_match_request",
            resource_id=request_id,
            correlation_id=getattr(request.state, "correlation_id", None),
            diff={"event": "resolved"},
        )
    )


@router.post(
    "/matching/manual",
    status_code=201,
    # response_model=None: retorno é ou o 201 (CreateManualMatchResponse)
    # ou um JSONResponse 409 cru (avisos pendentes de confirmação) — união
    # que o FastAPI não consegue inferir sozinho como um único response_model.
    response_model=None,
    summary="Cria um match manual, sobrepondo a sugestão automática (Administrativo)",
)
def create_manual_match(
    body: CreateManualMatchRequest,
    request: Request,
    current: CurrentUser = Depends(require_role(["ADMIN"])),
    repo: SqlAlchemyMatchingRepository = Depends(_get_repo),
    audit: AuditRecorder = Depends(_get_audit),
) -> CreateManualMatchResponse | JSONResponse:
    use_case = CreateManualMatch(repo, audit)
    result = use_case.execute(
        CreateManualMatchInput(
            actor_id=current.sub,
            patient_id=body.patient_id,
            intern_id=body.intern_id,
            scheduled_at=body.scheduled_at,
            room_id=body.room_id,
            acknowledge_warnings=body.acknowledge_warnings,
            correlation_id=getattr(request.state, "correlation_id", None),
        )
    )
    if not result.confirmed:
        # Avisos pendentes de confirmação — corpo tem "warnings" além dos
        # campos padrão de erro (não passa pelo error_handler genérico,
        # já que isso não é uma exceção — é um resultado estruturado).
        return JSONResponse(
            status_code=409,
            content={
                "code": "conflict",
                "message": "Há conflitos que precisam ser confirmados antes de criar o match manual.",
                "correlation_id": getattr(request.state, "correlation_id", None),
                "warnings": [{"code": w.code, "message": w.message} for w in result.warnings],
            },
        )
    assert result.appointment_id is not None  # garantido por CreateManualMatch quando confirmed=True
    return CreateManualMatchResponse(
        appointment_id=result.appointment_id,
        warnings=[WarningOut(code=w.code, message=w.message) for w in result.warnings],
    )
