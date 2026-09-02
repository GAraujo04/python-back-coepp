"""Atribui um correlation_id a cada requisição (observabilidade).

Porta shared/http/correlation.ts. Reusa o header X-Correlation-Id se o
cliente/gateway já enviou; senão gera. Fastify tinha isso como plugin
decorando `request`; no FastAPI usamos middleware ASGI + `request.state`
(o jeito idiomático de anexar dado por request sem um decorator próprio).
"""

from __future__ import annotations

from uuid import uuid4

from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import Response


class CorrelationIdMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next):  # type: ignore[no-untyped-def]
        incoming = request.headers.get("x-correlation-id")
        correlation_id = incoming if incoming else str(uuid4())
        request.state.correlation_id = correlation_id
        response: Response = await call_next(request)
        response.headers["x-correlation-id"] = correlation_id
        return response
