"""Bloqueio temporário em memória (por processo) por tentativas falhas de
login (estagiário).

Porta features/auth/infrastructure/in-memory-login-attempt-tracker.ts.
Suficiente para o único processo da aplicação hoje — não é distribuído nem
sobrevive a um restart. Mesma limitação documentada no original (viraria
Redis se a aplicação passasse a rodar em mais de uma instância).
"""

from __future__ import annotations

import time
from dataclasses import dataclass

from ..application.ports import LoginAttemptTracker

_DEFAULT_MAX_ATTEMPTS = 5
_DEFAULT_WINDOW_SECONDS = 15 * 60
_DEFAULT_LOCK_SECONDS = 15 * 60


@dataclass
class _AttemptState:
    count: int
    window_started_at: float
    locked_until: float | None


class InMemoryLoginAttemptTracker(LoginAttemptTracker):
    def __init__(
        self,
        max_attempts: int = _DEFAULT_MAX_ATTEMPTS,
        window_seconds: float = _DEFAULT_WINDOW_SECONDS,
        lock_seconds: float = _DEFAULT_LOCK_SECONDS,
    ) -> None:
        self._max_attempts = max_attempts
        self._window_seconds = window_seconds
        self._lock_seconds = lock_seconds
        self._state: dict[str, _AttemptState] = {}

    def is_locked(self, key: str) -> bool:
        entry = self._state.get(key)
        if not entry:
            return False
        now = time.time()
        if entry.locked_until and entry.locked_until > now:
            return True
        if entry.locked_until and entry.locked_until <= now:
            del self._state[key]  # trava expirou — limpa pra não vazar memória indefinidamente
            return False
        return False

    def record_failure(self, key: str) -> None:
        now = time.time()
        existing = self._state.get(key)
        if not existing or now - existing.window_started_at > self._window_seconds:
            entry = _AttemptState(count=1, window_started_at=now, locked_until=None)
        else:
            entry = _AttemptState(
                count=existing.count + 1, window_started_at=existing.window_started_at, locked_until=None
            )
        if entry.count >= self._max_attempts:
            entry.locked_until = now + self._lock_seconds
        self._state[key] = entry

    def record_success(self, key: str) -> None:
        self._state.pop(key, None)
