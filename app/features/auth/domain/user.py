"""Entidade User (agregado) + Value Object Email.

Porta features/auth/domain/user.ts. Regra de negócio preservada:
SUPERVISOR precisa de CRP.
"""

from __future__ import annotations

import re
from typing import Literal

from ....shared.errors.app_error import ValidationError

Role = Literal["PATIENT", "INTERN", "SUPERVISOR", "ADMIN"]

_EMAIL_RE = re.compile(r"^[^\s@]+@[^\s@]+\.[^\s@]+$")


class Email:
    """Value Object de e-mail — normaliza (lowercase/trim) e valida no
    boundary do domínio. Construtor "privado" via factory `create`, mesmo
    espírito do `private constructor` + `static create` do TS (Python não
    tem construtor privado de verdade, mas a convenção de só instanciar via
    `Email.create` é a mesma)."""

    __slots__ = ("value",)

    def __init__(self, value: str) -> None:
        self.value = value

    @staticmethod
    def create(raw: str) -> Email:
        normalized = raw.strip().lower()
        if not _EMAIL_RE.match(normalized):
            raise ValidationError("E-mail inválido.", {"email": raw})
        return Email(normalized)

    def __eq__(self, other: object) -> bool:
        return isinstance(other, Email) and self.value == other.value

    def __repr__(self) -> str:
        return f"Email({self.value!r})"


class User:
    """Entidade User (agregado). Guarda o hash da senha (opaco ao domínio —
    o algoritmo é detalhe de infraestrutura)."""

    def __init__(
        self,
        id: str,
        email: Email,
        full_name: str,
        role: Role,
        password_hash: str | None,
        crp: str | None,
        active: bool,
        ra: str | None = None,
        phone: str | None = None,
        department: str | None = None,
    ) -> None:
        if role == "SUPERVISOR" and not crp:
            raise ValidationError("Supervisor deve possuir CRP.", {"userId": id})
        self.id = id
        self.email = email
        self.full_name = full_name
        self.role: Role = role
        self.password_hash = password_hash
        self.crp = crp
        self.active = active
        self.ra = ra
        self.phone = phone
        self.department = department

    def can_authenticate(self) -> bool:
        return self.active
