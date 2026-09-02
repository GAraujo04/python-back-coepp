"""Porta da trilha de auditoria (append-only).

Porta shared/audit/audit-recorder.ts.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass
from typing import Any, Literal

AuditAction = Literal[
    "LOGIN", "LOGIN_FAILED", "REFRESH", "LOGOUT", "READ", "CREATE", "UPDATE", "DELETE", "EXPORT", "TRANSITION"
]


@dataclass
class AuditEvent:
    action: AuditAction
    resource_type: str
    actor_id: str | None = None
    resource_id: str | None = None
    correlation_id: str | None = None
    ip: str | None = None
    user_agent: str | None = None
    diff: dict[str, Any] | None = None


class AuditRecorder(ABC):
    @abstractmethod
    def record(self, event: AuditEvent) -> None: ...
