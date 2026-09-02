"""Porta do provedor de assinatura. Hoje há a implementação 'internal'
(hash autenticado + carimbo). Quando a aplicação for credenciada na
Assinatura Eletrônica gov.br, basta uma implementação 'govbr' desta
mesma interface.

Porta features/documents/domain/signature-provider.ts.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass


@dataclass
class SignaturePayload:
    document_id: str
    signer_id: str
    content_hash: str


@dataclass
class SignatureResult:
    signature_hash: str
    provider: str  # 'internal' | 'govbr'


class SignatureProvider(ABC):
    @abstractmethod
    def sign(self, payload: SignaturePayload) -> SignatureResult: ...
