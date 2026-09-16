"""Rate limit por IP no boundary HTTP.

O backend Fastify original protegia a API com `@fastify/rate-limit` (teto
global de 100 req/min por IP, mais 10 tentativas/15 min nas rotas de
login). Essa proteção não veio junto na migração das slices para o Python
— o comentário "Rate limit global se aplica às públicas" em
`enrollment/presentation/routes.py` ficou órfão, descrevendo algo que não
existia mais. Este módulo a reintroduz como middleware ASGI, sem
dependência nova (o projeto já mantém contadores em memória à mão em
`InMemoryLoginAttemptTracker`, mesma filosofia).

Três baldes, todos por IP e configuráveis por ambiente:

- GLOBAL   — todas as requisições. Teto de abuso genérico.
- AUTH     — rotas de login. Conta apenas as tentativas que FALHAM
             (400/401/403). A distinção importa: uma clínica inteira atrás
             de um único IP (NAT) faz dezenas de logins legítimos por hora
             sem gastar orçamento nenhum, enquanto uma força bruta esgota
             o balde em 10 tentativas. Um limite estreito por IP só é
             viável assim; contando tráfego, ele derrubaria a recepção
             junto com o atacante.
- REGISTER — autocadastro público. Conta todas as requisições (não há
             "falha" a distinguir aqui — o abuso é o próprio volume).

Um login bem-sucedido zera o balde AUTH daquele IP: quem prova conhecer
uma credencial não é quem estamos tentando conter, e sem isso o usuário
que erra a senha 3x e acerta na 4ª continuaria carregando o débito.

Limitações conhecidas, idênticas às já documentadas no
`InMemoryLoginAttemptTracker`: o estado é do PROCESSO — não é distribuído
e não sobrevive a restart. Com mais de uma instância, cada uma passa a ter
seu próprio orçamento (o limite efetivo vira N × o configurado) e a troca
natural é mover os contadores para Redis. Enquanto a aplicação roda em um
processo só, isto basta e não adiciona infraestrutura.
"""

from __future__ import annotations

import math
import time
from dataclasses import dataclass
from threading import Lock

from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import JSONResponse, Response

from ..config.env import Env, load_env

# Sondas de orquestrador (liveness/readiness) batem em intervalo fixo e
# curto por natureza — limitá-las só produziria falso alarme de saúde.
EXEMPT_PATHS = frozenset({"/health", "/ready", "/version"})

AUTH_PATHS = frozenset(
    {
        "/api/auth/login",
        "/api/auth/intern-login",
        "/api/auth/patient-login",
    }
)

REGISTER_PATHS = frozenset(
    {
        "/api/register/patient",
        "/api/register/student",
    }
)

# 403 entra junto com 401/400 porque uma credencial válida sem vínculo
# ativo (estagiário não habilitado) é indistinguível, do lado de fora, de
# uma sondagem — e é justamente o que um atacante usaria pra enumerar.
FAILED_AUTH_STATUSES = frozenset({400, 401, 403})


@dataclass(frozen=True)
class RateLimitRule:
    name: str
    max_requests: int
    window_seconds: int
    count_only_failures: bool = False


@dataclass
class _Window:
    count: int
    started_at: float
    window_seconds: int


class FixedWindowCounters:
    """Contadores de janela fixa em memória.

    Janela fixa (e não deslizante) é a mesma estratégia do
    `@fastify/rate-limit` que este middleware substitui: aceita uma rajada
    na virada de janela em troca de custo O(1) por requisição e de um
    estado que cabe num dict. Para conter força bruta e abuso de
    autocadastro — que se medem em minutos, não em milissegundos — a
    imprecisão da virada é irrelevante.
    """

    _SWEEP_INTERVAL_SECONDS = 60.0

    def __init__(self) -> None:
        self._state: dict[str, _Window] = {}
        # O dispatch do middleware roda no event loop (uma thread só), mas
        # o Lock é barato e deixa a estrutura correta se alguém um dia
        # chamá-la de dentro de um endpoint `def` (que o FastAPI executa em
        # threadpool).
        self._lock = Lock()
        self._next_sweep = 0.0

    def retry_after(self, key: str, rule: RateLimitRule, now: float) -> int | None:
        """Segundos até liberar, ou None se ainda há orçamento."""
        with self._lock:
            window = self._state.get(key)
            if window is None or now - window.started_at >= rule.window_seconds:
                return None
            if window.count < rule.max_requests:
                return None
            return max(1, math.ceil(window.started_at + rule.window_seconds - now))

    def record(self, key: str, rule: RateLimitRule, now: float) -> None:
        with self._lock:
            self._sweep(now)
            window = self._state.get(key)
            if window is None or now - window.started_at >= rule.window_seconds:
                self._state[key] = _Window(count=1, started_at=now, window_seconds=rule.window_seconds)
            else:
                window.count += 1

    def reset(self, key: str) -> None:
        with self._lock:
            self._state.pop(key, None)

    def _sweep(self, now: float) -> None:
        """Descarta janelas vencidas. Sem isto, um scanner passando por
        milhares de IPs deixaria uma entrada por IP na memória pra sempre —
        o rate limit viraria o próprio vetor de exaustão."""
        if now < self._next_sweep:
            return
        self._next_sweep = now + self._SWEEP_INTERVAL_SECONDS
        stale = [k for k, w in self._state.items() if now - w.started_at >= w.window_seconds]
        for key in stale:
            del self._state[key]


@dataclass(frozen=True)
class RateLimitSettings:
    enabled: bool
    trust_forwarded_for: bool
    global_rule: RateLimitRule
    auth_rule: RateLimitRule
    register_rule: RateLimitRule

    @classmethod
    def from_env(cls, env: Env) -> RateLimitSettings:
        return cls(
            enabled=env.RATE_LIMIT_ENABLED,
            trust_forwarded_for=env.RATE_LIMIT_TRUST_FORWARDED_FOR,
            global_rule=RateLimitRule("global", env.RATE_LIMIT_MAX, env.RATE_LIMIT_WINDOW_SECONDS),
            auth_rule=RateLimitRule(
                "auth", env.RATE_LIMIT_AUTH_MAX, env.RATE_LIMIT_AUTH_WINDOW_SECONDS, count_only_failures=True
            ),
            register_rule=RateLimitRule(
                "register", env.RATE_LIMIT_REGISTER_MAX, env.RATE_LIMIT_REGISTER_WINDOW_SECONDS
            ),
        )


def client_ip(request: Request, trust_forwarded_for: bool) -> str:
    """IP do cliente.

    `X-Forwarded-For` é escrito pelo próprio cliente quando não há um proxy
    reescrevendo-o — confiar nele sem proxy à frente transforma o limite em
    decoração, porque basta variar o header a cada requisição pra ganhar um
    balde novo. Por isso o default é NÃO confiar; ligue
    RATE_LIMIT_TRUST_FORWARDED_FOR apenas quando a aplicação estiver
    comprovadamente atrás de um reverse proxy que sobrescreva o header.
    """
    if trust_forwarded_for:
        forwarded = request.headers.get("x-forwarded-for")
        if forwarded:
            return forwarded.split(",")[0].strip()
    return request.client.host if request.client else "unknown"


def _too_many_requests(request: Request, retry_after: int) -> JSONResponse:
    """Mesmo envelope de erro do resto da API ({code, message,
    correlation_id}) — o front trata 429 pelo `code`, como já faz com os
    demais erros de login."""
    return JSONResponse(
        status_code=429,
        content={
            "code": "rate_limited",
            "message": "Muitas requisições. Tente novamente em instantes.",
            "correlation_id": getattr(request.state, "correlation_id", None),
        },
        headers={"Retry-After": str(retry_after)},
    )


class RateLimitMiddleware(BaseHTTPMiddleware):
    def __init__(self, app, settings: RateLimitSettings | None = None) -> None:  # type: ignore[no-untyped-def]
        super().__init__(app)
        self._settings = settings or RateLimitSettings.from_env(load_env())
        self._counters = FixedWindowCounters()

    def _rules_for(self, path: str) -> list[RateLimitRule]:
        rules = [self._settings.global_rule]
        if path in AUTH_PATHS:
            rules.append(self._settings.auth_rule)
        elif path in REGISTER_PATHS:
            rules.append(self._settings.register_rule)
        return rules

    async def dispatch(self, request: Request, call_next):  # type: ignore[no-untyped-def]
        settings = self._settings
        path = request.url.path
        # OPTIONS é o preflight do CORS, disparado pelo próprio navegador
        # antes de cada requisição "não simples" — contá-lo dobraria o
        # consumo de todo cliente web sem medir nada de real.
        if not settings.enabled or request.method == "OPTIONS" or path in EXEMPT_PATHS:
            return await call_next(request)

        ip = client_ip(request, settings.trust_forwarded_for)
        rules = self._rules_for(path)
        now = time.monotonic()

        for rule in rules:
            retry_after = self._counters.retry_after(f"{rule.name}:{ip}", rule, now)
            if retry_after is not None:
                return _too_many_requests(request, retry_after)

        for rule in rules:
            if not rule.count_only_failures:
                self._counters.record(f"{rule.name}:{ip}", rule, now)

        response: Response = await call_next(request)

        for rule in rules:
            if not rule.count_only_failures:
                continue
            key = f"{rule.name}:{ip}"
            if response.status_code in FAILED_AUTH_STATUSES:
                self._counters.record(key, rule, time.monotonic())
            elif response.status_code < 400:
                self._counters.reset(key)

        return response
