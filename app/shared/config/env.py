"""Validação centralizada de variáveis de ambiente (fail-fast no boot).

Porta shared/config/env.ts (Zod) para Pydantic Settings — mesma filosofia:
schema declarativo, validado uma vez no boot, nunca lido direto de
`os.environ` no resto do código. Segredos NUNCA hardcoded.
"""

from __future__ import annotations

import base64
import json
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

    # Id da chave ativa, gravado dentro de cada payload cifrado (ver
    # shared/crypto/field_encryption.py). Só mude ao rotacionar — e, ao
    # mudar, a chave anterior tem que ir para ENCRYPTION_KEYS_RETIRED, ou
    # tudo que já está no banco fica ilegível.
    ENCRYPTION_KEY_ID: int = 1

    # Chaves aposentadas, só para DECIFRAR dado ainda não reescrito.
    # JSON {"<id>": "<chave em base64>"}. Vazio quando não há rotação em
    # andamento, que é o estado normal.
    ENCRYPTION_KEYS_RETIRED: str = ""

    @field_validator("ENCRYPTION_KEY")
    @classmethod
    def _validate_encryption_key(cls, v: str) -> str:
        if len(base64.b64decode(v)) != 32:
            raise ValueError("ENCRYPTION_KEY deve ser 32 bytes em base64")
        return v

    @field_validator("ENCRYPTION_KEYS_RETIRED")
    @classmethod
    def _validate_retired_keys(cls, v: str) -> str:
        """Falha no boot, não na primeira leitura de dado antigo. Uma chave
        aposentada malformada só se manifestaria ao tentar decifrar a linha
        que precisa dela — possivelmente semanas depois da rotação."""
        if not v.strip():
            return v
        for raw_id, raw_key in json.loads(v).items():
            int(raw_id)
            if len(base64.b64decode(raw_key)) != 32:
                raise ValueError(f"ENCRYPTION_KEYS_RETIRED[{raw_id}] deve ser 32 bytes em base64")
        return v

    # CORS — origem do frontend (pode ser mais de uma, separadas por vírgula)
    CORS_ORIGIN: str = "http://localhost:5173"

    # Rate limit por IP (ver shared/http/rate_limit.py). Os defaults são os
    # mesmos números do @fastify/rate-limit do backend original: 100/min no
    # geral e 10/15min nas rotas de login. RATE_LIMIT_ENABLED=False existe
    # para os testes, que disparam muitas requisições no mesmo "IP" do
    # TestClient — nunca desligue em produção.
    RATE_LIMIT_ENABLED: bool = True
    RATE_LIMIT_MAX: int = 100
    RATE_LIMIT_WINDOW_SECONDS: int = 60
    RATE_LIMIT_AUTH_MAX: int = 10
    RATE_LIMIT_AUTH_WINDOW_SECONDS: int = 900
    RATE_LIMIT_REGISTER_MAX: int = 5
    RATE_LIMIT_REGISTER_WINDOW_SECONDS: int = 3600
    # Só ligue quando houver um reverse proxy à frente que SOBRESCREVA o
    # X-Forwarded-For. Sem proxy, o header é escrito pelo cliente e o
    # limite passa a ser burlável trocando-o a cada requisição.
    RATE_LIMIT_TRUST_FORWARDED_FOR: bool = False

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
