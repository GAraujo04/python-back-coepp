"""Avisos internos (o sininho), calculados a partir do estado que já existe.

Dois tipos:
- PENDÊNCIA (`actionable`): algo a fazer. Aparece enquanto existir —
  documento esperando revisão, ajuste solicitado — e some quando resolvido.
  Não há "marcar como lida": o aviso é o próprio trabalho pendente.
- INFORMATIVO: algo que aconteceu (documento aprovado/rejeitado). Fica
  visível por INFO_WINDOW e conta no sininho só até a pessoa abrir a lista
  (users.notifications_seen_at).

O texto fica no front (rótulos de tipo de documento, i18n); aqui só o
fato: tipo do aviso, quantidade e a quem ele se refere.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta
from typing import Literal

INFO_WINDOW = timedelta(days=14)

NotificationKind = Literal[
    "REVIEW_QUEUE",  # supervisor: documentos aguardando revisão
    "AVAILABILITY_REQUESTS",  # supervisor/admin: pedidos de alteração de disponibilidade
    "PENDING_MATCHES",  # admin: pacientes sem pareamento exato
    "ASSIGNMENTS_WITHOUT_SUPERVISOR",  # admin: vínculos sem supervisor (documentos ficam fora da fila)
    "CHANGES_REQUESTED",  # estagiário: supervisor pediu ajustes
    "AVAILABILITY_UNLOCKED",  # estagiário: pode alterar a disponibilidade
    "DOCUMENT_APPROVED",  # estagiário: informativo
    "DOCUMENT_REJECTED",  # estagiário: informativo
]


@dataclass
class Notification:
    kind: NotificationKind
    actionable: bool
    at: datetime | None = None
    count: int = 1
    document_id: str | None = None
    doc_type: str | None = None
    patient_code: str | None = None
    until: datetime | None = None


def is_unseen(n: Notification, seen_at: datetime | None) -> bool:
    """Informativo que aconteceu depois da última vez que a pessoa abriu a
    lista. Pendência nunca é "vista": vale enquanto existir."""
    return not n.actionable and n.at is not None and (seen_at is None or n.at > seen_at)


def unread_count(items: list[Notification], seen_at: datetime | None) -> int:
    """Número do sininho: toda pendência (pela quantidade — 12 documentos
    na fila contam 12) mais os informativos ainda não vistos."""
    pending = sum(n.count for n in items if n.actionable)
    return pending + sum(1 for n in items if is_unseen(n, seen_at))


def sort_for_display(items: list[Notification]) -> list[Notification]:
    """Pendências primeiro; dentro de cada grupo, o mais recente no topo."""
    return sorted(items, key=lambda n: (not n.actionable, -(n.at.timestamp() if n.at else 0)))
