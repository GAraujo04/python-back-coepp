"""Porta do repositório de triagens (clinical_documents dos tipos SCREENING_*).

Porta features/screening/domain/screening-repository.ts.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from datetime import datetime
from typing import Literal

from .screening_content import ScreeningType

ScreeningStatus = Literal[
    "RASCUNHO", "ENVIADO_PARA_SUPERVISAO", "EM_REVISAO", "REVISAO_SOLICITADA", "REJEITADO", "APROVADO_LOCKED"
]


@dataclass
class AccessContext:
    user_id: str
    role: str


@dataclass
class NewScreening:
    type: ScreeningType
    patient_id: str
    author_id: str
    co_author_ids: list[str]
    content: dict[str, object]


@dataclass
class SignatureInfo:
    signer_name: str
    signer_role: str
    signer_ref: str | None
    provider: str
    signed_at: datetime


@dataclass
class ScreeningRecord:
    id: str
    numero: str | None
    type: ScreeningType
    status: ScreeningStatus
    version: int
    patient_id: str
    author_id: str
    co_author_ids: list[str]
    content: dict[str, object]
    created_at: datetime
    updated_at: datetime
    signatures: list[SignatureInfo] = field(default_factory=list)


class ScreeningRepository(ABC):
    @abstractmethod
    def create(self, ctx: AccessContext, data: NewScreening) -> ScreeningRecord: ...

    @abstractmethod
    def list_for_actor(self, ctx: AccessContext) -> list[ScreeningRecord]: ...

    @abstractmethod
    def find_by_id(self, ctx: AccessContext, id: str) -> ScreeningRecord | None: ...

    @abstractmethod
    def update_draft(
        self, ctx: AccessContext, id: str, content: dict[str, object], expected_version: int
    ) -> ScreeningRecord:
        """Atualiza o content do rascunho com concorrência otimista (expected_version)."""
        ...

    @abstractmethod
    def delete(self, ctx: AccessContext, id: str) -> None:
        """Remove o documento. Autorização final garantida pela RLS (BLOCK PREDICATE)."""
        ...
