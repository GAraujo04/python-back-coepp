"""Gravador de auditoria append-only com cadeia de hash:
    row_hash = sha256(prev_hash + payload_canônico)

Porta shared/audit/prisma-audit-recorder.ts. Qualquer adulteração/remoção
de um registro quebra a cadeia dos seguintes — o trigger
`trg_audit_log_append_only` (no banco, inalterado por esta migração)
rejeita UPDATE/DELETE incondicionalmente. Um lock de aplicação por
transação (sp_getapplock — ver applock.py) garante ordenação consistente
sob concorrência.
"""

from __future__ import annotations

import hashlib
import json
from datetime import UTC, datetime

from sqlalchemy import text
from sqlalchemy.orm import Session

from ..db.applock import with_app_lock
from .audit_recorder import AuditEvent, AuditRecorder

AUDIT_LOCK_RESOURCE = "audit_log_chain"


class SqlAuditRecorder(AuditRecorder):
    def __init__(self, session: Session) -> None:
        self._session = session

    def record(self, event: AuditEvent) -> None:
        occurred_at = datetime.now(UTC)

        def _write() -> None:
            last_hash = self._session.execute(text("SELECT TOP 1 row_hash FROM audit_log ORDER BY id DESC")).scalar()

            # json.dumps com separators sem espaço extra pra bater com o
            # JSON.stringify do Node (ambos compactos) — só importa que a
            # cadeia de hash seja internamente consistente daqui pra frente;
            # não precisa reproduzir bit a bit o formato usado pelo TS antes
            # da migração, já que cada backend só valida a própria cadeia.
            canonical = json.dumps(
                {
                    "occurredAt": occurred_at.isoformat(),
                    "actorId": event.actor_id,
                    "action": event.action,
                    "resourceType": event.resource_type,
                    "resourceId": event.resource_id,
                    "correlationId": event.correlation_id,
                    "diff": event.diff,
                },
                separators=(",", ":"),
            )
            row_hash = hashlib.sha256(((last_hash or "") + canonical).encode("utf-8")).hexdigest()

            self._session.execute(
                text(
                    "INSERT INTO audit_log "
                    "(occurred_at, actor_id, action, resource_type, resource_id, correlation_id, ip, "
                    " user_agent, diff, prev_hash, row_hash) "
                    "VALUES (:occurred_at, :actor_id, :action, :resource_type, :resource_id, :correlation_id, "
                    " :ip, :user_agent, :diff, :prev_hash, :row_hash)"
                ),
                {
                    "occurred_at": occurred_at,
                    "actor_id": event.actor_id,
                    "action": event.action,
                    "resource_type": event.resource_type,
                    "resource_id": event.resource_id,
                    "correlation_id": event.correlation_id,
                    "ip": event.ip,
                    "user_agent": event.user_agent,
                    "diff": json.dumps(event.diff) if event.diff is not None else None,
                    "prev_hash": last_hash,
                    "row_hash": row_hash,
                },
            )

        with_app_lock(self._session, AUDIT_LOCK_RESOURCE, _write)
