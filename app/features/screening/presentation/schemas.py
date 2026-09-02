"""Modelos Pydantic do slice screening.

Porta features/screening/presentation/schemas.ts. O content é validado
por Pydantic (screening_content.py) no caso de uso, não aqui — chega/sai
como dict solto (JSON opaco), igual ao `additionalProperties: true` do
JSON Schema original.
"""

from __future__ import annotations

from typing import Literal

from pydantic import Field

from ....shared.http.camel_model import CamelModel
from ....shared.http.utc_datetime import UtcDatetime


class SignatureOut(CamelModel):
    signer_name: str
    signer_role: str
    signer_ref: str | None
    provider: str
    signed_at: UtcDatetime


class ScreeningOut(CamelModel):
    id: str
    numero: str | None
    type: Literal["SCREENING_ADULT", "SCREENING_CHILD"]
    status: str
    version: int
    patient_id: str
    author_id: str
    co_author_ids: list[str]
    content: dict[str, object]
    signatures: list[SignatureOut]
    created_at: UtcDatetime
    updated_at: UtcDatetime


class CreateScreeningRequest(CamelModel):
    type: Literal["SCREENING_ADULT", "SCREENING_CHILD"]
    patient_id: str
    co_author_ids: list[str] = Field(default_factory=list)
    content: dict[str, object] = Field(default_factory=dict)


class UpdateDraftRequest(CamelModel):
    content: dict[str, object]
    expected_version: int = Field(ge=1)
