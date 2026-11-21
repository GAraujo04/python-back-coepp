"""Modelos Pydantic do slice matching.

Porta features/matching/presentation/routes.ts (schemas inline no
Fastify original).
"""

from __future__ import annotations

from typing import Literal

from pydantic import Field

from ....shared.http.camel_model import CamelModel

WarningCode = Literal[
    "TIME_INCOMPATIBLE_PATIENT", "TIME_INCOMPATIBLE_INTERN", "ROOM_OCCUPIED", "PATIENT_ALREADY_ASSIGNED"
]


class WarningOut(CamelModel):
    code: WarningCode
    message: str


class MatchResultOut(CamelModel):
    proposal_id: str
    intern_id: str
    patient_id: str
    room_id: str | None
    scheduled_at: str


class RunMatchingResponse(CamelModel):
    # Propostas criadas nesta rodada (aguardam o administrativo salvar).
    matched: int
    results: list[MatchResultOut]


class MatchProposalOut(CamelModel):
    id: str
    patient_id: str
    patient_code: str
    intern_id: str
    intern_name: str
    room_id: str | None
    room_name: str | None
    scheduled_at: str


class ConfirmMatchProposalRequest(CamelModel):
    scheduled_at: str
    room_id: str | None = None


class ConfirmMatchProposalResponse(CamelModel):
    appointment_id: str


class MatchViewOut(CamelModel):
    appointment_id: str
    scheduled_at: str
    status: str
    # Com patient_code, identifica o par: a tela agrupa as consultas da série por ele.
    intern_id: str
    intern_name: str
    patient_name: str | None  # None para o supervisor
    patient_code: str
    room_name: str | None


class MatchSuggestionOut(CamelModel):
    patient_id: str
    patient_code: str
    intern_id: str
    intern_name: str
    room_id: str
    room_name: str
    scheduled_at: str


class WindowOut(CamelModel):
    weekday: int  # 0=domingo .. 6=sábado
    start_time: str
    end_time: str


class UnmatchedPatientOut(CamelModel):
    id: str
    code: str
    is_minor: bool
    has_disability: bool
    windows: list[WindowOut]
    registered_at: str
    no_match_since: str | None


class UnmatchedInternOut(CamelModel):
    id: str
    name: str
    ra: str | None
    windows: list[WindowOut]


class UnmatchedOut(CamelModel):
    patients: list[UnmatchedPatientOut]
    interns: list[UnmatchedInternOut]


class PendingMatchRequestOut(CamelModel):
    id: str
    patient_code: str
    suggested_intern_name: str | None
    suggested_at: str | None
    status: str
    created_at: str


class CreateManualMatchRequest(CamelModel):
    patient_id: str
    intern_id: str
    scheduled_at: str
    room_id: str | None = None
    acknowledge_warnings: bool = False


class CreateManualMatchResponse(CamelModel):
    appointment_id: str
    warnings: list[WarningOut] = Field(default_factory=list)
