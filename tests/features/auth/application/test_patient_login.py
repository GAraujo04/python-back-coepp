"""Testes do login do paciente (CPF + data de nascimento).

Este é o login mais exposto do sistema — os dois fatores são dados
pessoais, não segredos, e a data de nascimento tem espaço de busca
pequeno. Os testes abaixo cobrem justamente o que impede a varredura.
"""

from __future__ import annotations

from datetime import datetime, timedelta

import pytest

from app.features.auth.application.patient_login import PatientLogin, PatientLoginInput
from app.features.auth.application.ports import (
    AccessTokenPayload,
    AccessTokenSigner,
    IssuedRefreshToken,
    LoginAttemptTracker,
    PatientAccount,
    PatientAuthLookup,
    RefreshSessionMeta,
    RefreshTokenStore,
)
from app.shared.audit.audit_recorder import AuditEvent, AuditRecorder
from app.shared.errors.app_error import TooManyRequestsError, UnauthorizedError

CPF = "390.533.447-05"
NASCIMENTO = "1990-05-14"


class FakePatientAuthLookup(PatientAuthLookup):
    def __init__(self, account: PatientAccount | None) -> None:
        self.account = account
        self.lookups = 0

    def find_by_cpf(self, cpf: str) -> PatientAccount | None:
        self.lookups += 1
        return self.account


class FakeAccessTokenSigner(AccessTokenSigner):
    def sign(self, payload: AccessTokenPayload) -> str:
        return "access.jwt"


class FakeRefreshTokenStore(RefreshTokenStore):
    def issue(self, user_id: str, meta: RefreshSessionMeta) -> IssuedRefreshToken:
        return IssuedRefreshToken(token="refresh-opaque", expires_at=datetime.now() + timedelta(days=7))

    def rotate(self, old_token: str, meta: RefreshSessionMeta) -> tuple[str, IssuedRefreshToken]:  # pragma: no cover
        raise NotImplementedError

    def revoke(self, token: str) -> None:  # pragma: no cover
        raise NotImplementedError


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


class RecordingAuditRecorder(AuditRecorder):
    def __init__(self) -> None:
        self.events: list[AuditEvent] = []

    def record(self, event: AuditEvent) -> None:
        self.events.append(event)


def make_account() -> PatientAccount:
    return PatientAccount(user_id="u1", email="paciente@exemplo.br", full_name="Maria", birth_date=NASCIMENTO)


INPUT = PatientLoginInput(cpf=CPF, birth_date=NASCIMENTO, meta=RefreshSessionMeta())


def build(
    account: PatientAccount | None, attempts: FakeLoginAttemptTracker | None = None
) -> tuple[PatientLogin, FakePatientAuthLookup, FakeLoginAttemptTracker, RecordingAuditRecorder]:
    lookup = FakePatientAuthLookup(account)
    tracker = attempts or FakeLoginAttemptTracker()
    audit = RecordingAuditRecorder()
    use_case = PatientLogin(lookup, FakeAccessTokenSigner(), FakeRefreshTokenStore(), tracker, audit)
    return use_case, lookup, tracker, audit


def test_autentica_com_cpf_e_nascimento_corretos() -> None:
    use_case, _, attempts, audit = build(make_account())

    out = use_case.execute(INPUT)

    assert out.access_token == "access.jwt"
    assert out.user.role == "PATIENT"
    assert "LOGIN" in [e.action for e in audit.events]
    assert len(attempts.successes) == 1


def test_data_de_nascimento_errada_debita_o_contador() -> None:
    use_case, _, attempts, audit = build(make_account())
    errado = PatientLoginInput(cpf=CPF, birth_date="1991-01-01", meta=RefreshSessionMeta())

    with pytest.raises(UnauthorizedError, match="CPF ou data de nascimento inválidos."):
        use_case.execute(errado)

    assert len(attempts.failures) == 1
    assert "LOGIN_FAILED" in [e.action for e in audit.events]


def test_cpf_inexistente_devolve_a_mesma_mensagem() -> None:
    """Mensagem idêntica à da data errada — do contrário a resposta viraria
    um oráculo de 'este CPF é paciente da clínica', que é informação de
    saúde."""
    use_case, _, _, _ = build(None)

    with pytest.raises(UnauthorizedError, match="CPF ou data de nascimento inválidos."):
        use_case.execute(INPUT)


def test_bloqueia_varredura_de_datas_no_mesmo_cpf() -> None:
    attempts = FakeLoginAttemptTracker()
    attempts.locked = True
    use_case, lookup, _, audit = build(make_account(), attempts=attempts)

    with pytest.raises(TooManyRequestsError, match="Muitas tentativas."):
        use_case.execute(INPUT)

    # Recusado antes de consultar o banco: uma varredura bloqueada não deve
    # nem custar uma query por tentativa.
    assert lookup.lookups == 0
    assert audit.events == []


def test_chave_de_bloqueio_nao_guarda_o_cpf_em_claro() -> None:
    """O contador vive 15 min em memória; não há razão pra manter uma lista
    de CPFs em claro no processo — inclusive de quem nem é paciente daqui."""
    attempts = FakeLoginAttemptTracker()
    use_case, _, _, _ = build(None, attempts=attempts)

    with pytest.raises(UnauthorizedError):
        use_case.execute(INPUT)

    (key,) = attempts.failures
    assert key.startswith("cpf:")
    assert "39053344705" not in key
    assert CPF not in key


def test_cpf_com_e_sem_mascara_caem_na_mesma_chave() -> None:
    """Senão bastaria alternar entre '390.533.447-05' e '39053344705' pra
    ganhar um balde novo a cada tentativa."""
    attempts = FakeLoginAttemptTracker()
    use_case, _, _, _ = build(None, attempts=attempts)

    with pytest.raises(UnauthorizedError):
        use_case.execute(INPUT)
    with pytest.raises(UnauthorizedError):
        use_case.execute(PatientLoginInput(cpf="39053344705", birth_date=NASCIMENTO, meta=RefreshSessionMeta()))

    assert attempts.failures[0] == attempts.failures[1]
