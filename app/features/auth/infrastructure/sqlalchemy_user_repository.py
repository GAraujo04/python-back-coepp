"""Adapter SQLAlchemy do UserRepository. Mapeia a linha do banco para a
entidade de domínio.

Porta features/auth/infrastructure/prisma-user-repository.ts.
"""

from __future__ import annotations

from typing import Any, cast

from sqlalchemy import select, text, update
from sqlalchemy.engine import CursorResult
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from ....shared.db.models import User as UserRow
from ..domain.user import Email, Role, User
from ..domain.user_repository import NewUser, PendingSupervisorLink, TotvsResolveOutcome, UserRepository

# Domínio reservado p/ endereços que provavelmente não existem (RFC 2606) —
# usado como e-mail sintético de contas de estagiário auto-provisionadas
# via TOTVS (que não fornece e-mail nenhum).
_TOTVS_PLACEHOLDER_EMAIL_DOMAIN = "totvs.invalid"


def _to_domain(row: UserRow) -> User:
    return User(
        id=row.id,
        email=Email.create(row.email),
        full_name=row.full_name,
        role=row.role,  # type: ignore[arg-type]  # coluna String com CHECK constraint no banco garante o conjunto fechado
        password_hash=row.password_hash,
        crp=row.crp,
        active=row.active,
        ra=row.ra,
        phone=row.phone,
        department=row.department,
    )


class SqlAlchemyUserRepository(UserRepository):
    def __init__(self, session: Session) -> None:
        self._session = session

    def find_by_email(self, email: str) -> User | None:
        row = self._session.scalar(select(UserRow).where(UserRow.email == email.lower()))
        return _to_domain(row) if row else None

    def find_by_id(self, user_id: str) -> User | None:
        row = self._session.get(UserRow, user_id)
        return _to_domain(row) if row else None

    def create(self, data: NewUser) -> User:
        row = UserRow(
            role=data.role,
            full_name=data.full_name,
            email=data.email.lower(),
            password_hash=data.password_hash,
            crp=data.crp,
            ra=data.ra,
            phone=data.phone,
            department=data.department,
        )
        self._session.add(row)
        self._session.flush()  # popula row.id sem precisar commitar ainda
        return _to_domain(row)

    def list_by_role(self, role: Role) -> list[User]:
        # UserRow.active diretamente como filtro (não .is_(True)) — SQL
        # Server não tem BOOLEAN nativo (a coluna é BIT) e `.is_(True)`
        # compila pra `IS 1`, sintaxe que o T-SQL rejeita; a coluna usada
        # como predicado já renderiza o `= 1`/`= 0` correto por dialeto.
        rows = self._session.scalars(
            select(UserRow).where(UserRow.role == role, UserRow.active).order_by(UserRow.full_name.asc())
        )
        return [_to_domain(r) for r in rows]

    def list_pending_supervisor_links(self) -> list[PendingSupervisorLink]:
        rows = self._session.scalars(
            select(UserRow)
            .where(
                UserRow.role == "INTERN",
                UserRow.academic_supervisor_id.is_(None),
                UserRow.pending_supervisor_name.isnot(None),
            )
            .order_by(UserRow.created_at.asc())
        )
        return [
            PendingSupervisorLink(
                id=r.id, full_name=r.full_name, email=r.email, pending_supervisor_name=r.pending_supervisor_name or ""
            )
            for r in rows
        ]

    def link_supervisor(self, intern_id: str, supervisor_id: str) -> bool:
        result = cast(
            "CursorResult[Any]",
            self._session.execute(
                update(UserRow)
                .where(UserRow.id == intern_id, UserRow.role == "INTERN", UserRow.academic_supervisor_id.is_(None))
                .values(academic_supervisor_id=supervisor_id, pending_supervisor_name=None)
            ),
        )
        return bool(result.rowcount > 0)

    def resolve_intern_from_totvs(
        self, totvs_usuario: str, full_name: str, link_email: str | None
    ) -> TotvsResolveOutcome:
        existing = self._session.scalar(select(UserRow).where(UserRow.totvs_usuario == totvs_usuario))
        if existing:
            if existing.full_name != full_name:
                existing.full_name = full_name
                self._session.flush()
            return TotvsResolveOutcome(kind="returning", user=_to_domain(existing))

        if link_email:
            # Só vincula conta INTERN existente que ainda não tenha usuário
            # RM — nunca sobrescreve um vínculo já feito por outra pessoa.
            result = cast(
                "CursorResult[Any]",
                self._session.execute(
                    update(UserRow)
                    .where(
                        UserRow.email == link_email.lower(), UserRow.role == "INTERN", UserRow.totvs_usuario.is_(None)
                    )
                    .values(totvs_usuario=totvs_usuario, full_name=full_name)
                ),
            )
            if result.rowcount == 0:
                return TotvsResolveOutcome(kind="link_failed")
            self._session.flush()
            row = self._session.scalar(select(UserRow).where(UserRow.totvs_usuario == totvs_usuario))
            if not row:
                # Não deveria acontecer (acabamos de gravar) — trata como
                # falha de vínculo em vez de lançar.
                return TotvsResolveOutcome(kind="link_failed")
            return TotvsResolveOutcome(kind="linked", user=_to_domain(row))

        try:
            row = UserRow(
                role="INTERN",
                full_name=full_name,
                email=f"{totvs_usuario}@{_TOTVS_PLACEHOLDER_EMAIL_DOMAIN}",
                totvs_usuario=totvs_usuario,
                password_hash=None,
                enrollment_verified=True,  # TOTVS confirmou o vínculo — matrícula verificada
                active=True,
            )
            self._session.add(row)
            self._session.flush()
            return TotvsResolveOutcome(kind="created", user=_to_domain(row))
        except IntegrityError:
            # Corrida: duas requisições criando a mesma conta ao mesmo tempo
            # — o índice único em totvs_usuario rejeita a 2ª. Trata como "returning".
            self._session.rollback()
            row = self._session.scalar(select(UserRow).where(UserRow.totvs_usuario == totvs_usuario))
            if row:
                return TotvsResolveOutcome(kind="returning", user=_to_domain(row))
            raise

    def is_intern_profile_complete(self, user_id: str) -> bool:
        row = self._session.get(UserRow, user_id)
        if not row:
            return False
        has_supervisor = bool(row.academic_supervisor_id or row.pending_supervisor_name)
        if not (row.disciplina_id and has_supervisor):
            return False
        # availability_windows/term_acceptances ainda não têm classe ORM
        # (pertencem à slice enrollment, não migrada ainda) — SQL cru
        # direto na tabela, mesma checagem que o `take: 1` do Prisma faz
        # (só precisa saber se existe ao menos 1 linha). Vira um
        # `select(AvailabilityWindow)`/`select(TermAcceptance)` normal
        # quando essa slice for migrada.
        has_availability = self._session.execute(
            text("SELECT TOP 1 1 FROM availability_windows WHERE intern_id = :user_id"), {"user_id": user_id}
        ).first()
        has_term = self._session.execute(
            text("SELECT TOP 1 1 FROM term_acceptances WHERE user_id = :user_id"), {"user_id": user_id}
        ).first()
        return has_availability is not None and has_term is not None
