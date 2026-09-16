"""Conteúdo clínico em JSON, cifrado em repouso.

`clinical_documents.content` guarda a triagem, a evolução, o laudo — o
relato clínico em si. Estava em NVARCHAR(MAX) em claro: quem lesse a
tabela (um backup extraviado, um dump, uma credencial de banco vazada)
lia o prontuário inteiro. A RLS que protege essa tabela é controle de
ACESSO, e controle de acesso não vale nada fora do processo que o aplica.

A forma canônica do JSON (`separators=(",", ":")`, sem espaços, e
`ensure_ascii=False`) é a mesma que `TransitionDocument` já usava pra
calcular o hash das assinaturas — mantida idêntica de propósito: o dígito
gravado em `clinical_documents.content_hash` e o que vai para a assinatura
descrevem os MESMOS bytes, então "o conteúdo mudou desde a aprovação"
continua sendo uma comparação de igualdade, não uma reinterpretação.

Por que um hash separado, se o conteúdo já está cifrado: o AES-GCM usa IV
aleatório a cada operação, então cifrar duas vezes o mesmo texto produz
bytes diferentes. Qualquer regra que precise responder "isto mudou?" —
como o trigger de imutabilidade (WORM) do documento APROVADO_LOCKED —
deixaria de funcionar comparando o ciphertext, porque ele muda mesmo
quando o conteúdo não muda. O hash do texto claro é o que preserva essa
pergunta.
"""

from __future__ import annotations

import hashlib
import json
from typing import Any

from .field_encryption import decrypt_field, encrypt_field


def canonical_json(value: Any) -> str:
    """Serialização estável — mesma convenção do JSON.stringify do JS, que
    é o que o backend Node produzia para o mesmo conteúdo."""
    return json.dumps(value, separators=(",", ":"), ensure_ascii=False)


def content_digest(value: Any) -> str:
    """SHA-256 do conteúdo em claro, em hex."""
    return hashlib.sha256(canonical_json(value).encode("utf-8")).hexdigest()


def encrypt_json(value: Any) -> bytes:
    return encrypt_field(canonical_json(value))


def decrypt_json(payload: bytes) -> dict[str, Any]:
    loaded: dict[str, Any] = json.loads(decrypt_field(payload))
    return loaded
