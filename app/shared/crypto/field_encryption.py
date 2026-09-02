"""Criptografia de campo (PII em repouso) — AES-256-GCM.

Porta shared/crypto/field-encryption.ts. Formato do payload cifrado
idêntico ao original: [ 12 bytes IV | 16 bytes authTag | ciphertext ] — por
isso dado cifrado pelo backend Node continua legível aqui sem nenhuma
migração de dado. A chave (32 bytes) vem de ENCRYPTION_KEY (base64).
"""

from __future__ import annotations

import base64
import os

from cryptography.hazmat.primitives.ciphers.aead import AESGCM

from ..config.env import load_env

IV_LENGTH = 12
AUTH_TAG_LENGTH = 16


def _get_key() -> bytes:
    return base64.b64decode(load_env().ENCRYPTION_KEY)


def encrypt_field(plaintext: str) -> bytes:
    iv = os.urandom(IV_LENGTH)
    aesgcm = AESGCM(_get_key())
    # cryptography já anexa o auth tag (16 bytes) ao final do ciphertext —
    # mesmo layout que o Node produz separando cipher.final()+getAuthTag(),
    # só que aqui vem embutido; o formato final [iv|tag|ciphertext] é
    # remontado abaixo pra bater exatamente com o que o Node grava.
    ct_with_tag = aesgcm.encrypt(iv, plaintext.encode("utf-8"), None)
    ciphertext, auth_tag = ct_with_tag[:-AUTH_TAG_LENGTH], ct_with_tag[-AUTH_TAG_LENGTH:]
    return iv + auth_tag + ciphertext


def decrypt_field(payload: bytes) -> str:
    iv = payload[:IV_LENGTH]
    auth_tag = payload[IV_LENGTH : IV_LENGTH + AUTH_TAG_LENGTH]
    ciphertext = payload[IV_LENGTH + AUTH_TAG_LENGTH :]
    aesgcm = AESGCM(_get_key())
    plaintext = aesgcm.decrypt(iv, ciphertext + auth_tag, None)
    return plaintext.decode("utf-8")
