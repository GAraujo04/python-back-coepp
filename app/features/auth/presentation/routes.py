"""Rotas do slice auth. A composição (wiring) das dependências dos casos
de uso acontece aqui, na borda — domain/application permanecem livres de
framework.

Porta features/auth/presentation/routes.ts. Diferença estrutural real: no
Fastify, `new PrismaUserRepository(prisma)` etc. eram construídos UMA VEZ
no boot (o `prisma` é um pool compartilhado, seguro entre requests
concorrentes). Aqui, cada request ganha sua própria `Session` (não é
segura pra concorrência) — por isso os repositórios/casos de uso são
construídos DENTRO de funções de dependência do FastAPI, uma vez por
request, não uma vez só no boot.
"""

from __future__ import annotations

from collections.abc import Iterator
from datetime import UTC, datetime

from fastapi import APIRouter, Depends, Request, Response
from sqlalchemy.orm import Session

from ....shared.audit.audit_recorder import AuditRecorder
from ....shared.audit.sql_audit_recorder import SqlAuditRecorder
from ....shared.auth.jwt_auth import CurrentUser, get_current_user
from ....shared.config.env import load_env
from ....shared.db.session import get_session
from ....shared.errors.app_error import NotFoundError
from ..application.intern_login import InternLogin, InternLoginInput
from ..application.login_user import LoginInput, LoginUser
from ..application.logout_user import LogoutInput, LogoutUser
from ..application.patient_login import PatientLogin, PatientLoginInput
from ..application.ports import RefreshSessionMeta, TotvsAuthClient
from ..application.refresh_session import RefreshInput, RefreshSession
from ..domain.user_repository import UserRepository
from ..infrastructure.argon_password_hasher import ArgonPasswordHasher
from ..infrastructure.http_totvs_auth_client import HttpTotvsAuthClient, HttpTotvsAuthClientConfig
from ..infrastructure.in_memory_login_attempt_tracker import InMemoryLoginAttemptTracker
from ..infrastructure.jwt_access_token_signer import JwtAccessTokenSigner
from ..infrastructure.mock_totvs_auth_client import MockTotvsAuthClient
from ..infrastructure.sqlalchemy_patient_auth_repository import SqlAlchemyPatientAuthRepository
from ..infrastructure.sqlalchemy_refresh_token_store import SqlAlchemyRefreshTokenStore
from ..infrastructure.sqlalchemy_user_repository import SqlAlchemyUserRepository
from .schemas import (
    InternLoginRequest,
    LoginRequest,
    PatientLoginRequest,
    RefreshResponse,
    SessionResponse,
    UserPublic,
)

router = APIRouter(prefix="/api", tags=["auth"])

REFRESH_COOKIE = "pep_refresh"

# Bloqueio de tentativas precisa sobreviver entre requests (é o próprio
# ponto do rate-limit) — diferente da Session, que é por request. Único
# estado do módulo que fica fora da função de dependência por request;
# mesma vida útil de processo que tinha no Fastify (instanciado uma vez em
# authRoutes()).
#
# Um tracker POR MECANISMO de login, não um só compartilhado: as chaves já
# são disjuntas por prefixo ("rm:", "email:", "cpf:"), mas separar deixa
# explícito que a política de cada um é ajustável de forma independente —
# o login do paciente, que não tem senha, é o candidato natural a um
# limite mais estreito que os outros dois.
_intern_login_attempts = InMemoryLoginAttemptTracker()
_user_login_attempts = InMemoryLoginAttemptTracker()
_patient_login_attempts = InMemoryLoginAttemptTracker()


def _get_db() -> Iterator[Session]:
    with get_session() as session:
        yield session


def _get_users(db: Session = Depends(_get_db)) -> UserRepository:
    return SqlAlchemyUserRepository(db)


def _get_audit(db: Session = Depends(_get_db)) -> AuditRecorder:
    return SqlAuditRecorder(db)


def _get_access_token_signer() -> JwtAccessTokenSigner:
    env = load_env()
    return JwtAccessTokenSigner(env.JWT_SECRET, env.ACCESS_TOKEN_TTL_MINUTES)


def _get_refresh_tokens(db: Session = Depends(_get_db)) -> SqlAlchemyRefreshTokenStore:
    return SqlAlchemyRefreshTokenStore(db, load_env().REFRESH_TOKEN_TTL_DAYS)


def _get_totvs_client() -> TotvsAuthClient:
    env = load_env()
    if env.TOTVS_MOCK:
        return MockTotvsAuthClient()
    return HttpTotvsAuthClient(
        HttpTotvsAuthClientConfig(
            base_url=env.TOTVS_BASE_URL,
            timeout_seconds=env.TOTVS_TIMEOUT_SECONDS,
            sentenca=env.TOTVS_SENTENCA,
            coligada=env.TOTVS_COLIGADA,
            sistema=env.TOTVS_SISTEMA,
            param_nome=env.TOTVS_PARAM_NOME,
            param_com_aspas=env.TOTVS_PARAM_COM_ASPAS,
        )
    )


def _request_meta(request: Request) -> RefreshSessionMeta:
    return RefreshSessionMeta(
        ip=request.client.host if request.client else None, user_agent=request.headers.get("user-agent")
    )


def _set_refresh_cookie(response: Response, token: str, expires_at: datetime) -> None:
    is_prod = load_env().APP_ENV == "production"
    max_age = max(0, int((expires_at - datetime.now(UTC).replace(tzinfo=None)).total_seconds()))
    response.set_cookie(
        key=REFRESH_COOKIE,
        value=token,
        httponly=True,
        secure=is_prod,
        samesite="lax",
        path="/api/auth",
        max_age=max_age,
    )


@router.post(
    "/auth/login", response_model=SessionResponse, response_model_exclude_none=True, summary="Autentica e inicia sessão"
)
def login(
    body: LoginRequest,
    request: Request,
    response: Response,
    users: UserRepository = Depends(_get_users),
    audit: AuditRecorder = Depends(_get_audit),
    refresh_tokens: SqlAlchemyRefreshTokenStore = Depends(_get_refresh_tokens),
    access_tokens: JwtAccessTokenSigner = Depends(_get_access_token_signer),
) -> SessionResponse:
    use_case = LoginUser(users, ArgonPasswordHasher(), access_tokens, refresh_tokens, _user_login_attempts, audit)
    correlation_id = getattr(request.state, "correlation_id", None)
    result = use_case.execute(
        LoginInput(email=body.email, password=body.password, meta=_request_meta(request), correlation_id=correlation_id)
    )
    _set_refresh_cookie(response, result.refresh_token, result.refresh_expires_at)
    return SessionResponse(
        access_token=result.access_token,
        user=UserPublic(
            id=result.user.id, email=result.user.email, full_name=result.user.full_name, role=result.user.role
        ),
    )


@router.post(
    "/auth/intern-login",
    response_model=SessionResponse,
    response_model_exclude_none=True,
    summary="Login do estagiário via TOTVS RM (usuário/senha institucionais)",
)
def intern_login(
    body: InternLoginRequest,
    request: Request,
    response: Response,
    users: UserRepository = Depends(_get_users),
    audit: AuditRecorder = Depends(_get_audit),
    refresh_tokens: SqlAlchemyRefreshTokenStore = Depends(_get_refresh_tokens),
    access_tokens: JwtAccessTokenSigner = Depends(_get_access_token_signer),
    totvs: TotvsAuthClient = Depends(_get_totvs_client),
) -> SessionResponse:
    env = load_env()
    use_case = InternLogin(
        users, totvs, access_tokens, refresh_tokens, _intern_login_attempts, audit, env.TOTVS_TIPO_ALUNO
    )
    correlation_id = getattr(request.state, "correlation_id", None)
    result = use_case.execute(
        InternLoginInput(
            usuario_rm=body.usuario_rm,
            senha_rm=body.senha_rm,
            link_email=body.link_email,
            meta=_request_meta(request),
            correlation_id=correlation_id,
        )
    )
    _set_refresh_cookie(response, result.refresh_token, result.refresh_expires_at)
    return SessionResponse(
        access_token=result.access_token,
        user=UserPublic(
            id=result.user.id,
            email=result.user.email,
            full_name=result.user.full_name,
            role=result.user.role,
            profile_complete=result.user.profile_complete,
        ),
    )


@router.post(
    "/auth/patient-login",
    response_model=SessionResponse,
    response_model_exclude_none=True,
    summary="Login do paciente por CPF + data de nascimento (sem senha)",
)
def patient_login(
    body: PatientLoginRequest,
    request: Request,
    response: Response,
    db: Session = Depends(_get_db),
    audit: AuditRecorder = Depends(_get_audit),
    refresh_tokens: SqlAlchemyRefreshTokenStore = Depends(_get_refresh_tokens),
    access_tokens: JwtAccessTokenSigner = Depends(_get_access_token_signer),
) -> SessionResponse:
    use_case = PatientLogin(
        SqlAlchemyPatientAuthRepository(db), access_tokens, refresh_tokens, _patient_login_attempts, audit
    )
    correlation_id = getattr(request.state, "correlation_id", None)
    result = use_case.execute(
        PatientLoginInput(
            cpf=body.cpf, birth_date=body.birth_date, meta=_request_meta(request), correlation_id=correlation_id
        )
    )
    _set_refresh_cookie(response, result.refresh_token, result.refresh_expires_at)
    return SessionResponse(
        access_token=result.access_token,
        user=UserPublic(
            id=result.user.id, email=result.user.email, full_name=result.user.full_name, role=result.user.role
        ),
    )


@router.post("/auth/refresh", response_model=RefreshResponse, summary="Renova o access token (rotaciona o refresh)")
def refresh(
    request: Request,
    response: Response,
    users: UserRepository = Depends(_get_users),
    audit: AuditRecorder = Depends(_get_audit),
    refresh_tokens: SqlAlchemyRefreshTokenStore = Depends(_get_refresh_tokens),
    access_tokens: JwtAccessTokenSigner = Depends(_get_access_token_signer),
) -> RefreshResponse:
    use_case = RefreshSession(users, access_tokens, refresh_tokens, audit)
    correlation_id = getattr(request.state, "correlation_id", None)
    token = request.cookies.get(REFRESH_COOKIE, "")
    result = use_case.execute(
        RefreshInput(refresh_token=token, meta=_request_meta(request), correlation_id=correlation_id)
    )
    _set_refresh_cookie(response, result.refresh_token, result.refresh_expires_at)
    return RefreshResponse(access_token=result.access_token)


@router.post("/auth/logout", status_code=204, summary="Encerra a sessão")
def logout(
    request: Request,
    response: Response,
    audit: AuditRecorder = Depends(_get_audit),
    refresh_tokens: SqlAlchemyRefreshTokenStore = Depends(_get_refresh_tokens),
) -> Response:
    use_case = LogoutUser(refresh_tokens, audit)
    correlation_id = getattr(request.state, "correlation_id", None)
    use_case.execute(
        LogoutInput(
            refresh_token=request.cookies.get(REFRESH_COOKIE),
            correlation_id=correlation_id,
            ip=request.client.host if request.client else None,
            user_agent=request.headers.get("user-agent"),
        )
    )
    response.delete_cookie(REFRESH_COOKIE, path="/api/auth")
    response.status_code = 204
    return response


@router.get(
    "/auth/me", response_model=UserPublic, response_model_exclude_none=True, summary="Dados do usuário autenticado"
)
def me(current: CurrentUser = Depends(get_current_user), users: UserRepository = Depends(_get_users)) -> UserPublic:
    user = users.find_by_id(current.sub)
    if not user:
        raise NotFoundError("Usuário não encontrado.")
    profile_complete = users.is_intern_profile_complete(user.id) if user.role == "INTERN" else None
    return UserPublic(
        id=current.sub, email=current.email, full_name=user.full_name, role=user.role, profile_complete=profile_complete
    )
