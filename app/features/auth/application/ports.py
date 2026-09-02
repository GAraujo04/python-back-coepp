"""Portas (interfaces) do caso de uso de autenticação.

Porta features/auth/application/ports.ts.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass
from datetime import datetime

from ..domain.user import Role


class PasswordHasher(ABC):
    """Verificação de senha (argon2 na infra). Domínio/aplicação não conhecem o algoritmo."""

    @abstractmethod
    def verify(self, hash_: str, plaintext: str) -> bool: ...

    @abstractmethod
    def hash(self, plaintext: str) -> str: ...


@dataclass
class PatientAccount:
    user_id: str
    email: str
    full_name: str
    birth_date: str | None  # yyyy-mm-dd


class PatientAuthLookup(ABC):
    """Busca a conta do paciente pelo CPF (via índice cego). Login por CPF + nascimento."""

    @abstractmethod
    def find_by_cpf(self, cpf: str) -> PatientAccount | None: ...


@dataclass
class AccessTokenPayload:
    sub: str
    role: Role
    email: str


class AccessTokenSigner(ABC):
    """Assina o access token (JWT curto)."""

    @abstractmethod
    def sign(self, payload: AccessTokenPayload) -> str: ...


@dataclass
class RefreshSessionMeta:
    ip: str | None = None
    user_agent: str | None = None


@dataclass
class IssuedRefreshToken:
    token: str  # valor opaco enviado ao cliente (cookie httpOnly)
    expires_at: datetime


class RefreshTokenStore(ABC):
    """Armazena o HASH do refresh token (nunca o token em si)."""

    @abstractmethod
    def issue(self, user_id: str, meta: RefreshSessionMeta) -> IssuedRefreshToken: ...

    @abstractmethod
    def rotate(self, old_token: str, meta: RefreshSessionMeta) -> tuple[str, IssuedRefreshToken]:
        """Valida o refresh token e o rotaciona (revoga o antigo, emite um novo). Retorna (user_id, issued)."""
        ...

    @abstractmethod
    def revoke(self, token: str) -> None: ...


# --- Autenticação do estagiário via TOTVS RM ------------------------------


class TotvsInvalidCredentialsError(Exception):
    """Erro de credencial inválida na chamada de token do TOTVS (400/401/403)."""


class TotvsUnavailableError(Exception):
    """TOTVS fora do ar/timeout/5xx — falha temporária, não deve ser
    tratada como credencial inválida."""

    def __init__(self, message: str, details: dict[str, object] | None = None) -> None:
        super().__init__(message)
        self.details = details


class TotvsProtocolError(Exception):
    """Resposta do TOTVS fora do formato esperado."""

    def __init__(self, message: str, details: dict[str, object] | None = None) -> None:
        super().__init__(message)
        self.details = details


@dataclass
class TotvsTokenResult:
    access_token: str


@dataclass
class TotvsVinculo:
    nome: str
    tipo: str
    email: str | None = None


class TotvsAuthClient(ABC):
    """Client dedicado às duas chamadas do TOTVS RM (token + consulta de vínculo)."""

    @abstractmethod
    def authenticate(self, usuario: str, senha: str) -> TotvsTokenResult: ...

    @abstractmethod
    def consultar_vinculo(self, usuario: str, access_token: str) -> list[TotvsVinculo]: ...


class LoginAttemptTracker(ABC):
    """Bloqueio temporário por tentativas falhas de login (estagiário)."""

    @abstractmethod
    def is_locked(self, key: str) -> bool: ...

    @abstractmethod
    def record_failure(self, key: str) -> None: ...

    @abstractmethod
    def record_success(self, key: str) -> None: ...
