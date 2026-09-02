"""Erros tipados do domínio/aplicação. Nunca vazam stack trace nem
identificadores internos ao cliente (regra de segurança). Cada erro carrega
um `code` estável (machine-readable) e um `status_code` HTTP.

Porta shared/errors/app-error.ts — mesma hierarquia, classes em vez de
subclasses TS, `code`/`status_code` como propriedades abstratas via ABC.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Any


class AppError(ABC, Exception):
    def __init__(self, message: str, details: dict[str, Any] | None = None) -> None:
        super().__init__(message)
        self.message = message
        self.details = details

    @property
    @abstractmethod
    def code(self) -> str: ...

    @property
    @abstractmethod
    def status_code(self) -> int: ...


class ValidationError(AppError):
    code = "validation_failed"
    status_code = 400


class UnauthorizedError(AppError):
    code = "unauthorized"
    status_code = 401


class ForbiddenError(AppError):
    code = "forbidden"
    status_code = 403


class NotFoundError(AppError):
    code = "not_found"
    status_code = 404


class ConflictError(AppError):
    code = "conflict"
    status_code = 409


class ServiceUnavailableError(AppError):
    """Dependência externa indisponível (ex.: TOTVS RM fora do ar/timeout) —
    erro temporário, distinto de credencial inválida (não confundir com 401)."""

    code = "service_unavailable"
    status_code = 503


class InvalidTransitionError(AppError):
    """Transição inválida na máquina de estados de documentos clínicos."""

    code = "invalid_transition"
    status_code = 409
