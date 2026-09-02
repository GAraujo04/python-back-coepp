"""Rotas do slice screening (triagem). Guards RBAC no boundary; RLS por
vínculo no banco.

Porta features/screening/presentation/routes.ts.
"""

from __future__ import annotations

from collections.abc import Iterator

from fastapi import APIRouter, Depends, Request
from sqlalchemy.orm import Session

from ....shared.audit.audit_recorder import AuditRecorder
from ....shared.audit.sql_audit_recorder import SqlAuditRecorder
from ....shared.auth.jwt_auth import CurrentUser, get_current_user, require_role
from ....shared.db.session import get_session
from ..application.create_screening import CreateScreening, CreateScreeningInput
from ..application.delete_screening import DeleteScreening
from ..application.query_screenings import GetScreening, ListScreenings
from ..application.update_screening_draft import UpdateDraftInput, UpdateScreeningDraft
from ..domain.screening_repository import AccessContext, ScreeningRecord, ScreeningRepository
from ..infrastructure.sqlalchemy_screening_repository import SqlAlchemyScreeningRepository
from .schemas import CreateScreeningRequest, ScreeningOut, SignatureOut, UpdateDraftRequest

router = APIRouter(prefix="/api", tags=["screening"])


def _get_db() -> Iterator[Session]:
    with get_session() as session:
        yield session


def _get_repo(db: Session = Depends(_get_db)) -> ScreeningRepository:
    return SqlAlchemyScreeningRepository(db)


def _get_audit(db: Session = Depends(_get_db)) -> AuditRecorder:
    return SqlAuditRecorder(db)


def _ctx_of(user: CurrentUser) -> AccessContext:
    return AccessContext(user_id=user.sub, role=user.role)


def _serialize(s: ScreeningRecord) -> ScreeningOut:
    return ScreeningOut(
        id=s.id,
        numero=s.numero,
        type=s.type,
        status=s.status,
        version=s.version,
        patient_id=s.patient_id,
        author_id=s.author_id,
        co_author_ids=s.co_author_ids,
        content=s.content,
        signatures=[
            SignatureOut(
                signer_name=sig.signer_name,
                signer_role=sig.signer_role,
                signer_ref=sig.signer_ref,
                provider=sig.provider,
                signed_at=sig.signed_at,
            )
            for sig in s.signatures
        ],
        created_at=s.created_at,
        updated_at=s.updated_at,
    )


@router.post(
    "/screenings", response_model=ScreeningOut, status_code=201, summary="Cria uma triagem (rascunho) — Estagiário"
)
def create_screening(
    body: CreateScreeningRequest,
    request: Request,
    current: CurrentUser = Depends(require_role(["INTERN"])),
    repo: ScreeningRepository = Depends(_get_repo),
    audit: AuditRecorder = Depends(_get_audit),
) -> ScreeningOut:
    use_case = CreateScreening(repo, audit)
    screening = use_case.execute(
        CreateScreeningInput(
            actor=_ctx_of(current),
            type=body.type,
            patient_id=body.patient_id,
            co_author_ids=list(body.co_author_ids),
            content=dict(body.content),
            correlation_id=getattr(request.state, "correlation_id", None),
        )
    )
    return _serialize(screening)


@router.get("/screenings", response_model=list[ScreeningOut], summary="Lista triagens visíveis (escopo por RLS)")
def list_screenings(
    current: CurrentUser = Depends(get_current_user), repo: ScreeningRepository = Depends(_get_repo)
) -> list[ScreeningOut]:
    use_case = ListScreenings(repo)
    return [_serialize(s) for s in use_case.execute(_ctx_of(current))]


@router.get("/screenings/{screening_id}", response_model=ScreeningOut, summary="Obtém uma triagem (leitura auditada)")
def get_screening(
    screening_id: str,
    request: Request,
    current: CurrentUser = Depends(get_current_user),
    repo: ScreeningRepository = Depends(_get_repo),
    audit: AuditRecorder = Depends(_get_audit),
) -> ScreeningOut:
    use_case = GetScreening(repo, audit)
    screening = use_case.execute(_ctx_of(current), screening_id, getattr(request.state, "correlation_id", None))
    return _serialize(screening)


@router.patch(
    "/screenings/{screening_id}",
    response_model=ScreeningOut,
    summary="Salva o rascunho da triagem (auto-save) — Estagiário",
)
def update_draft(
    screening_id: str,
    body: UpdateDraftRequest,
    request: Request,
    current: CurrentUser = Depends(require_role(["INTERN"])),
    repo: ScreeningRepository = Depends(_get_repo),
    audit: AuditRecorder = Depends(_get_audit),
) -> ScreeningOut:
    use_case = UpdateScreeningDraft(repo, audit)
    updated = use_case.execute(
        UpdateDraftInput(
            actor=_ctx_of(current),
            screening_id=screening_id,
            content=dict(body.content),
            expected_version=body.expected_version,
            correlation_id=getattr(request.state, "correlation_id", None),
        )
    )
    return _serialize(updated)


@router.delete(
    "/screenings/{screening_id}",
    status_code=204,
    summary="Remove um documento — só RASCUNHO próprio/coautoria (ADMIN remove qualquer status)",
)
def delete_screening(
    screening_id: str,
    request: Request,
    current: CurrentUser = Depends(require_role(["INTERN", "ADMIN"])),
    repo: ScreeningRepository = Depends(_get_repo),
    audit: AuditRecorder = Depends(_get_audit),
) -> None:
    use_case = DeleteScreening(repo, audit)
    use_case.execute(_ctx_of(current), screening_id, getattr(request.state, "correlation_id", None))
