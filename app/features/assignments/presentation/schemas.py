"""Modelos Pydantic do slice assignments.

Porta features/assignments/presentation/routes.ts (schemas inline no
Fastify original).
"""

from __future__ import annotations

from ....shared.http.camel_model import CamelModel


class AssignmentViewOut(CamelModel):
    id: str
    patient_code: str
    intern_id: str
    intern_name: str
    supervisor_id: str | None
    supervisor_name: str | None
    active: bool


class UpdateAssignmentRequest(CamelModel):
    # Pelo menos um dos dois — validado na rota (mensagem melhor que o
    # "anyOf" do JSON Schema, mesmo padrão dos outros slices).
    intern_id: str | None = None
    supervisor_id: str | None = None
    # False encerra o vínculo (e cancela as consultas futuras). Reativar não
    # é suportado: um vínculo novo nasce do pareamento.
    active: bool | None = None
