"""Cadastro de usuário pelo Administrativo (aluno/estagiário ou supervisor
docente). Regras: estagiário exige RA; supervisor exige CRP; e-mail único.

Porta features/auth/application/register-user.ts.
"""

from __future__ import annotations

from dataclasses import dataclass

from ....shared.audit.audit_recorder import AuditEvent, AuditRecorder
from ....shared.errors.app_error import ConflictError, ValidationError
from ..domain.user import Email, Role, User
from ..domain.user_repository import NewUser, UserRepository
from .ports import PasswordHasher


@dataclass
class RegisterUserInput:
    actor_id: str
    role: Role
    full_name: str
    email: str
    password: str
    crp: str | None = None
    ra: str | None = None
    phone: str | None = None
    department: str | None = None
    correlation_id: str | None = None


class RegisterUser:
    def __init__(self, users: UserRepository, hasher: PasswordHasher, audit: AuditRecorder) -> None:
        self._users = users
        self._hasher = hasher
        self._audit = audit

    def execute(self, input: RegisterUserInput) -> User:
        email = Email.create(input.email)

        if input.role == "INTERN" and not (input.ra or "").strip():
            raise ValidationError("Estagiário deve possuir RA (Registro Acadêmico).")
        if input.role == "SUPERVISOR" and not (input.crp or "").strip():
            raise ValidationError("Supervisor deve possuir CRP.")
        if len(input.password) < 8:
            raise ValidationError("A senha deve ter ao menos 8 caracteres.")
        if self._users.find_by_email(email.value):
            raise ConflictError("Já existe um usuário com este e-mail.")

        password_hash = self._hasher.hash(input.password)
        user = self._users.create(
            NewUser(
                role=input.role,
                full_name=input.full_name,
                email=email.value,
                password_hash=password_hash,
                crp=input.crp,
                ra=input.ra,
                phone=input.phone,
                department=input.department,
            )
        )

        self._audit.record(
            AuditEvent(
                actor_id=input.actor_id,
                action="CREATE",
                resource_type="user",
                resource_id=user.id,
                correlation_id=input.correlation_id,
            )
        )

        return user
