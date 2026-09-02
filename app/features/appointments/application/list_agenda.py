"""Lista a agenda visível ao ator.

Porta features/appointments/application/list-agenda.ts. O escopo
(estagiário vê só a própria agenda; supervisor vê a dos vínculos que
supervisiona; admin vê tudo) é imposto pela RLS do banco — o caso de uso
apenas delega, sem replicar a regra de filtro.
"""

from __future__ import annotations

from ..domain.appointment import Appointment
from ..domain.appointment_repository import AccessContext, AppointmentRepository


class ListAgenda:
    def __init__(self, repo: AppointmentRepository) -> None:
        self._repo = repo

    def execute(self, actor: AccessContext) -> list[Appointment]:
        return self._repo.list_for_actor(actor)
