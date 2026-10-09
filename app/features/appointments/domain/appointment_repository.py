"""Porta do repositório de agendamentos.

Porta features/appointments/domain/appointment-repository.ts. Todo método
recebe o AccessContext, que a implementação usa para abrir a transação com
o contexto de RLS setado — assim o banco filtra por vínculo mesmo que a
aplicação erre (defesa em profundidade).
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass
from datetime import datetime

from .appointment import Appointment, AppointmentStatus


@dataclass
class AccessContext:
    """Contexto de acesso (papel + usuário) propagado para a RLS do banco."""

    user_id: str
    role: str


@dataclass
class NewAppointment:
    patient_id: str
    intern_id: str
    scheduled_at: datetime
    notes: str | None = None
    room_id: str | None = None


class AppointmentRepository(ABC):
    @abstractmethod
    def create(self, ctx: AccessContext, data: NewAppointment) -> Appointment: ...

    @abstractmethod
    def list_for_actor(self, ctx: AccessContext) -> list[Appointment]:
        """Lista os agendamentos visíveis ao ator (RLS aplica o escopo por papel/vínculo)."""
        ...

    @abstractmethod
    def find_by_id(self, ctx: AccessContext, id: str) -> Appointment | None: ...

    @abstractmethod
    def update_status(self, ctx: AccessContext, id: str, status: AppointmentStatus) -> Appointment: ...

    @abstractmethod
    def cancel(self, ctx: AccessContext, id: str, following: bool) -> int:
        """Cancela a consulta; com `following`, também as seguintes ainda
        marcadas do mesmo par paciente↔estagiário. Devolve quantas."""
        ...

    @abstractmethod
    def reschedule(self, ctx: AccessContext, id: str, scheduled_at: datetime, room_id: str | None) -> Appointment:
        """Muda data/hora (e sala). Conflito de sala -> ConflictError."""
        ...
