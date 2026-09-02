"""Handler de erros central e estruturado.

Porta shared/http/error-handler.ts. Mapeia AppError para respostas com
`code` estável + `correlation_id` — mesmo formato de resposta do backend
Fastify, pra não quebrar contrato com os frontends. Erros inesperados são
logados por completo no servidor, mas retornam 500 genérico (nunca stack
trace ao cliente).

Também normaliza `RequestValidationError` (falha de validação do Pydantic
no boundary — corpo/query/path mal formados) pro MESMO formato. Sem isso,
o FastAPI usaria seu handler padrão, que devolve `422` com corpo
`{"detail": [...]}` — divergindo do `400`/`{code, message, correlation_id}`
que o `@fastify/schema`/ajv do backend original sempre produz. Achado
DEPOIS de já ter migrado 8 slices (afeta TODAS elas igualmente, não é
específico de nenhuma) — comparando `POST /screenings` sem `patientId`
nos dois backends: Fastify devolvia `400 {"code":"validation_failed",
"message":"body must have required property 'patientId'", ...}`,
Python devolvia `422 {"detail": [...]}`. Corrigido aqui, uma vez, pra
todas as slices já migradas e as futuras — não precisa refazer nada nos
schemas de cada slice individualmente.

O texto da mensagem não replica byte a byte todas as variações de
mensagem do ajv (cada validador de schema tem seu próprio dialeto) — o
caso mais comum e mais previsível (campo obrigatório ausente) usa a
MESMA frase do ajv (`body must have required property 'x'`); os demais
casos usam uma mensagem legível derivada do erro do Pydantic. O que
importa pro contrato (código HTTP 400, `code: "validation_failed"`,
presença de `correlation_id`) é sempre idêntico.
"""

from __future__ import annotations

import logging

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse

from ..errors.app_error import AppError

logger = logging.getLogger("pep")


def _format_validation_message(exc: RequestValidationError) -> str:
    errors = exc.errors()
    if not errors:
        return "Corpo da requisição inválido."
    err = errors[0]
    loc = [str(p) for p in err["loc"] if p not in ("body", "query", "path")]
    field = ".".join(loc) if loc else None
    scope = err["loc"][0] if err["loc"] else "body"

    if err["type"] == "missing" and field:
        # Mesma frase do ajv pro caso mais comum — campo obrigatório ausente.
        return f"{scope} must have required property '{field}'"
    if field:
        return f"{scope}/{field} {err['msg']}"
    return f"{scope}: {err['msg']}"


def register_error_handlers(app: FastAPI) -> None:
    @app.exception_handler(AppError)
    async def handle_app_error(request: Request, exc: AppError) -> JSONResponse:
        correlation_id = getattr(request.state, "correlation_id", None)
        logger.info("%s: %s (details=%s)", exc.code, exc.message, exc.details)
        return JSONResponse(
            status_code=exc.status_code,
            content={"code": exc.code, "message": exc.message, "correlation_id": correlation_id},
        )

    @app.exception_handler(RequestValidationError)
    async def handle_validation_error(request: Request, exc: RequestValidationError) -> JSONResponse:
        correlation_id = getattr(request.state, "correlation_id", None)
        message = _format_validation_message(exc)
        logger.info("validation_failed: %s (errors=%s)", message, exc.errors())
        return JSONResponse(
            status_code=400,
            content={"code": "validation_failed", "message": message, "correlation_id": correlation_id},
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
