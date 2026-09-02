"""Rotas de gestão de usuários (cadastro pelo Administrativo + listagem
para seletores).

Porta features/auth/presentation/user-routes.ts.
"""

from __future__ import annotations

from fastapi import APIRouter, Depends, Request

from ....shared.audit.audit_recorder import AuditRecorder
from ....shared.auth.jwt_auth import CurrentUser, get_current_user, require_role
from ....shared.http.camel_model import CamelModel
from ..application.link_pending_supervisor import LinkPendingSupervisor, LinkPendingSupervisorInput
from ..application.register_user import RegisterUser, RegisterUserInput
from ..domain.user import Role, User
from ..domain.user_repository import UserRepository
from ..infrastructure.argon_password_hasher import ArgonPasswordHasher
from .routes import _get_audit, _get_users  # reusa as mesmas dependências por-request da slice auth

router = APIRouter(prefix="/api", tags=["users"])


class CreateUserRequest(CamelModel):
    role: Role
    full_name: str
    email: str
    password: str
    crp: str | None = None
    ra: str | None = None
    phone: str | None = None
    department: str | None = None


class LinkSupervisorRequest(CamelModel):
    supervisor_id: str


class UserPublicOut(CamelModel):
    id: str
    full_name: str
    email: str
    role: str
    crp: str | None
    ra: str | None
    phone: str | None
    department: str | None
    active: bool


class PendingSupervisorOut(CamelModel):
    id: str
    full_name: str
    email: str
    pending_supervisor_name: str


def _to_public(u: User) -> UserPublicOut:
    return UserPublicOut(
        id=u.id,
        full_name=u.full_name,
        email=u.email.value,
        role=u.role,
        crp=u.crp,
        ra=u.ra,
        phone=u.phone,
        department=u.department,
        active=u.active,
    )


@router.post(
    "/users",
    response_model=UserPublicOut,
    status_code=201,
    summary="Cadastra aluno/estagiário ou supervisor (Administrativo)",
)
def create_user(
    body: CreateUserRequest,
    request: Request,
    current: CurrentUser = Depends(require_role(["ADMIN"])),
    users: UserRepository = Depends(_get_users),
    audit: AuditRecorder = Depends(_get_audit),
) -> UserPublicOut:
    use_case = RegisterUser(users, ArgonPasswordHasher(), audit)
    user = use_case.execute(
        RegisterUserInput(
            actor_id=current.sub,
            role=body.role,
            full_name=body.full_name,
            email=body.email,
            password=body.password,
            crp=body.crp,
            ra=body.ra,
            phone=body.phone,
            department=body.department,
            correlation_id=getattr(request.state, "correlation_id", None),
        )
    )
    return _to_public(user)


@router.get(
    "/users", response_model=list[UserPublicOut], summary="Lista usuários por papel (seletores de coautor/agendamento)"
)
def list_users(
    role: Role | None = None,
    current: CurrentUser = Depends(get_current_user),
    users: UserRepository = Depends(_get_users),
) -> list[UserPublicOut]:
    if not role:
        return []
    return [_to_public(u) for u in users.list_by_role(role)]


@router.get(
    "/users/pending-supervisors",
    response_model=list[PendingSupervisorOut],
    summary='Lista estagiários com supervisor pendente (opção "Outro" no autocadastro)',
)
def pending_supervisors(
    current: CurrentUser = Depends(require_role(["ADMIN"])), users: UserRepository = Depends(_get_users)
) -> list[PendingSupervisorOut]:
    return [
        PendingSupervisorOut(
            id=p.id, full_name=p.full_name, email=p.email, pending_supervisor_name=p.pending_supervisor_name
        )
        for p in users.list_pending_supervisor_links()
    ]


@router.patch(
    "/users/{user_id}/link-supervisor",
    status_code=204,
    summary="Vincula um estagiário pendente a um supervisor cadastrado (Administrativo)",
)
def link_supervisor(
    user_id: str,
    body: LinkSupervisorRequest,
    request: Request,
    current: CurrentUser = Depends(require_role(["ADMIN"])),
    users: UserRepository = Depends(_get_users),
    audit: AuditRecorder = Depends(_get_audit),
) -> None:
    use_case = LinkPendingSupervisor(users, audit)
    use_case.execute(
        LinkPendingSupervisorInput(
            actor_id=current.sub,
            intern_id=user_id,
            supervisor_id=body.supervisor_id,
            correlation_id=getattr(request.state, "correlation_id", None),
        )
    )
