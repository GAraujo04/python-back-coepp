"""Composition root do backend. Monta a instância FastAPI com os plugins
transversais (CORS, correlação, handler de erro) e registra as rotas de
cada slice.

Porta app.ts. Diferença de modelo mental: no Fastify, `buildApp()` retorna
a instância e `server.ts` chama `.listen()` nela — dois passos separados
pra permitir testar com `app.inject()` sem abrir porta. No FastAPI/ASGI o
próprio objeto `app` já é o que o servidor (uvicorn) importa e serve; o
equivalente a "testar sem abrir porta" é `TestClient(app)` (usa o mesmo
objeto ASGI, sem rede de verdade) — não precisamos de um `server.py`
separado só pra isso.
"""

from __future__ import annotations

from fastapi import FastAPI
from starlette.middleware.cors import CORSMiddleware

from .features.health.presentation.routes import router as health_router
from .shared.config.env import load_env
from .shared.http.correlation import CorrelationIdMiddleware
from .shared.http.error_handler import register_error_handlers


def create_app() -> FastAPI:
    env = load_env()

    # TOTVS_MOCK bypassa a autenticação real do estagiário (respostas
    # fixas) — aceitável em dev/homologação, jamais em produção. Aborta o
    # boot em vez de só logar um aviso: um bypass de auth ligado por engano
    # é grave demais pra depender de alguém notar um log.
    if env.TOTVS_MOCK and env.APP_ENV == "production":
        raise RuntimeError(
            "TOTVS_MOCK=True em produção é um bypass de autenticação do estagiário. "
            "Boot abortado — corrija a variável de ambiente."
        )

    app = FastAPI(
        title="PEP API — Clínica-Escola de Psicologia",
        description="Prontuário Eletrônico do Paciente. Contrato gerado a partir das rotas (schema-first).",
        version="0.1.0",
        # Swagger-UI nativo do FastAPI só fora de produção — mesma cautela
        # do @fastify/swagger-ui original (que tinha uma falha conhecida de
        # path traversal sem correção disponível). Em produção o contrato é
        # obtido via export estático, sem expor a UI interativa.
        docs_url="/docs" if env.APP_ENV != "production" else None,
        redoc_url=None,
    )

    app.add_middleware(
        CORSMiddleware,
        allow_origins=[o.strip() for o in env.CORS_ORIGIN.split(",")],
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )
    app.add_middleware(CorrelationIdMiddleware)

    register_error_handlers(app)

    # --- Rotas por slice ---
    # health não leva prefixo /api (mesma exceção do app.ts original —
    # sondas de liveness/readiness costumam ficar na raiz por convenção de
    # orquestrador/reverse proxy).
    app.include_router(health_router)
    # auth, users, appointments, screening, patients, enrollment, matching,
    # documents, assignments, disciplinas, rooms — entram aqui conforme
    # cada slice for migrada (ver spec: docs/specs/migracao-backend-python.md).

    return app


app = create_app()
