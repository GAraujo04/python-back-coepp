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

- [x] `enrollment` (`POST /register/patient`, `POST /register/student`,
      `GET /register/options`, `GET /register/responsibility-term`,
      `PATCH /enrollment/complete-profile`,
      `GET/PUT /enrollment/availability-windows`) — autocadastro público de
      paciente/estagiário e edição da disponibilidade recorrente do
      estagiário. Sem `domain/` no original, mantido fiel. Termo de
      responsabilidade (Docs-as-Code) copiado verbatim pra
      `docs/legal/` deste repo (confirmado idêntico via diff), já que
      este é um repositório PRÓPRIO sem o monorepo `pep` como ancestral.
      **Bug de path/regex encontrado e corrigido antes do primeiro teste
      pegar** (nunca chegou a afetar o Fastify, só o meu próprio port): o
      parser do front-matter usava `re.match` com `^` — falha porque o
      arquivo real começa com um comentário HTML de aviso ANTES do bloco
      `---`, não com `---` na primeira linha; o regex original em JS não
      tem essa âncora. Corrigido pra `re.search` sem `^`, replicando o
      comportamento exato do original. `ageInYears`/`EMAIL_RE` duplicados
      deliberadamente aqui (não importados de `patients/`) — mesma decisão
      de fronteira de slice do TS original. Verificado: ruff, mypy, 26
      testes pytest (nenhum novo — cobertura desta slice foi só via teste
      ao vivo). Servidor uvicorn real comparado byte a byte com o Fastify:
      cadastro de paciente com disponibilidade (código sequencial
      intercalado corretamente entre os dois backends, mesma sequência
      `patient_counters`); rejeição de menor sem responsável e de janelas
      sobrepostas (mesma mensagem); cadastro de estagiário com
      `pendingSupervisorName`; conflito de versão do termo (`409`);
      exigência de exatamente um supervisor (`400`); confirmado que um
      estagiário AUTOCADASTRADO nunca consegue logar por e-mail/senha em
      NENHUM dos dois backends — característica pré-existente do sistema
      original (`LoginUser` rejeita `role === 'INTERN'` incondicionalmente,
      TOTVS é o único caminho), não uma regressão da migração;
      `GET/PUT /enrollment/availability-windows` e
      `PATCH /enrollment/complete-profile` testados com um JWT assinado
      localmente (mesmo `JWT_SECRET`) pra um INTERN real, com efeito
      idêntico nos dois backends (mesma linha final no banco); RBAC
      (`403` pra ADMIN) e conflito de e-mail (`409`) também batendo.

- [x] `matching` (`POST /matching/run`, `GET /matching/matches`,
      `GET /matching/suggestions`, `GET /matching/pending-requests`,
      `PATCH /matching/pending-requests/{id}/resolve`, `POST /matching/manual`)
      — motor de pareamento automático (item 2/6) + fallback por
      aproximação (item 5) + match manual (item 7). Com `domain/` no
      original (única das últimas 4 slices que tem).
      **Achado importante de fuso horário, corrigido**: `next-occurrence.ts`
      calcula "próxima ocorrência" usando os getters/setters LOCAIS de
      `Date` — internamente um instante UTC, então o resultado "parece"
      hora local mas o Node grava UTC de verdade no banco. Confirmado
      empiricamente ANTES de portar (script isolado): um `Date` com
      `setHours(14,30)` às 12h em São Paulo (UTC-3) foi lido de volta do
      banco, via `SELECT CONVERT` cru, como `17:30:00`. Python não tem
      essa conversão automática — `next_occurrence`/`time_of_day` fazem a
      conversão local→UTC (e UTC→local, no sentido inverso) explicitamente
      (`astimezone()`), verificado batendo com o valor gravado pelo
      Fastify pro mesmo horário de janela de disponibilidade.
      **Bug de sessão SQLAlchemy encontrado e corrigido (afeta código
      compartilhado, não só matching)**: `with_rls_context` chamava
      `session.begin()` incondicionalmente, presumindo ser sempre a
      PRIMEIRA operação da Session — verdade em todas as slices
      anteriores, mas não em `RunMatching`, que lê `patients`/`users`/
      `rooms` (sem RLS) ANTES de escrever em `appointments` (com RLS na
      mesma Session por-request). A leitura anterior já tinha
      "autobegin"ado uma transação implícita (padrão do SQLAlchemy 2.0),
      e o `session.begin()` aninhado lançava
      `InvalidRequestError: A transaction is already begun`. Corrigido
      para só chamar `session.begin()` se `not session.in_transaction()`.
      **Achado retroativo, corrigido para TODAS as 9 slices já migradas**:
      erro de validação de corpo de requisição (campo obrigatório
      ausente, tipo errado etc.) não tinha handler dedicado — o FastAPI
      caía no seu 422 padrão (`{"detail": [...]}`), divergindo do 400
      `{"code": "validation_failed", "message": ..., "correlation_id": ...}`
      que o ajv do Fastify sempre produz. Adicionado um
      `RequestValidationError` handler em `shared/http/error_handler.py`
      (infra compartilhada — vale pra toda slice já migrada e as
      futuras) que normaliza pro mesmo formato; o caso mais comum (campo
      obrigatório ausente) usa a MESMA frase do ajv
      (`"body must have required property 'x'"`, confirmado idêntico
      byte a byte); os demais tipos de erro usam uma mensagem legível
      derivada do Pydantic (não é uma réplica byte a byte de todo
      dialeto do ajv, mas o código/status/formato do contrato batem
      sempre). Verificado: ruff, mypy, 26 testes pytest. Servidor
      uvicorn real comparado byte a byte com o Fastify (mesma base,
      pacientes/estagiário/sala de teste criados direto no banco):
      pareamento automático com sucesso (Assignment + Appointment
      criados, horário local→UTC batendo); o mesmo cenário de "sala
      escolhida pelo algoritmo colide com uma appointment já persistida
      de uma rodada anterior" reproduz o MESMO `409 conflict` nos dois
      backends (não é bug — é uma característica do algoritmo puro, que
      não conhece o estado do banco até a escrita real); `GET
      /matching/matches`, `/suggestions` e `/pending-requests` idênticos
      byte a byte; `PATCH .../resolve` idempotente; `POST
      /matching/manual` com avisos bloqueando sem `acknowledgeWarnings`,
      confirmando com `acknowledgeWarnings=true`, `404` para
      paciente/estagiário inexistente (mesma mensagem nos dois).

- [x] `documents` (`POST /documents/{id}/transitions`, `GET /documents/review-queue`,
      `GET /documents/{id}/review`) — máquina de estados dos documentos
      clínicos (RASCUNHO → ENVIADO_PARA_SUPERVISAO → EM_REVISAO →
      APROVADO_LOCKED/REJEITADO/REVISAO_SOLICITADA), assinatura interna
      (HMAC-SHA256) e trava WORM na aprovação. Com `domain/` no original.
      `resolve_transition` porta a tabela de transições 1:1 (dict de
      dict, mesma forma que o `Record` do TS). Novos modelos:
      `DocumentApproval`, `ReviewComment`; `ClinicalDocument` ganhou
      `author`/`patient`/`comments` (relationships eager). Hash do
      conteúdo (`sha256` sobre o JSON) usa `separators=(",", ":")` +
      `ensure_ascii=False` pra bater byte a byte com o
      `JSON.stringify()` do Node (mesma convenção de key-order já
      preservada desde a slice screening). Verificado: ruff, mypy, 26
      testes pytest. Servidor uvicorn real, ciclo de vida completo
      testado ao vivo contra o Fastify:
      SUBMIT → TAKE → REQUEST_CHANGES (com comentário) → SUBMIT de novo →
      APPROVE, criando um documento inteiramente pelo Fastify e lendo o
      resultado final pelo Python — **idêntico byte a byte**, incluindo
      as 3 assinaturas (2 do estagiário, 1 do supervisor com CRP),
      1 comentário e o nome do paciente decifrado. Também testado:
      transição inválida a partir de `APROVADO_LOCKED` (`409
      invalid_transition`, mesma mensagem); papel sem permissão pra
      ação (`PATIENT` tentando `SUBMIT`, mesma mensagem "Papel
      não permitido"); RBAC do `review-queue` (`403` pra `INTERN`);
      estagiário sem autoria/coautoria tentando `SUBMIT` (`403
      forbidden`, "Apenas o autor ou coautor...") — todos idênticos nos
      dois backends.

O Fastify (`pep/apps/api`) continua sendo o backend real em produção — este
repo não substitui nada até todas as 11 slices estarem migradas e validadas.
