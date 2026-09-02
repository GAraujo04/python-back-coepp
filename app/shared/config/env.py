"""Validação centralizada de variáveis de ambiente (fail-fast no boot).

Porta shared/config/env.ts (Zod) para Pydantic Settings — mesma filosofia:
schema declarativo, validado uma vez no boot, nunca lido direto de
`os.environ` no resto do código. Segredos NUNCA hardcoded.
"""

from __future__ import annotations

import base64
from functools import lru_cache
from typing import Literal

from pydantic import Field, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Env(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    APP_ENV: Literal["development", "test", "staging", "production"] = "development"
    APP_PORT: int = 8000
    APP_HOST: str = "0.0.0.0"
    LOG_LEVEL: Literal["fatal", "error", "warn", "info", "debug", "trace"] = "info"

    # Connection string do SQL Server. Formato próprio do SQLAlchemy+pyodbc
    # (dialeto "mssql+pyodbc://..."), diferente do formato do Prisma
    # ("sqlserver://host:porta;database=x;...") — a mesma informação (host,
    # porta, banco, credencial), só a sintaxe da URL muda entre as duas
    # ferramentas.
    DATABASE_URL: str = Field(min_length=1)

    # Auth
    JWT_SECRET: str = Field(min_length=32)
    ACCESS_TOKEN_TTL_MINUTES: int = 15
    REFRESH_TOKEN_TTL_DAYS: int = 7

    # Criptografia de PII em repouso (AES-256-GCM). Chave de 32 bytes em base64.
    ENCRYPTION_KEY: str

    @field_validator("ENCRYPTION_KEY")
    @classmethod
    def _validate_encryption_key(cls, v: str) -> str:
        if len(base64.b64decode(v)) != 32:
            raise ValueError("ENCRYPTION_KEY deve ser 32 bytes em base64")
        return v

    # CORS — origem do frontend (pode ser mais de uma, separadas por vírgula)
    CORS_ORIGIN: str = "http://localhost:5173"

    # Autenticação do estagiário via TOTVS RM.
    # TOTVS_MOCK=True nunca pode rodar em produção — checado no boot (main.py).
    # Diferente do JS (onde Boolean("false") é `true`, uma armadilha real que
    # o env.ts original evita com strictBooleanEnv), o parser de bool do
    # Pydantic já trata "true"/"false" corretamente — mantemos Literal aqui
    # mesmo assim, só para deixar explícito que nenhum outro valor é aceito.
    TOTVS_MOCK: bool = False
    TOTVS_BASE_URL: str = "http://www.portal.fsa.br:8051"
    TOTVS_TIMEOUT_SECONDS: float = 10.0
    TOTVS_SENTENCA: str = "Retorna_Vinculo"
    TOTVS_COLIGADA: str = "1"
    TOTVS_SISTEMA: str = "S"
    TOTVS_PARAM_NOME: str = "USUARIO_S"
    TOTVS_PARAM_COM_ASPAS: bool = False
    TOTVS_TIPO_ALUNO: str = "A"


@lru_cache
def load_env() -> Env:
    """Carrega e valida o ambiente uma única vez por processo (equivalente
    ao cache em módulo do env.ts original)."""
    return Env()  # type: ignore[call-arg]  # campos obrigatórios vêm do .env/ambiente
