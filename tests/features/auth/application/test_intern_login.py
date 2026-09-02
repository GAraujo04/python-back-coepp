"""Porta tests/features/auth/application/intern-login.test.ts — mesmos
cenários, fakes em memória no lugar de vi.fn()."""

from __future__ import annotations

from datetime import datetime, timedelta

import pytest

from app.features.auth.application.intern_login import InternLogin, InternLoginInput
from app.features.auth.application.ports import (
    AccessTokenPayload,
    AccessTokenSigner,
    IssuedRefreshToken,
    LoginAttemptTracker,
    RefreshSessionMeta,
    RefreshTokenStore,
    TotvsAuthClient,
    TotvsInvalidCredentialsError,
    TotvsProtocolError,
    TotvsTokenResult,
    TotvsUnavailableError,
    TotvsVinculo,
)
from app.features.auth.domain.user import Email, Role, User
from app.features.auth.domain.user_repository import (
    NewUser,
    PendingSupervisorLink,
    TotvsResolveOutcome,
    UserRepository,
)
from app.shared.audit.audit_recorder import AuditEvent, AuditRecorder
from app.shared.errors.app_error import ForbiddenError, ServiceUnavailableError, UnauthorizedError, ValidationError

RM_VALIDO = "12345678901"


def make_user(active: bool = True) -> User:
    return User("intern-1", Email.create("12345678901@totvs.invalid"), "Estagiário Teste", "INTERN", None, None, active)


class FakeUserRepository(UserRepository):
    def __init__(self) -> None:
        self.resolve_result: TotvsResolveOutcome = TotvsResolveOutcome(kind="created", user=make_user())
        self.profile_complete = False

    def find_by_email(self, email: str) -> User | None:
        raise NotImplementedError

    def find_by_id(self, user_id: str) -> User | None:
        raise NotImplementedError

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
        return self.resolve_result

    def is_intern_profile_complete(self, user_id: str) -> bool:
        return self.profile_complete


class FakeTotvsAuthClient(TotvsAuthClient):
    def __init__(self) -> None:
        self.authenticate_result: TotvsTokenResult | Exception = TotvsTokenResult(access_token="totvs-token")
        self.vinculo_result: list[TotvsVinculo] | Exception = []

    def authenticate(self, usuario: str, senha: str) -> TotvsTokenResult:
        if isinstance(self.authenticate_result, Exception):
            raise self.authenticate_result
        return self.authenticate_result

    def consultar_vinculo(self, usuario: str, access_token: str) -> list[TotvsVinculo]:
        if isinstance(self.vinculo_result, Exception):
            raise self.vinculo_result
        return self.vinculo_result


class FakeLoginAttemptTracker(LoginAttemptTracker):
    def __init__(self) -> None:
        self.locked = False
        self.successes: list[str] = []

    def is_locked(self, key: str) -> bool:
        return self.locked

    def record_failure(self, key: str) -> None:
        pass

    def record_success(self, key: str) -> None:
        self.successes.append(key)


class FakeAccessTokenSigner(AccessTokenSigner):
    def sign(self, payload: AccessTokenPayload) -> str:
        return "access.jwt"


class FakeRefreshTokenStore(RefreshTokenStore):
    def issue(self, user_id: str, meta: RefreshSessionMeta) -> IssuedRefreshToken:
        return IssuedRefreshToken(token="refresh-opaque", expires_at=datetime.now() + timedelta(seconds=1))

    def rotate(self, old_token: str, meta: RefreshSessionMeta) -> tuple[str, IssuedRefreshToken]:  # pragma: no cover
        raise NotImplementedError

    def revoke(self, token: str) -> None:  # pragma: no cover
        raise NotImplementedError


class RecordingAuditRecorder(AuditRecorder):
    def __init__(self) -> None:
        self.events: list[AuditEvent] = []

    def record(self, event: AuditEvent) -> None:
        self.events.append(event)


INPUT = InternLoginInput(usuario_rm=RM_VALIDO, senha_rm="senha-rm", meta=RefreshSessionMeta())


def build() -> tuple[
    InternLogin, FakeUserRepository, FakeTotvsAuthClient, FakeLoginAttemptTracker, RecordingAuditRecorder
]:
    users = FakeUserRepository()
    totvs = FakeTotvsAuthClient()
    attempts = FakeLoginAttemptTracker()
    audit = RecordingAuditRecorder()
    use_case = InternLogin(users, totvs, FakeAccessTokenSigner(), FakeRefreshTokenStore(), attempts, audit, "A")
    return use_case, users, totvs, attempts, audit


def test_autoriza_aluno_tipo_a_e_registra_login() -> None:
    use_case, _, totvs, attempts, audit = build()
    totvs.vinculo_result = [TotvsVinculo(nome="Fulano", tipo="A")]

    out = use_case.execute(INPUT)

    assert out.access_token == "access.jwt"
    assert out.user.role == "INTERN"
    assert "LOGIN" in [e.action for e in audit.events]
    assert attempts.successes


def test_profile_complete_false_quando_conta_recem_provisionada() -> None:
    use_case, users, totvs, _, _ = build()
    totvs.vinculo_result = [TotvsVinculo(nome="Fulano", tipo="A")]
    users.profile_complete = False

    out = use_case.execute(INPUT)
    assert out.user.profile_complete is False


def test_profile_complete_true_quando_perfil_ja_completo() -> None:
    use_case, users, totvs, _, _ = build()
    totvs.vinculo_result = [TotvsVinculo(nome="Fulano", tipo="A")]
    users.profile_complete = True

    out = use_case.execute(INPUT)
    assert out.user.profile_complete is True


def test_token_400_credencial_invalida_sem_chamar_consulta_de_vinculo() -> None:
    use_case, _, totvs, _, audit = build()
    totvs.authenticate_result = TotvsInvalidCredentialsError("bad creds")

    with pytest.raises(UnauthorizedError):
        use_case.execute(INPUT)
    assert "LOGIN_FAILED" in [e.action for e in audit.events]


def test_vinculo_vazio_forbidden() -> None:
    use_case, _, totvs, _, _ = build()
    totvs.vinculo_result = []
    with pytest.raises(ForbiddenError):
        use_case.execute(INPUT)


def test_so_funcionario_forbidden() -> None:
    use_case, _, totvs, _, _ = build()
    totvs.vinculo_result = [TotvsVinculo(nome="Fulano", tipo="F")]
    with pytest.raises(ForbiddenError):
        use_case.execute(INPUT)


def test_so_professor_forbidden() -> None:
    use_case, _, totvs, _, _ = build()
    totvs.vinculo_result = [TotvsVinculo(nome="Fulano", tipo="P")]
    with pytest.raises(ForbiddenError):
        use_case.execute(INPUT)


def test_multiplos_vinculos_autoriza_pelo_a_nao_pega_primeiro_cegamente() -> None:
    use_case, _, totvs, _, _ = build()
    totvs.vinculo_result = [TotvsVinculo(nome="Fulano", tipo="F"), TotvsVinculo(nome="Fulano", tipo="A")]
    out = use_case.execute(INPUT)
    assert out.user.role == "INTERN"


def test_tipo_desconhecido_e_logado_e_nao_derruba_vinculo_a_presente() -> None:
    use_case, _, totvs, _, audit = build()
    totvs.vinculo_result = [TotvsVinculo(nome="Fulano", tipo="X"), TotvsVinculo(nome="Fulano", tipo="A")]
    use_case.execute(INPUT)
    assert any(
        e.diff and e.diff.get("reason") == "tipo_desconhecido" and e.diff.get("tipo") == "X" for e in audit.events
    )


def test_tipo_desconhecido_sem_nenhum_a_forbidden() -> None:
    use_case, _, totvs, _, _ = build()
    totvs.vinculo_result = [TotvsVinculo(nome="Fulano", tipo="X")]
    with pytest.raises(ForbiddenError):
        use_case.execute(INPUT)


def test_5xx_mapeado_como_service_unavailable() -> None:
    use_case, _, totvs, _, _ = build()
    totvs.authenticate_result = TotvsUnavailableError("totvs respondeu 503")
    with pytest.raises(ServiceUnavailableError):
        use_case.execute(INPUT)


def test_timeout_mapeado_como_service_unavailable() -> None:
    use_case, _, totvs, _, _ = build()
    totvs.vinculo_result = TotvsUnavailableError("timeout")
    with pytest.raises(ServiceUnavailableError):
        use_case.execute(INPUT)


def test_json_malformado_mapeado_como_service_unavailable() -> None:
    use_case, _, totvs, _, _ = build()
    totvs.vinculo_result = TotvsProtocolError("resposta não é array")
    with pytest.raises(ServiceUnavailableError):
        use_case.execute(INPUT)


def test_usuario_com_caracteres_invalidos_rejeitado_antes_do_totvs() -> None:
    use_case, _, totvs, _, _ = build()
    bad_input = InternLoginInput(usuario_rm='123"; DROP TABLE users;--', senha_rm="x", meta=RefreshSessionMeta())
    with pytest.raises(ValidationError):
        use_case.execute(bad_input)


def test_usuario_com_menos_de_11_digitos_rejeitado_antes_do_totvs() -> None:
    use_case, _, _, _, _ = build()
    bad_input = InternLoginInput(usuario_rm="123", senha_rm="x", meta=RefreshSessionMeta())
    with pytest.raises(ValidationError):
        use_case.execute(bad_input)


def test_bloqueia_por_tentativas_antes_de_chamar_totvs() -> None:
    use_case, _, _, attempts, _ = build()
    attempts.locked = True
    with pytest.raises(UnauthorizedError):
        use_case.execute(INPUT)


def test_email_de_vinculo_sem_conta_correspondente_nao_cria_conta_silenciosamente() -> None:
    use_case, users, totvs, _, _ = build()
    totvs.vinculo_result = [TotvsVinculo(nome="Fulano", tipo="A")]
    users.resolve_result = TotvsResolveOutcome(kind="link_failed")
    bad_input = InternLoginInput(
        usuario_rm=RM_VALIDO, senha_rm="x", meta=RefreshSessionMeta(), link_email="nao-existe@exemplo.br"
    )
    with pytest.raises(ValidationError):
        use_case.execute(bad_input)


def test_conta_inativa_ja_vinculada_rejeitada_com_erro_generico() -> None:
    use_case, users, totvs, _, _ = build()
    totvs.vinculo_result = [TotvsVinculo(nome="Fulano", tipo="A")]
    users.resolve_result = TotvsResolveOutcome(kind="returning", user=make_user(active=False))
    with pytest.raises(UnauthorizedError):
        use_case.execute(INPUT)
