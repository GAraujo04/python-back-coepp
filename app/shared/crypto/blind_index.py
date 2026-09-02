"""Índice cego determinístico do CPF — HMAC-SHA256 dos dígitos.

Porta shared/crypto/blind-index.ts. Mesmo algoritmo e mesma chave —
produz o MESMO hash que o backend Node, então o índice já gravado no banco
(cpf_hash) continua funcionando sem re-processar nenhuma linha.
"""

from __future__ import annotations

import base64
import hashlib
import hmac
import re

from ..config.env import load_env


def cpf_blind_index(cpf: str) -> str:
    digits = re.sub(r"\D", "", cpf)
    key = base64.b64decode(load_env().ENCRYPTION_KEY)
    return hmac.new(key, digits.encode("utf-8"), hashlib.sha256).hexdigest()
