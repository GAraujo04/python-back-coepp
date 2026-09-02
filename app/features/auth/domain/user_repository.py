"""Porta (interface) do repositório de usuários. Implementada em infrastructure/.

Porta features/auth/domain/user-repository.ts.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass
from typing import Literal

from .user import Role, User


@dataclass
class NewUser:
    role: Role
    full_name: str
    email: str
    password_hash: str
    crp: str | None = None
    ra: str | None = None
    phone: str | None = None
    department: str | None = None


@dataclass
class PendingSupervisorLink:
    id: str
    full_name: str
    email: str
    pending_supervisor_name: str


@dataclass
class TotvsResolveOutcome:
    """Equivalente ao union discriminado TotvsResolveOutcome do TS
    (returning/linked/created/link_failed) — uma classe só com `kind` +
    `user` opcional, em vez de 4 subclasses, porque é só isso que o
    chamador (InternLogin) de fato inspeciona."""

    kind: Literal["returning", "linked", "created", "link_failed"]
    user: User | None = None


class UserRepository(ABC):
    @abstractmethod
    def find_by_email(self, email: str) -> User | None: ...

    @abstractmethod
    def find_by_id(self, user_id: str) -> User | None: ...

    @abstractmethod
    def create(self, data: NewUser) -> User: ...

    @abstractmethod
    def list_by_role(self, role: Role) -> list[User]:
        """Lista usuários por papel (para seletores: coautores, agendamento). Dados mínimos."""
        ...

    @abstractmethod
    def list_pending_supervisor_links(self) -> list[PendingSupervisorLink]:
        """Estagiários que se autocadastraram com "Outro" em vez de um supervisor cadastrado."""
        ...

    @abstractmethod
    def link_supervisor(self, intern_id: str, supervisor_id: str) -> bool:
        """Vincula o estagiário a um supervisor cadastrado, limpando
        pending_supervisor_name. Só aplica se o estagiário ainda estiver
        pendente (retorna False se já resolvido)."""
        ...

    @abstractmethod
    def resolve_intern_from_totvs(
        self, totvs_usuario: str, full_name: str, link_email: str | None
    ) -> TotvsResolveOutcome:
        """Login do estagiário via TOTVS (ver InternLogin): acha a conta
        pelo usuário RM; se não achar e um e-mail foi informado, tenta
        vincular a uma conta INTERN existente ainda sem usuário RM; senão,
        cria uma conta nova (auto-provisionamento)."""
        ...

    @abstractmethod
    def is_intern_profile_complete(self, user_id: str) -> bool:
        """Perfil do estagiário está completo? (disciplina + supervisor/pendente
        + ao menos 1 janela de disponibilidade + ao menos 1 aceite de termo)."""
        ...
