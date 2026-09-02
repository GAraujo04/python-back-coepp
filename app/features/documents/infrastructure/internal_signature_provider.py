"""Assinatura interna: HMAC-SHA256 sobre (documento | assinante | hash do
conteúdo | carimbo de tempo), com a chave do sistema. Prova autenticada
de que aquele usuário assinou aquele conteúdo naquele instante.
Substituível pelo gov.br.

Porta features/documents/infrastructure/internal-signature-provider.ts.
"""

from __future__ import annotations

import base64
import hashlib
import hmac
from datetime import UTC, datetime

from ....shared.config.env import load_env
from ....shared.http.utc_datetime import to_iso_utc
from ..domain.signature_provider import SignaturePayload, SignatureProvider, SignatureResult


class InternalSignatureProvider(SignatureProvider):
    def sign(self, payload: SignaturePayload) -> SignatureResult:
        ts = to_iso_utc(datetime.now(UTC).replace(tzinfo=None))
        key = base64.b64decode(load_env().ENCRYPTION_KEY)
        message = f"{payload.document_id}|{payload.signer_id}|{payload.content_hash}|{ts}"
        signature_hash = hmac.new(key, message.encode("utf-8"), hashlib.sha256).hexdigest()
        return SignatureResult(signature_hash=signature_hash, provider="internal")
