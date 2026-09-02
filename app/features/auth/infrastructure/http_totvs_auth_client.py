"""Adapter real do TotvsAuthClient — as duas chamadas HTTP ao TOTVS RM
(token + consulta de vínculo). Nunca loga senha/token.

Porta features/auth/infrastructure/http-totvs-auth-client.ts. `httpx` no
lugar do `fetch` nativo do Node — mesma semântica (timeout, 1 retry só
pra erro de rede/timeout ou 5xx, nunca em 4xx).
"""

from __future__ import annotations

from dataclasses import dataclass
from urllib.parse import quote

import httpx

from ..application.ports import (
    TotvsAuthClient,
    TotvsInvalidCredentialsError,
    TotvsProtocolError,
    TotvsTokenResult,
    TotvsUnavailableError,
    TotvsVinculo,
)


@dataclass
class HttpTotvsAuthClientConfig:
    base_url: str
    timeout_seconds: float
    sentenca: str
    coligada: str
    sistema: str
    param_nome: str
    param_com_aspas: bool


def _request_with_one_retry(client: httpx.Client, method: str, url: str, **kwargs: object) -> httpx.Response:
    """No máximo 1 retry, só para erro de rede/timeout ou 5xx — nunca em 4xx."""
    try:
        res = client.request(method, url, **kwargs)  # type: ignore[arg-type]
        if res.status_code >= 500:
            return client.request(method, url, **kwargs)  # type: ignore[arg-type]
        return res
    except httpx.HTTPError:
        # Erro de rede/timeout na 1ª tentativa — tenta mais uma vez; se
        # falhar de novo, propaga (o chamador trata como TotvsUnavailableError).
        return client.request(method, url, **kwargs)  # type: ignore[arg-type]


class HttpTotvsAuthClient(TotvsAuthClient):
    def __init__(self, config: HttpTotvsAuthClientConfig) -> None:
        self._config = config

    def authenticate(self, usuario: str, senha: str) -> TotvsTokenResult:
        url = f"{self._config.base_url}/api/connect/token"
        try:
            with httpx.Client(timeout=self._config.timeout_seconds) as client:
                res = _request_with_one_retry(
                    client,
                    "POST",
                    url,
                    headers={"Content-Type": "application/json"},
                    # NUNCA logar este body (contém a senha em texto claro)
                    # — só ele é construído aqui e enviado direto ao httpx,
                    # nunca passado a log.
                    json={"grant_type": "password", "username": usuario, "password": senha},
                )
        except httpx.HTTPError as exc:
            raise TotvsUnavailableError("Falha de conexão ao autenticar no TOTVS.") from exc

        if res.status_code in (400, 401, 403):
            raise TotvsInvalidCredentialsError("Credenciais TOTVS inválidas.")
        if not res.is_success:
            raise TotvsUnavailableError(
                f"TOTVS respondeu {res.status_code} na autenticação.", {"status": res.status_code}
            )

        try:
            body = res.json()
        except ValueError as exc:
            raise TotvsProtocolError("Resposta de token do TOTVS não é um JSON válido.") from exc
        # access_token nunca é logado — só extraído e devolvido em memória.
        access_token = body.get("access_token") if isinstance(body, dict) else None
        if not isinstance(access_token, str) or not access_token:
            raise TotvsProtocolError("Resposta de token do TOTVS não trouxe access_token.")
        return TotvsTokenResult(access_token=access_token)

    def consultar_vinculo(self, usuario: str, access_token: str) -> list[TotvsVinculo]:
        # Formato ainda não validado pelo TOTVS (ver env.py) — tudo
        # parametrizado pra corrigir via variável de ambiente, sem tocar
        # este código.
        inner_param = f"{self._config.param_nome}=" + (f'"{usuario}"' if self._config.param_com_aspas else usuario)
        url = (
            f"{self._config.base_url}/api/framework/v1/consultaSQLServer/RealizaConsulta/"
            f"{self._config.sentenca}/{self._config.coligada}/{self._config.sistema}/"
            f"?parameters={quote(inner_param)}"
        )

        try:
            with httpx.Client(timeout=self._config.timeout_seconds) as client:
                # Authorization vai só no header — nunca aparece na URL logada acima.
                res = _request_with_one_retry(client, "GET", url, headers={"Authorization": f"Bearer {access_token}"})
        except httpx.HTTPError as exc:
            raise TotvsUnavailableError("Falha de conexão ao consultar vínculo no TOTVS.", {"totvsUrl": url}) from exc

        if not res.is_success:
            raise TotvsUnavailableError(
                f"TOTVS respondeu {res.status_code} na consulta de vínculo.",
                {"totvsUrl": url, "status": res.status_code},
            )

        try:
            body = res.json()
        except ValueError as exc:
            raise TotvsProtocolError("Resposta de vínculo do TOTVS não é um JSON válido.", {"totvsUrl": url}) from exc
        if not isinstance(body, list):
            raise TotvsProtocolError("Resposta de vínculo do TOTVS não é um array.", {"totvsUrl": url})

        vinculos: list[TotvsVinculo] = []
        for index, item in enumerate(body):
            nome = item.get("NOME") if isinstance(item, dict) else None
            tipo = item.get("TIPO") if isinstance(item, dict) else None
            if not isinstance(nome, str) or not isinstance(tipo, str):
                raise TotvsProtocolError(
                    f"Item {index} da resposta de vínculo do TOTVS não tem NOME/TIPO string.", {"totvsUrl": url}
                )
            # EMAIL é novo na sentença Retorna_Vinculo — opcional, nunca
            # vaza pra um TotvsProtocolError por sua ausência.
            email_raw = item.get("EMAIL") if isinstance(item, dict) else None
            email = email_raw if isinstance(email_raw, str) and email_raw.strip() != "" else None
            vinculos.append(TotvsVinculo(nome=nome, tipo=tipo, email=email))
        return vinculos
