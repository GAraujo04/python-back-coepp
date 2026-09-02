# python-back-coepp

Backend do PEP (Prontuário Eletrônico do Paciente — Clínica-Escola de
Psicologia, Fundação Santo André), migrado de Fastify/TypeScript
(`pep/apps/api`) para **Python + FastAPI**.

## Por quê

Decisão de time, não técnica: quem mantém o backend no dia a dia conhece
Python de verdade, não Fastify/Node. Ver:

- ADR: [`../pep/docs/adr/0005-backend-python-fastapi-repo-proprio.md`](../pep/docs/adr/0005-backend-python-fastapi-repo-proprio.md)
- Spec: [`../pep/docs/specs/migracao-backend-python.md`](../pep/docs/specs/migracao-backend-python.md)

**Não define nada sozinho** — o contrato HTTP é o de
`pep/docs/api/openapi.yaml`, reproduzido aqui, não redesenhado. O banco
(SQL Server) é o mesmo, com o mesmo schema/RLS/triggers do
`pep/apps/api/prisma` — esta migração troca só a linguagem/framework da
camada de aplicação.

## Stack

- **FastAPI** (async, gera OpenAPI nativo a partir de Pydantic)
- **SQLAlchemy 2.0** + **Alembic** (ORM/migrations — banco continua SQL Server)
- **pyodbc** (driver, via ODBC Driver 18 da Microsoft)
- **PyJWT**, **argon2-cffi** (mesmos algoritmos do backend original: HS256, Argon2id)
- **pytest** + **ruff** + **mypy**

## Rodando local

Pré-requisitos: Python 3.13+, SQL Server local rodando (`docker compose up mssql` no repo `pep`), driver ODBC 18 instalado (`brew install msodbcsql18` via o tap `microsoft/mssql-release`).

```bash
python3.13 -m venv .venv
.venv/bin/pip install -e ".[dev]"
cp .env.example .env  # ajuste DATABASE_URL/segredos
.venv/bin/uvicorn app.main:app --reload --port 8001
```

Roda na porta **8001** por padrão (o Fastify original continua na 8000) —
de propósito, pra permitir rodar os dois lado a lado durante a migração e
comparar respostas diretamente.

```bash
.venv/bin/pytest          # testes
.venv/bin/ruff check app/ # lint
.venv/bin/mypy app/       # typecheck
```

## Status (2026-09-02)

Migração incremental, uma slice por vez (ver spec, seção 6 e 10). Slices
migradas até aqui:

- [x] `health` (`/health`, `/ready`, `/version`) — prova de conceito,
      testada ao vivo contra o SQL Server local e comparada byte a byte
      com a resposta do Fastify original.

O Fastify (`pep/apps/api`) continua sendo o backend real em produção — este
repo não substitui nada até todas as 11 slices estarem migradas e validadas.
