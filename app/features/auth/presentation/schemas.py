"""Modelos Pydantic das rotas de auth (validação no boundary + geração do
OpenAPI nativo do FastAPI).

Porta features/auth/presentation/schemas.ts — JSON Schema (Fastify) vira
BaseModel (Pydantic), mesma filosofia de schema declarativo na borda.
"""

from __future__ import annotations

from pydantic import EmailStr, Field

from ....shared.http.camel_model import CamelModel


class UserPublic(CamelModel):
    id: str
    email: str
    full_name: str
    role: str
    # Só populado pra INTERN (login via TOTVS) — indica se falta completar
    # disciplina/supervisor/disponibilidade/termo. Ausente = não se aplica.
    profile_complete: bool | None = None


class LoginRequest(CamelModel):
    email: EmailStr
    password: str = Field(min_length=8, max_length=128)


class PatientLoginRequest(CamelModel):
    cpf: str
    birth_date: str


class InternLoginRequest(CamelModel):
    usuario_rm: str = Field(pattern=r"^\d{11}$")
    senha_rm: str = Field(min_length=1, max_length=128)
    # Só usado no 1º acesso, pra vincular a uma conta já cadastrada.
    link_email: EmailStr | None = None


class SessionResponse(CamelModel):
    access_token: str
    user: UserPublic


class RefreshResponse(CamelModel):
    access_token: str
