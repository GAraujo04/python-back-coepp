"""Variante mockada do TotvsAuthClient para desenvolvimento (TOTVS_MOCK=True
— NUNCA em produção, ver a trava em app/main.py).

Porta features/auth/infrastructure/mock-totvs-auth-client.ts. Mesmos
cenários fixos, selecionados pelo valor de `usuario` (11 dígitos):
  - 11111111111 → aluno válido (TIPO=A), senha "mock123"
  - 22222222222 → só funcionário (TIPO=F), senha "mock123"
  - 33333333333 → múltiplos vínculos (A + F), senha "mock123"
  - 44444444444 → TIPO desconhecido ("X"), senha "mock123"
  - 55555555555 → array de vínculo vazio, senha "mock123"
  - 99999999999 → serviço fora do ar (simula TotvsUnavailableError)
  - qualquer outro usuário, ou senha diferente de "mock123" → credencial inválida
"""

from __future__ import annotations

from ..application.ports import (
    TotvsAuthClient,
    TotvsInvalidCredentialsError,
    TotvsTokenResult,
    TotvsUnavailableError,
    TotvsVinculo,
)

_SENHA_VALIDA = "mock123"

_VINCULOS: dict[str, list[TotvsVinculo]] = {
    "11111111111": [TotvsVinculo(nome="Estagiário Mock Válido", tipo="A", email="estagiario.mock@fsa.br")],
    "22222222222": [TotvsVinculo(nome="Funcionário Mock", tipo="F", email="funcionario.mock@fsa.br")],
    "33333333333": [
        TotvsVinculo(nome="Pessoa Mock Múltiplo Vínculo", tipo="A", email="multiplo.mock@fsa.br"),
        TotvsVinculo(nome="Pessoa Mock Múltiplo Vínculo", tipo="F", email="multiplo.mock@fsa.br"),
    ],
    "44444444444": [TotvsVinculo(nome="Pessoa Mock Tipo Desconhecido", tipo="X", email=None)],
    "55555555555": [],
}


class MockTotvsAuthClient(TotvsAuthClient):
    def authenticate(self, usuario: str, senha: str) -> TotvsTokenResult:
        if usuario == "99999999999":
            raise TotvsUnavailableError("[mock] TOTVS simulado fora do ar.")
        if senha != _SENHA_VALIDA or usuario not in _VINCULOS:
            raise TotvsInvalidCredentialsError("[mock] Credenciais TOTVS inválidas.")
        return TotvsTokenResult(access_token=f"mock-token-{usuario}")

    def consultar_vinculo(self, usuario: str, access_token: str) -> list[TotvsVinculo]:
        return _VINCULOS.get(usuario, [])
