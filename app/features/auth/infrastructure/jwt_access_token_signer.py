"""Assinador de access token JWT.

Porta features/auth/infrastructure/fastify-access-token-signer.ts. O
Fastify delegava a assinatura ao plugin @fastify/jwt (`app.jwt.sign`); aqui
usamos PyJWT diretamente — mesmo algoritmo (HS256, o default de ambas as
libs) e mesmo JWT_SECRET, então tokens têm o mesmo formato.
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

import jwt

from ..application.ports import AccessTokenPayload, AccessTokenSigner


class JwtAccessTokenSigner(AccessTokenSigner):
    def __init__(self, secret: str, ttl_minutes: int) -> None:
        self._secret = secret
        self._ttl_minutes = ttl_minutes

    def sign(self, payload: AccessTokenPayload) -> str:
        now = datetime.now(UTC)
        exp = now + timedelta(minutes=self._ttl_minutes)
        return jwt.encode(
            {"sub": payload.sub, "role": payload.role, "email": payload.email, "iat": now, "exp": exp},
            self._secret,
            algorithm="HS256",
        )
