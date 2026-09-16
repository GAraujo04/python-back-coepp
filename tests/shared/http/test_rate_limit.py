"""Testes do rate limit por IP.

Montam um app FastAPI mínimo em volta do middleware — sem banco, sem as
rotas reais — porque o que está sob teste é a política (quantas passam,
quando bloqueia, o que zera o contador), não as slices. Os caminhos usados
são os reais (`/api/auth/login` etc.) porque a classificação por caminho
faz parte da política.
"""

from __future__ import annotations

from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.shared.http.rate_limit import (
    FixedWindowCounters,
    RateLimitMiddleware,
    RateLimitRule,
    RateLimitSettings,
)

SETTINGS = RateLimitSettings(
    enabled=True,
    trust_forwarded_for=False,
    global_rule=RateLimitRule("global", max_requests=5, window_seconds=60),
    auth_rule=RateLimitRule("auth", max_requests=2, window_seconds=900, count_only_failures=True),
    register_rule=RateLimitRule("register", max_requests=2, window_seconds=3600),
)


def build_client(settings: RateLimitSettings = SETTINGS) -> TestClient:
    app = FastAPI()
    app.add_middleware(RateLimitMiddleware, settings=settings)

    @app.get("/api/patients")
    def patients() -> dict[str, str]:
        return {"ok": "sim"}

    @app.get("/health")
    def health() -> dict[str, str]:
        return {"status": "ok"}

    @app.post("/api/auth/login")
    def login(body: dict[str, str]) -> dict[str, str]:
        from app.shared.errors.app_error import UnauthorizedError

        if body.get("password") != "certa":
            raise UnauthorizedError("E-mail ou senha inválidos.")
        return {"access_token": "jwt"}

    @app.post("/api/register/patient")
    def register() -> dict[str, str]:
        return {"id": "p1"}

    from app.shared.errors.app_error import AppError
    from app.shared.http.error_handler import register_error_handlers

    register_error_handlers(app)
    assert AppError  # o handler acima é quem converte UnauthorizedError em 401
    return TestClient(app)


def test_permite_ate_o_teto_e_bloqueia_a_proxima() -> None:
    client = build_client()
    for _ in range(5):
        assert client.get("/api/patients").status_code == 200

    resp = client.get("/api/patients")
    assert resp.status_code == 429
    assert resp.json()["code"] == "rate_limited"
    # Retry-After diz ao cliente QUANDO voltar; sem ele, um cliente bem
    # comportado só tem a opção de tentar de novo às cegas.
    assert int(resp.headers["Retry-After"]) > 0


def test_sondas_de_saude_ficam_fora_do_limite() -> None:
    """/health e /ready são chamados em intervalo fixo e curto pelo
    orquestrador — limitá-los transformaria o rate limit em falso alarme de
    indisponibilidade."""
    client = build_client()
    for _ in range(20):
        assert client.get("/health").status_code == 200


def test_login_bem_sucedido_nao_consome_o_balde_de_auth() -> None:
    """A clínica inteira sai por um IP só (NAT). Se logins válidos gastassem
    orçamento, o limite estreito derrubaria a recepção junto com o
    atacante."""
    client = build_client()
    for _ in range(5):
        assert client.post("/api/auth/login", json={"password": "certa"}).status_code == 200


def test_bloqueia_apos_tentativas_de_login_falhas() -> None:
    client = build_client()
    for _ in range(2):
        assert client.post("/api/auth/login", json={"password": "errada"}).status_code == 401

    resp = client.post("/api/auth/login", json={"password": "errada"})
    assert resp.status_code == 429
    assert resp.json()["code"] == "rate_limited"


def test_login_valido_zera_o_debito_de_tentativas_falhas() -> None:
    client = build_client()
    assert client.post("/api/auth/login", json={"password": "errada"}).status_code == 401
    assert client.post("/api/auth/login", json={"password": "certa"}).status_code == 200
    # Errar a senha duas vezes e acertar na terceira não pode deixar o
    # usuário devendo — depois do acerto, o orçamento volta ao cheio.
    for _ in range(2):
        assert client.post("/api/auth/login", json={"password": "errada"}).status_code == 401


def test_autocadastro_publico_conta_todas_as_requisicoes() -> None:
    """Aqui não há 'falha' a distinguir: o abuso é o próprio volume
    (cadastro em massa), então todo request debita."""
    client = build_client()
    for _ in range(2):
        assert client.post("/api/register/patient").status_code == 200
    assert client.post("/api/register/patient").status_code == 429


def test_desligado_por_configuracao_nao_limita_nada() -> None:
    client = build_client(
        RateLimitSettings(
            enabled=False,
            trust_forwarded_for=False,
            global_rule=RateLimitRule("global", 1, 60),
            auth_rule=RateLimitRule("auth", 1, 900, count_only_failures=True),
            register_rule=RateLimitRule("register", 1, 3600),
        )
    )
    for _ in range(10):
        assert client.get("/api/patients").status_code == 200


def test_janela_expirada_libera_novo_orcamento() -> None:
    """Sem relógio falso: chama o contador direto, avançando o `now` que ele
    recebe (é monotônico e injetado, justamente pra ser testável sem
    esperar 60s de verdade)."""
    counters = FixedWindowCounters()
    rule = RateLimitRule("global", max_requests=2, window_seconds=60)

    counters.record("global:1.2.3.4", rule, now=100.0)
    counters.record("global:1.2.3.4", rule, now=101.0)
    assert counters.retry_after("global:1.2.3.4", rule, now=102.0) == 58

    assert counters.retry_after("global:1.2.3.4", rule, now=161.0) is None


def test_contadores_nao_crescem_para_sempre() -> None:
    """Um scanner passando por milhares de IPs não pode deixar uma entrada
    por IP na memória — senão o rate limit vira o próprio vetor de
    exaustão."""
    counters = FixedWindowCounters()
    rule = RateLimitRule("global", max_requests=100, window_seconds=60)

    for i in range(500):
        counters.record(f"global:10.0.0.{i}", rule, now=100.0)
    assert len(counters._state) == 500

    # Passada a janela, a próxima escrita varre o que venceu.
    counters.record("global:novo", rule, now=400.0)
    assert len(counters._state) == 1
