"""Testes da slice health — equivalentes aos cenários que o backend Fastify
cobriria pra /health, /ready e /version (essa slice não tinha teste próprio
no TS original, mas o contrato é simples o bastante pra testar direto aqui).
"""

from fastapi.testclient import TestClient

from app.main import app

client = TestClient(app)


def test_health_liveness_sempre_ok() -> None:
    resp = client.get("/health")
    assert resp.status_code == 200
    assert resp.json() == {"status": "ok"}


def test_version_retorna_string() -> None:
    resp = client.get("/version")
    assert resp.status_code == 200
    assert "version" in resp.json()


def test_ready_contra_banco_real() -> None:
    """Teste de integração de verdade — exige o SQL Server local rodando
    (docker compose up mssql). Sem mock: se o banco cair, este teste falha,
    igual o endpoint real falharia em produção."""
    resp = client.get("/ready")
    assert resp.status_code == 200
    assert resp.json() == {"status": "ready"}
