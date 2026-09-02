"""Handler de erros central e estruturado.

Porta shared/http/error-handler.ts. Mapeia AppError para respostas com
`code` estável + `correlation_id` — mesmo formato de resposta do backend
Fastify, pra não quebrar contrato com os frontends. Erros inesperados são
logados por completo no servidor, mas retornam 500 genérico (nunca stack
trace ao cliente).
"""

from __future__ import annotations

import logging

from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse

from ..errors.app_error import AppError

logger = logging.getLogger("pep")


def register_error_handlers(app: FastAPI) -> None:
    @app.exception_handler(AppError)
    async def handle_app_error(request: Request, exc: AppError) -> JSONResponse:
        correlation_id = getattr(request.state, "correlation_id", None)
        logger.info("%s: %s (details=%s)", exc.code, exc.message, exc.details)
        return JSONResponse(
            status_code=exc.status_code,
            content={"code": exc.code, "message": exc.message, "correlation_id": correlation_id},
        )

    @app.exception_handler(Exception)
    async def handle_unexpected(request: Request, exc: Exception) -> JSONResponse:
        correlation_id = getattr(request.state, "correlation_id", None)
        logger.error("Unhandled error", exc_info=exc)
        return JSONResponse(
            status_code=500,
            content={
                "code": "internal_error",
                "message": "Ocorreu um erro interno. Tente novamente mais tarde.",
                "correlation_id": correlation_id,
            },
        )
