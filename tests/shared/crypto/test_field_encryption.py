"""Testes do formato de payload cifrado (v0 legado / v1 versionado).

O que está sob teste aqui não é o AES — é a `cryptography` que o
implementa — mas a compatibilidade entre formatos: dado gravado antes
desta mudança tem que continuar legível, sem migração, e o formato novo
tem que carregar consigo qual chave o gerou.
"""

from __future__ import annotations

import base64
import json
import os

import pytest
from cryptography.hazmat.primitives.ciphers.aead import AESGCM

from app.shared.crypto import field_encryption
from app.shared.crypto.field_encryption import (
    AUTH_TAG_LENGTH,
    IV_LENGTH,
    VERSION_1,
    decrypt_field,
    encrypt_field,
    is_legacy_payload,
)


@pytest.fixture(autouse=True)
def _limpa_cache_do_chaveiro() -> None:
    """O chaveiro é cacheado por processo (lru_cache). Os testes que trocam
    as variáveis de ambiente precisam invalidá-lo, senão herdam o chaveiro
    montado pelo teste anterior."""
    field_encryption._keyring.cache_clear()


def _legacy_encrypt(plaintext: str, key: bytes, first_iv_byte: int | None = None) -> bytes:
    """Reproduz o formato v0 — o mesmo layout [IV|tag|ciphertext] que o
    backend Node grava e que este projeto usou até aqui.

    `first_iv_byte` força o primeiro byte do IV: é como se constrói, de
    forma determinística, o payload legado que se disfarça de v1."""
    iv = os.urandom(IV_LENGTH)
    if first_iv_byte is not None:
        iv = bytes([first_iv_byte]) + iv[1:]
    ct_with_tag = AESGCM(key).encrypt(iv, plaintext.encode("utf-8"), None)
    return iv + ct_with_tag[-AUTH_TAG_LENGTH:] + ct_with_tag[:-AUTH_TAG_LENGTH]


def _active_key() -> bytes:
    from app.shared.config.env import load_env

    return base64.b64decode(load_env().ENCRYPTION_KEY)


def test_ida_e_volta_no_formato_novo() -> None:
    assert decrypt_field(encrypt_field("Maria da Silva")) == "Maria da Silva"


def test_grava_sempre_no_formato_v1() -> None:
    payload = encrypt_field("x")
    assert payload[0] == VERSION_1
    assert payload[1] == 1  # ENCRYPTION_KEY_ID default


def test_le_dado_gravado_no_formato_antigo() -> None:
    """O requisito que permite este módulo entrar em produção sem migrar
    nenhuma linha antes."""
    legado = _legacy_encrypt("Prontuário antigo", _active_key())
    assert decrypt_field(legado) == "Prontuário antigo"


def test_le_payload_antigo_que_comeca_com_o_byte_de_versao() -> None:
    """1 em 256 payloads v0 começa com 0x01 e se parece com um v1. A
    verificação do authTag é quem desfaz o engano — sem ela, esses dados
    ficariam ilegíveis de forma INTERMITENTE, que é o pior modo de falhar:
    passaria por toda a homologação e apareceria em produção como "um
    prontuário aqui e ali não abre"."""
    payload = _legacy_encrypt("Segredo", _active_key(), first_iv_byte=VERSION_1)
    assert payload[0] == VERSION_1  # indistinguível de um v1 pelo cabeçalho
    assert decrypt_field(payload) == "Segredo"
    assert is_legacy_payload(payload) is True


def test_reconhece_o_que_ainda_precisa_ser_reescrito() -> None:
    assert is_legacy_payload(_legacy_encrypt("antigo", _active_key())) is True
    assert is_legacy_payload(encrypt_field("novo")) is False


def test_decifra_com_chave_aposentada_apos_rotacao(monkeypatch: pytest.MonkeyPatch) -> None:
    """O cenário que o key_id existe pra permitir: dado cifrado com a chave
    velha e dado cifrado com a nova convivendo no mesmo banco."""
    from app.shared.config.env import load_env

    chave_velha = _active_key()
    cifrado_com_a_velha = encrypt_field("escrito antes da rotação")

    chave_nova = base64.b64encode(os.urandom(32)).decode()
    monkeypatch.setenv("ENCRYPTION_KEY", chave_nova)
    monkeypatch.setenv("ENCRYPTION_KEY_ID", "2")
    monkeypatch.setenv("ENCRYPTION_KEYS_RETIRED", json.dumps({"1": base64.b64encode(chave_velha).decode()}))
    load_env.cache_clear()
    field_encryption._keyring.cache_clear()

    try:
        assert decrypt_field(cifrado_com_a_velha) == "escrito antes da rotação"
        novo = encrypt_field("escrito depois")
        assert novo[1] == 2
        assert decrypt_field(novo) == "escrito depois"
    finally:
        load_env.cache_clear()
        field_encryption._keyring.cache_clear()


def test_recusa_chave_ativa_listada_como_aposentada(monkeypatch: pytest.MonkeyPatch) -> None:
    """Erro de configuração plausível numa rotação feita com pressa —
    e que deixaria o id 1 apontando pra duas chaves diferentes."""
    from app.shared.config.env import load_env

    monkeypatch.setenv("ENCRYPTION_KEYS_RETIRED", json.dumps({"1": base64.b64encode(os.urandom(32)).decode()}))
    load_env.cache_clear()
    field_encryption._keyring.cache_clear()
    try:
        with pytest.raises(ValueError, match="ativo ao mesmo tempo"):
            encrypt_field("x")
    finally:
        load_env.cache_clear()
        field_encryption._keyring.cache_clear()


def test_payload_adulterado_nao_decifra() -> None:
    """GCM autentica: mexer num byte do ciphertext tem que falhar, não
    devolver texto corrompido."""
    from cryptography.exceptions import InvalidTag

    payload = bytearray(encrypt_field("Diagnóstico"))
    payload[-1] ^= 0x01
    with pytest.raises(InvalidTag):
        decrypt_field(bytes(payload))
