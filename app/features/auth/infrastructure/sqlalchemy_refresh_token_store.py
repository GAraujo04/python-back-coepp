"""Adapter SQLAlchemy do RefreshTokenStore. Persiste apenas o HASH do
token. Rotação: cada refresh revoga a sessão antiga e cria uma nova
(mitiga reuso/replay).

Porta features/auth/infrastructure/prisma-refresh-token-store.ts.
"""

from __future__ import annotations

import hashlib
import secrets
from datetime import UTC, datetime, timedelta

from sqlalchemy import select
from sqlalchemy.orm import Session

from ....shared.db.models import RefreshSession
from ....shared.errors.app_error import UnauthorizedError
from ..application.ports import IssuedRefreshToken, RefreshSessionMeta, RefreshTokenStore


def _hash_token(token: str) -> str:
    return hashlib.sha256(token.encode("utf-8")).hexdigest()


def _utc_now() -> datetime:
    """UTC naive — SQL Server DATETIME2 (e o driver pyodbc) não carregam
    tzinfo; mantemos os datetimes naive em todo o projeto (aqui e no JWT)
    pra nunca comparar naive com aware, que levanta TypeError em Python."""
    return datetime.now(UTC).replace(tzinfo=None)


class SqlAlchemyRefreshTokenStore(RefreshTokenStore):
    def __init__(self, session: Session, ttl_days: int) -> None:
        self._session = session
        self._ttl_days = ttl_days

    def _expiry(self) -> datetime:
        return _utc_now() + timedelta(days=self._ttl_days)

    def issue(self, user_id: str, meta: RefreshSessionMeta) -> IssuedRefreshToken:
        token = secrets.token_urlsafe(32)
        expires_at = self._expiry()
        row = RefreshSession(
            user_id=user_id,
            token_hash=_hash_token(token),
            user_agent=meta.user_agent,
            ip=meta.ip,
            expires_at=expires_at,
        )
        self._session.add(row)
        self._session.flush()
        return IssuedRefreshToken(token=token, expires_at=expires_at)

    def rotate(self, old_token: str, meta: RefreshSessionMeta) -> tuple[str, IssuedRefreshToken]:
        session_row = self._session.scalar(
            select(RefreshSession).where(RefreshSession.token_hash == _hash_token(old_token))
        )
        now = _utc_now()
        expired = session_row is not None and session_row.expires_at < now
        if not session_row or session_row.revoked_at or expired:
            raise UnauthorizedError("Sessão inválida ou expirada.")

        session_row.revoked_at = now
        self._session.flush()
        issued = self.issue(session_row.user_id, meta)
        return session_row.user_id, issued

    def revoke(self, token: str) -> None:
        row = self._session.scalar(
            select(RefreshSession).where(
                RefreshSession.token_hash == _hash_token(token), RefreshSession.revoked_at.is_(None)
            )
        )
        if row:
            row.revoked_at = _utc_now()
            self._session.flush()
