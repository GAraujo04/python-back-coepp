"""Modelos Pydantic do slice documents.

Porta features/documents/presentation/routes.ts (schemas inline no
Fastify original).
"""

from __future__ import annotations

from typing import Literal

from ....shared.http.camel_model import CamelModel
from ....shared.http.utc_datetime import UtcDatetime

DocActionIn = Literal["SUBMIT", "TAKE", "REQUEST_CHANGES", "REJECT", "APPROVE", "REOPEN"]


class TransitionRequest(CamelModel):
    action: DocActionIn
    comment: str | None = None


class TransitionResponse(CamelModel):
    id: str
    status: str


class QueueItemOut(CamelModel):
    id: str
    numero: str | None
    type: str
    status: str
    author_name: str
    # None para o supervisor (ver shared/privacy/patient_name.py).
    patient_name: str | None
    patient_code: str
    updated_at: UtcDatetime


class ReportItemOut(QueueItemOut):
    author_id: str
    submitted_at: UtcDatetime


class SignatureOut(CamelModel):
    signer_name: str
    signer_role: str
    signer_ref: str | None
    provider: str
    signed_at: UtcDatetime


class CommentOut(CamelModel):
    id: str
    body: str
    reviewer_name: str
    created_at: UtcDatetime


class DocForReviewOut(QueueItemOut):
    content: dict[str, object]
    comments: list[CommentOut]
    signatures: list[SignatureOut]
