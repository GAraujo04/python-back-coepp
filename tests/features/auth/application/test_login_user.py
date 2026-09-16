"""Porta tests/features/auth/application/login-user.test.ts — mesmos
cenários, fakes em memória no lugar de vi.fn() (sem tocar o banco real)."""

from __future__ import annotations

from datetime import datetime, timedelta

import pytest

from app.features.auth.application.login_user import LoginInput, LoginUser
from app.features.auth.application.ports import (
    AccessTokenPayload,
    AccessTokenSigner,
    IssuedRefreshToken,
    LoginAttemptTracker,
    PasswordHasher,
    RefreshSessionMeta,
    RefreshTokenStore,
)
from app.features.auth.domain.user import Email, Role, User
from app.features.auth.domain.user_repository import (
    NewUser,
    PendingSupervisorLink,
    TotvsResolveOutcome,
    UserRepository,
)
from app.shared.audit.audit_recorder import AuditEvent, AuditRecorder
from app.shared.errors.app_error import TooManyRequestsError, UnauthorizedError


def make_user(role: Role = "ADMIN", active: bool = True) -> User:
    return User("u1", Email.create("ana@exemplo.br"), "Ana", role, "stored-hash", None, active)


class FakeUserRepository(UserRepository):
    def __init__(self, found: User | None) -> None:
        self.found = found

    def find_by_email(self, email: str) -> User | None:
        return self.found

    def find_by_id(self, user_id: str) -> User | None:
        return self.found

    def create(self, data: NewUser) -> User:
        raise NotImplementedError

    def list_by_role(self, role: Role) -> list[User]:
        raise NotImplementedError

    def list_pending_supervisor_links(self) -> list[PendingSupervisorLink]:
        raise NotImplementedError

    def link_supervisor(self, intern_id: str, supervisor_id: str) -> bool:
        raise NotImplementedError

    def resolve_intern_from_totvs(
        self, totvs_usuario: str, full_name: str, link_email: str | None
    ) -> TotvsResolveOutcome:
        raise NotImplementedError

    def is_intern_profile_complete(self, user_id: str) -> bool:
        raise NotImplementedError


class FakePasswordHasher(PasswordHasher):
    def __init__(self, verify_result: bool) -> None:
        self.verify_result = verify_result

    def verify(self, hash_: str, plaintext: str) -> bool:
        return self.verify_result

    def hash(self, plaintext: str) -> str:
        return "hashed"


class FakeAccessTokenSigner(AccessTokenSigner):
    def sign(self, payload: AccessTokenPayload) -> str:
        return "access.jwt"


class FakeRefreshTokenStore(RefreshTokenStore):
    def issue(self, user_id: str, meta: RefreshSessionMeta) -> IssuedRefreshToken:
        return IssuedRefreshToken(token="refresh-opaque", expires_at=datetime.now() + timedelta(seconds=1))

    def rotate(self, old_token: str, meta: RefreshSessionMeta) -> tuple[str, IssuedRefreshToken]:  # pragma: no cover
        raise NotImplementedError  # não usado neste caso de uso

    def revoke(self, token: str) -> None:  # pragma: no cover
        raise NotImplementedError


class RecordingAuditRecorder(AuditRecorder):
    def __init__(self) -> None:
        self.events: list[AuditEvent] = []

    def record(self, event: AuditEvent) -> None:
        self.events.append(event)


INPUT = LoginInput(email="ana@exemplo.br", password="segredo123", meta=RefreshSessionMeta())


class FakeLoginAttemptTracker(LoginAttemptTracker):
    def __init__(self) -> None:
        self.locked = False
        self.failures: list[str] = []
        self.successes: list[str] = []

    def is_locked(self, key: str) -> bool:
        return self.locked

    def record_failure(self, key: str) -> None:
        self.failures.append(key)

    def record_success(self, key: str) -> None:
        self.successes.append(key)


def build(
    user: User | None, verify_result: bool, attempts: FakeLoginAttemptTracker | None = None
) -> tuple[LoginUser, RecordingAuditRecorder, FakeRefreshTokenStore]:
    audit = RecordingAuditRecorder()
    refresh_tokens = FakeRefreshTokenStore()
    use_case = LoginUser(
        FakeUserRepository(user),
        FakePasswordHasher(verify_result),
        FakeAccessTokenSigner(),
        refresh_tokens,
        attempts or FakeLoginAttemptTracker(),
        audit,
    )
    return use_case, audit, refresh_tokens


def test_autentica_com_credenciais_validas_e_registra_login() -> None:
    use_case, audit, _ = build(make_user(), verify_result=True)
    out = use_case.execute(INPUT)
    assert out.access_token == "access.jwt"
    assert out.refresh_token == "refresh-opaque"
    assert out.user.email == "ana@exemplo.br"
    assert out.user.role == "ADMIN"
    assert "LOGIN" in [e.action for e in audit.events]


def test_rejeita_estagiario_com_erro_generico() -> None:
    """Login de estagiário migrou pro TOTVS (ver InternLogin) — mesmo com senha certa."""
    use_case, audit, refresh_tokens = build(make_user(role="INTERN"), verify_result=True)
    with pytest.raises(UnauthorizedError, match="E-mail ou senha inválidos."):
        use_case.execute(INPUT)
    assert "LOGIN_FAILED" in [e.action for e in audit.events]


def test_rejeita_senha_incorreta_e_registra_login_failed() -> None:
    use_case, audit, _ = build(make_user(), verify_result=False)
    with pytest.raises(UnauthorizedError):
        use_case.execute(INPUT)
    assert "LOGIN_FAILED" in [e.action for e in audit.events]


def test_nao_vaza_existencia_de_usuario_inexistente() -> None:
    use_case, _, _ = build(None, verify_result=True)
    with pytest.raises(UnauthorizedError, match="E-mail ou senha inválidos."):
        use_case.execute(INPUT)


def test_bloqueia_usuario_inativo() -> None:
    use_case, audit, _ = build(make_user(active=False), verify_result=True)
    with pytest.raises(UnauthorizedError):
        use_case.execute(INPUT)
    assert "LOGIN_FAILED" in [e.action for e in audit.events]


def test_bloqueia_conta_apos_limite_de_tentativas() -> None:
    """O limite por IP do middleware não cobre este caso: distribuindo as
    tentativas por vários IPs, só o bloqueio por CONTA segura a força
    bruta."""
    attempts = FakeLoginAttemptTracker()
    attempts.locked = True
    use_case, audit, _ = build(make_user(), verify_result=True, attempts=attempts)

    with pytest.raises(TooManyRequestsError, match="Muitas tentativas."):
        use_case.execute(INPUT)
    # Bloqueado antes de tocar o repositório/hasher — não gasta um verify
    # de Argon2 (que é caro de propósito) por tentativa recusada.
    assert audit.events == []


def test_falha_de_senha_debita_o_contador_da_conta() -> None:
    attempts = FakeLoginAttemptTracker()
    use_case, _, _ = build(make_user(), verify_result=False, attempts=attempts)

    with pytest.raises(UnauthorizedError):
        use_case.execute(INPUT)
    assert attempts.failures == ["email:ana@exemplo.br"]


def test_login_bem_sucedido_zera_o_contador_da_conta() -> None:
    attempts = FakeLoginAttemptTracker()
    use_case, _, _ = build(make_user(), verify_result=True, attempts=attempts)

    use_case.execute(INPUT)
    assert attempts.successes == ["email:ana@exemplo.br"]
    assert attempts.failures == []
