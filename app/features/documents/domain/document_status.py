"""Máquina de estados dos documentos clínicos (seção B.2 da arquitetura).
O estagiário submete; o supervisor aprova/rejeita/solicita ajustes.
APROVADO_LOCKED é terminal (imutável — reforçado por trigger WORM no
banco).

Porta features/documents/domain/document-status.ts.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Literal

from ....shared.errors.app_error import InvalidTransitionError

DocStatus = Literal[
    "RASCUNHO", "ENVIADO_PARA_SUPERVISAO", "EM_REVISAO", "REVISAO_SOLICITADA", "REJEITADO", "APROVADO_LOCKED"
]
DocAction = Literal["SUBMIT", "TAKE", "REQUEST_CHANGES", "REJECT", "APPROVE", "REOPEN"]
ActorRole = Literal["INTERN", "SUPERVISOR", "ADMIN", "PATIENT"]


@dataclass(frozen=True)
class _Rule:
    to: DocStatus
    roles: tuple[ActorRole, ...]


_TRANSITIONS: dict[DocStatus, dict[DocAction, _Rule]] = {
    "RASCUNHO": {
        "SUBMIT": _Rule(to="ENVIADO_PARA_SUPERVISAO", roles=("INTERN",)),
    },
    "ENVIADO_PARA_SUPERVISAO": {
        "TAKE": _Rule(to="EM_REVISAO", roles=("SUPERVISOR",)),
        "APPROVE": _Rule(to="APROVADO_LOCKED", roles=("SUPERVISOR",)),
        "REQUEST_CHANGES": _Rule(to="REVISAO_SOLICITADA", roles=("SUPERVISOR",)),
        "REJECT": _Rule(to="REJEITADO", roles=("SUPERVISOR",)),
    },
    "EM_REVISAO": {
        "APPROVE": _Rule(to="APROVADO_LOCKED", roles=("SUPERVISOR",)),
        "REQUEST_CHANGES": _Rule(to="REVISAO_SOLICITADA", roles=("SUPERVISOR",)),
        "REJECT": _Rule(to="REJEITADO", roles=("SUPERVISOR",)),
    },
    "REVISAO_SOLICITADA": {
        "SUBMIT": _Rule(to="ENVIADO_PARA_SUPERVISAO", roles=("INTERN",)),
    },
    "REJEITADO": {
        "REOPEN": _Rule(to="RASCUNHO", roles=("INTERN",)),
    },
    "APROVADO_LOCKED": {},
}

# Ações do estagiário (autor) sobre o próprio documento.
AUTHOR_ACTIONS: tuple[DocAction, ...] = ("SUBMIT", "REOPEN")


def resolve_transition(current: DocStatus, action: DocAction, role: ActorRole) -> DocStatus:
    """Resolve o estado de destino de uma transição, validando o estado
    atual e o papel do ator. Lança InvalidTransitionError se a ação não é
    permitida."""
    rule = _TRANSITIONS.get(current, {}).get(action)
    if not rule:
        raise InvalidTransitionError(
            f"Ação {action} não permitida a partir de {current}.", {"current": current, "action": action}
        )
    if role not in rule.roles:
        raise InvalidTransitionError(f"Papel {role} não pode executar {action}.", {"role": role, "action": action})
    return rule.to


def is_editable(status: DocStatus) -> bool:
    """Documento é editável (rascunho) pelo estagiário?"""
    return status in ("RASCUNHO", "REVISAO_SOLICITADA")
