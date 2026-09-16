"""Criptografia de campo (PII em repouso) — AES-256-GCM.

FORMATO DO PAYLOAD
------------------

    v1 (atual):  [ 0x01 | key_id (1) | IV (12) | authTag (16) | ciphertext ]
    v0 (legado): [                     IV (12) | authTag (16) | ciphertext ]

O v0 é o formato que o backend Node gravava e que este módulo produzia até
aqui: bytes crus, sem nada dizendo QUAL chave ou QUAL algoritmo os gerou.
Isso é o que torna uma chave irrotacionável na prática — sem um
identificador no próprio dado, não há como manter duas chaves válidas ao
mesmo tempo, e trocar a chave exige reescrever o banco inteiro numa única
janela, sem poder voltar atrás.

O v1 acrescenta dois bytes: versão e id da chave. Com eles, uma rotação
passa a ser: registrar a chave nova como ativa, manter a antiga em
`ENCRYPTION_KEYS_RETIRED`, e reescrever as linhas no ritmo que der — dado
velho e dado novo convivem no mesmo banco enquanto durar.

`decrypt_field` lê os dois formatos, então nenhum dado precisa ser
migrado pra este módulo entrar em produção. A desambiguação é segura
porque o GCM autentica: se um payload v0 por acaso começar com 0x01 (1
chance em 256), a leitura como v1 desloca tudo em dois bytes e a
verificação do authTag falha — aí caímos no v0 e a leitura sai correta. É
o authTag fazendo o papel de discriminador, não um palpite sobre os bytes.

`encrypt_field` sempre grava v1.

ATENÇÃO à chave: `ENCRYPTION_KEY` também deriva o índice cego do CPF (ver
blind_index.py). Enquanto essas duas finalidades compartilharem a mesma
chave, rotacioná-la invalida todo `cpf_hash` já gravado — a rotação exige
recalcular o índice junto. Separar as duas finalidades é o passo seguinte,
e o `key_id` daqui é o que o deixa possível.
"""

from __future__ import annotations

import base64
import json
import os
from functools import lru_cache

from cryptography.exceptions import InvalidTag
from cryptography.hazmat.primitives.ciphers.aead import AESGCM

from ..config.env import load_env

IV_LENGTH = 12
AUTH_TAG_LENGTH = 16

VERSION_1 = 1
_V1_HEADER_LENGTH = 2  # versão + key_id
_V1_MINIMUM_LENGTH = _V1_HEADER_LENGTH + IV_LENGTH + AUTH_TAG_LENGTH

# Id atribuído ao payload v0 quando ele for reescrito como v1: o dado
# legado foi cifrado com a chave que hoje está em ENCRYPTION_KEY.
LEGACY_KEY_ID = 1


@lru_cache
def _keyring() -> dict[int, bytes]:
    """Chaves conhecidas, por id. A ativa (ENCRYPTION_KEY_ID) cifra e
    decifra; as aposentadas (ENCRYPTION_KEYS_RETIRED) só decifram — é o
    que permite ler dado antigo enquanto ele ainda não foi reescrito."""
    env = load_env()
    keys = {env.ENCRYPTION_KEY_ID: base64.b64decode(env.ENCRYPTION_KEY)}
    if env.ENCRYPTION_KEYS_RETIRED.strip():
        for raw_id, raw_key in json.loads(env.ENCRYPTION_KEYS_RETIRED).items():
            key_id = int(raw_id)
            if key_id == env.ENCRYPTION_KEY_ID:
                raise ValueError(
                    f"key_id {key_id} está em ENCRYPTION_KEYS_RETIRED e é o ENCRYPTION_KEY_ID ativo ao mesmo tempo."
                )
            keys[key_id] = base64.b64decode(raw_key)
    return keys


def _active_key_id() -> int:
    return load_env().ENCRYPTION_KEY_ID


def _key(key_id: int) -> bytes:
    keys = _keyring()
    if key_id not in keys:
        raise KeyError(f"Chave de criptografia id={key_id} não está configurada.")
    return keys[key_id]


def encrypt_field(plaintext: str) -> bytes:
    key_id = _active_key_id()
    iv = os.urandom(IV_LENGTH)
    aesgcm = AESGCM(_key(key_id))
    # `cryptography` devolve o authTag anexado ao fim do ciphertext; o
    # layout abaixo o traz pra frente, mantendo a ordem [IV|tag|ct] que o
    # v0 já usava — assim a única diferença entre os formatos é o cabeçalho.
    ct_with_tag = aesgcm.encrypt(iv, plaintext.encode("utf-8"), None)
    ciphertext, auth_tag = ct_with_tag[:-AUTH_TAG_LENGTH], ct_with_tag[-AUTH_TAG_LENGTH:]
    return bytes([VERSION_1, key_id]) + iv + auth_tag + ciphertext


def _decrypt_body(payload: bytes, key: bytes) -> str:
    iv = payload[:IV_LENGTH]
    auth_tag = payload[IV_LENGTH : IV_LENGTH + AUTH_TAG_LENGTH]
    ciphertext = payload[IV_LENGTH + AUTH_TAG_LENGTH :]
    return AESGCM(key).decrypt(iv, ciphertext + auth_tag, None).decode("utf-8")


def decrypt_field(payload: bytes) -> str:
    if len(payload) >= _V1_MINIMUM_LENGTH and payload[0] == VERSION_1:
        try:
            return _decrypt_body(payload[_V1_HEADER_LENGTH:], _key(payload[1]))
        except (InvalidTag, KeyError):
            # Não era um v1 de verdade — é um v0 cujo primeiro byte de IV
            # calhou de ser 0x01. Segue para a leitura legada.
            pass
    return _decrypt_body(payload, _key(LEGACY_KEY_ID))


def is_legacy_payload(payload: bytes) -> bool:
    """Se este valor ainda está no formato v0.

    Usado pela migração que reescreve os dados: sem isto, o backfill não
    tem como saber o que já converteu, e uma re-execução (por retomada
    após falha, por exemplo) tentaria cifrar de novo o que já está cifrado.
    """
    if len(payload) < _V1_MINIMUM_LENGTH or payload[0] != VERSION_1:
        return True
    try:
        _decrypt_body(payload[_V1_HEADER_LENGTH:], _key(payload[1]))
    except (InvalidTag, KeyError):
        return True
    return False
