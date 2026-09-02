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
- [x] `auth` + `users` (`/auth/login`, `/auth/intern-login`, `/auth/patient-login`,
      `/auth/refresh`, `/auth/logout`, `/auth/me`, `/users`, `/users/pending-supervisors`,
      `/users/{id}/link-supervisor`) — a slice mais crítica do projeto
      (TOTVS RM, JWT, refresh token rotativo, RBAC). Testada ao vivo contra
      o SQL Server local para os 3 mecanismos de login (e-mail/senha,
      CPF+nascimento, TOTVS mock), com tokens emitidos pelo Python
      validados com sucesso pelo Fastify (mesmo `JWT_SECRET`/algoritmo) e
      vice-versa. 26 testes automatizados (pytest) portando os cenários
      dos arquivos vitest originais de `login-user`/`intern-login`.
- [x] `appointments` (`POST/GET /appointments`, `PATCH /appointments/{id}/attendance`)
      — primeira slice a exercitar RLS de verdade
      (`SECURITY POLICY`/`SESSION_CONTEXT` do SQL Server). Testada ao vivo:
      estagiário dono vê o próprio agendamento, supervisor com vínculo
      ativo na paciente também vê (mesmo sem ser o estagiário dela),
      paciente não vê nada (sem cláusula PATIENT na policy — fail-closed) —
      os 3 resultados batem exatamente com a função SQL lida na migration.
      Conflito de sala (409), transição de status inválida (409) e RBAC
      (403) também testados contra o banco real.
- [x] `disciplinas` + `rooms` (`GET/POST /disciplinas`, `GET /rooms`,
      `PATCH /rooms/reassign`) — duas slices pequenas, sem `domain/`/`application`
      no original (CRUD direto na rota), mantidas fiéis. Primeira vez que
      `decrypt_field` roda numa consulta de listagem (nome do paciente na
      sala ocupada). **Bug pré-existente encontrado e reproduzido
      fielmente (não corrigido — spec pede reproduzir, não redesenhar):**
      `listWithStatus()`/`list_with_status()` consulta `appointments`
      direto, sem `withRlsContext`/`with_rls_context` — como a RLS de
      `appointments` é fail-closed, a ocupação de sala mostrada nunca é
      real, em nenhum dos dois backends (confirmado isolando a causa).
      Registrado para decisão separada do usuário.
- [x] `patients` (cadastro, listagem por vínculo, `GET /portal/me`) — primeira
      vez que `encrypt_field`/`decrypt_field` (AES-256-GCM) são exercitados
      de ponta a ponta contra dado real gravado pelo Node: nomes já
      cadastrados pelo Fastify decifrados corretamente pelo Python, e um
      paciente novo cadastrado pelo Python lido de volta certo pelo
      Fastify. Escopo por vínculo (não é RLS de banco — `patients` não tem
      `SECURITY POLICY` — é `WHERE` explícito via join em `assignments`,
      igual ao TS) testado nos 2 papéis. `portal_data()` preserva a
      decisão original de usar `with_rls_context(..., role="ADMIN")` fixo
      (bypass deliberado, seguro porque a query já é escopada por
      `patient.user_id`).
- [x] `screening` (`POST/GET /screenings`, `GET/PATCH/DELETE /screenings/{id}`)
      — triagens (`clinical_documents` do tipo `SCREENING_*`). Content
      validado por Pydantic `.strict()` (schema fechado
      adulto/criança, replica os Zod originais); concorrência otimista
      por `version` testada ao vivo (`PATCH` com `expectedVersion` correto
      funciona, com versão obsoleta retorna `409`). Confirmado por leitura
      de uma segunda migration (`allow_author_delete_draft_document`) que
      o `BLOCK PREDICATE` de `DELETE` foi relaxado depois da primeira —
      autor/coautor pode apagar o próprio `RASCUNHO`, não só ADMIN — e
      testado ao vivo (`204` pro autor, `404` por RLS pra estagiário sem
      vínculo). **Bug de arredondamento encontrado e corrigido**: o
      `UtcDatetime` compartilhado arredondava microssegundos pro
      milissegundo mais próximo; o driver do Node trunca — corrigido para
      truncar também (achado comparando `updatedAt` do mesmo registro
      lido pelos dois backends, `.138Z` vs `.137Z`). Testado ao vivo:
      criação com `numero` sequencial (`AAAA-NNNN`), rejeição de campo de
      content desconhecido (`400`), leitura por supervisora com vínculo
      via assignment, e os 3 casos de escopo negativo (`GET`/`LIST`/`DELETE`
      por estagiário sem vínculo → `404`/lista vazia) comparados byte a
      byte com o Fastify usando o mesmo token nos dois backends.

O Fastify (`pep/apps/api`) continua sendo o backend real em produção — este
repo não substitui nada até todas as 11 slices estarem migradas e validadas.
