"""Sondas de saúde: liveness sempre 200 se o processo está de pé; readiness
checa dependências (DB). Usadas pelo reverse proxy/orquestrador.

Porta features/health/presentation/routes.ts — primeira slice migrada
(prova de conceito), a mais simples do projeto: sem domain/application,
só presentation, e só /ready toca no banco.
"""

from __future__ import annotations

import os

from fastapi import APIRouter
from fastapi.responses import JSONResponse
from sqlalchemy import text

from ....shared.db.session import get_session

router = APIRouter(tags=["health"])

APP_VERSION = os.environ.get("APP_VERSION", "dev")


@router.get("/health", summary="Liveness probe")
async def health() -> dict[str, str]:
    return {"status": "ok"}


@router.get("/ready", summary="Readiness probe (checa banco de dados)")
async def ready() -> JSONResponse:
    try:
        with get_session() as session:
            session.execute(text("SELECT 1"))
        return JSONResponse(status_code=200, content={"status": "ready"})
    except Exception:
        return JSONResponse(status_code=503, content={"status": "unavailable", "code": "db_unavailable"})


@router.get("/version", summary="Build version")
async def version() -> dict[str, str]:
    return {"version": APP_VERSION}
