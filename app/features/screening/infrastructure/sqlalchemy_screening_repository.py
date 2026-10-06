"""Adapter SQLAlchemy do ScreeningRepository. Toda operação roda sob RLS
(with_rls_context).

Porta features/screening/infrastructure/prisma-screening-repository.ts.
"""

from __future__ import annotations

from datetime import UTC, datetime
from typing import get_args

from sqlalchemy import select
from sqlalchemy.orm import Session

from ....shared.crypto.json_field import content_digest, decrypt_json, encrypt_json
from ....shared.db.applock import with_app_lock
from ....shared.db.models import ClinicalDocument, User
from ....shared.db.session import with_rls_context
from ....shared.errors.app_error import ConflictError, NotFoundError
from ..domain.screening_content import ScreeningType
from ..domain.screening_repository import (
    SCREENING_ONCE_TYPES,
    AccessContext,
    NewScreening,
    ScreeningRecord,
    ScreeningRepository,
    SignatureInfo,
)

# Deriva do Literal do domínio em vez de repetir a lista: um tipo novo
# aparece na listagem sozinho, sem depender de alguém lembrar deste
# arquivo (era o que faria o documento ser criado e nunca listado).
_SCREENING_TYPES = get_args(ScreeningType)


def _next_numero(session: Session) -> str:
    """Gera o Nº sequencial por ano (AAAA-NNNN) de forma atômica dentro da transação."""
    from ....shared.db.atomic_counter import next_counter_value

    year = datetime.now(UTC).year
    seq = next_counter_value(session, "document_counters", year)
    return f"{year}-{seq:04d}"


def _to_record(doc: ClinicalDocument) -> ScreeningRecord:
    return ScreeningRecord(
        id=doc.id,
        numero=doc.numero,
        type=doc.type,  # type: ignore[arg-type]  # coluna String com CHECK constraint no banco garante o conjunto fechado
        status=doc.status,  # type: ignore[arg-type]  # idem
        version=doc.version,
        patient_id=doc.patient_id,
        author_id=doc.author_id,
        co_author_ids=[u.id for u in doc.co_authors],
        content=decrypt_json(doc.content_enc),
        created_at=doc.created_at,
        updated_at=doc.updated_at,
        signatures=[
            SignatureInfo(
                signer_name=s.signer_name,
                signer_role=s.signer_role,
                signer_ref=s.signer_ref,
                provider=s.provider,
                signed_at=s.signed_at,
            )
            for s in doc.signatures
        ],
    )


class SqlAlchemyScreeningRepository(ScreeningRepository):
    def __init__(self, session: Session) -> None:
        self._session = session

    def create(self, ctx: AccessContext, data: NewScreening) -> ScreeningRecord:
        def _do(session: Session) -> ScreeningRecord:
            numero = _next_numero(session)
            co_authors = (
                session.scalars(select(User).where(User.id.in_(data.co_author_ids))).all() if data.co_author_ids else []
            )
            doc = ClinicalDocument(
                numero=numero,
                type=data.type,
                patient_id=data.patient_id,
                author_id=data.author_id,
                content_enc=encrypt_json(data.content),
                content_hash=content_digest(data.content),
                co_authors=list(co_authors),
            )
            session.add(doc)
            session.flush()
            session.refresh(doc, attribute_names=["co_authors", "signatures"])
            return _to_record(doc)

        return with_rls_context(self._session, ctx.user_id, ctx.role, _do)

    def patient_has_screening(self, ctx: AccessContext, patient_id: str) -> bool:
        def _do(session: Session) -> bool:
            # Lock por paciente, dono = transação: segura até o commit do
            # request, cobrindo também o INSERT que vem logo depois. Sem
            # ele, dois cliques simultâneos passariam os dois pela checagem.
            def _exists() -> bool:
                found = session.scalar(
                    select(ClinicalDocument.id).where(
                        ClinicalDocument.patient_id == patient_id,
                        ClinicalDocument.type.in_(SCREENING_ONCE_TYPES),
                    )
                )
                return found is not None

            return with_app_lock(session, f"screening-once:{patient_id}", _exists)

        # Contexto ADMIN só para esta leitura de existência (devolve um
        # booleano, nada do documento): sob o contexto do estagiário a RLS
        # filtraria a triagem de outro autor e a checagem passaria em falso.
        return with_rls_context(self._session, ctx.user_id, "ADMIN", _do)

    def list_for_actor(self, ctx: AccessContext) -> list[ScreeningRecord]:
        def _do(session: Session) -> list[ScreeningRecord]:
            rows = session.scalars(
                select(ClinicalDocument)
                .where(ClinicalDocument.type.in_(_SCREENING_TYPES))
                .order_by(ClinicalDocument.created_at.desc())
            ).all()
            return [_to_record(r) for r in rows]

        return with_rls_context(self._session, ctx.user_id, ctx.role, _do)

    def find_by_id(self, ctx: AccessContext, id: str) -> ScreeningRecord | None:
        def _do(session: Session) -> ScreeningRecord | None:
            doc = session.get(ClinicalDocument, id)
            return _to_record(doc) if doc else None

        return with_rls_context(self._session, ctx.user_id, ctx.role, _do)

    def update_draft(
        self, ctx: AccessContext, id: str, content: dict[str, object], expected_version: int
    ) -> ScreeningRecord:
        def _do(session: Session) -> ScreeningRecord:
            # Só edita rascunhos (ou os que voltaram para revisão). Concorrência otimista por version.
            doc = session.get(ClinicalDocument, id)
            if not doc or doc.version != expected_version or doc.status not in ("RASCUNHO", "REVISAO_SOLICITADA"):
                raise ConflictError(
                    "Rascunho desatualizado ou não editável (verifique versão/status).", {"documentId": id}
                )
            doc.content_enc = encrypt_json(content)
            doc.content_hash = content_digest(content)
            doc.version += 1
            session.flush()
            session.refresh(doc, attribute_names=["co_authors", "signatures"])
            return _to_record(doc)

        return with_rls_context(self._session, ctx.user_id, ctx.role, _do)

    def delete(self, ctx: AccessContext, id: str) -> None:
        def _do(session: Session) -> None:
            # A regra (só RASCUNHO próprio, ou ADMIN) já foi checada na
            # application; a BLOCK PREDICATE de DELETE é o backstop final
            # (defense in depth).
            doc = session.get(ClinicalDocument, id)
            if not doc:
                raise NotFoundError("Triagem não encontrada.")
            session.delete(doc)
            session.flush()

        with_rls_context(self._session, ctx.user_id, ctx.role, _do)
