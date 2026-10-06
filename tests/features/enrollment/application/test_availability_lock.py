"""Trava de disponibilidade: travada por padrão, liberada pelo supervisor
responsável, gasta no primeiro salvamento."""

from __future__ import annotations

from datetime import datetime, timedelta

import pytest

from app.features.enrollment.application.availability_lock import (
    Actor,
    AvailabilityLockRepository,
    AvailabilityLockState,
    GrantAvailabilityUnlock,
    PendingAvailabilityRequest,
    RequestAvailabilityChange,
    RevokeAvailabilityUnlock,
)
from app.features.enrollment.application.update_availability_windows import (
    UpdateAvailabilityWindows,
    UpdateAvailabilityWindowsInput,
)
from app.shared.audit.audit_recorder import AuditEvent, AuditRecorder
from app.shared.errors.app_error import ForbiddenError, NotFoundError, ValidationError
from app.shared.scheduling.availability_window import AvailabilityWindowInput

INTERN = "intern-1"
SUPERVISOR = Actor("sup-1", "SUPERVISOR")
OTHER_SUPERVISOR = Actor("sup-2", "SUPERVISOR")
ADMIN = Actor("admin-1", "ADMIN")


class FakeLockRepo(AvailabilityLockRepository):
    def __init__(self) -> None:
        self.state = AvailabilityLockState(unlocked_until=None, requested_at=None, request_reason=None)

    def get_state(self, intern_id: str) -> AvailabilityLockState | None:
        return self.state if intern_id == INTERN else None

    def save_request(self, intern_id: str, reason: str, at: datetime) -> None:
        self.state.requested_at, self.state.request_reason = at, reason

    def unlock(self, intern_id: str, until: datetime) -> None:
        self.state = AvailabilityLockState(unlocked_until=until, requested_at=None, request_reason=None)

    def relock(self, intern_id: str) -> None:
        self.state = AvailabilityLockState(unlocked_until=None, requested_at=None, request_reason=None)

    def consume_unlock(self, intern_id: str, now: datetime) -> bool:
        if not self.state.editable(now):
            return False
        self.state.unlocked_until = None
        return True

    def is_responsible(self, supervisor_id: str, intern_id: str) -> bool:
        return supervisor_id == SUPERVISOR.user_id

    def list_open(self, supervisor_id: str | None, now: datetime) -> list[PendingAvailabilityRequest]:
        return []


class FakeEnrollmentRepo:
    def __init__(self) -> None:
        self.saved: list[list[AvailabilityWindowInput]] = []

    def update_availability_windows(self, user_id: str, windows: list[AvailabilityWindowInput]) -> None:
        self.saved.append(windows)


class FakeAudit(AuditRecorder):
    def record(self, event: AuditEvent) -> None:
        pass


WINDOWS = [AvailabilityWindowInput(weekday=1, start_time="14:00", end_time="18:00")]


def _save(lock: FakeLockRepo, enrollment: FakeEnrollmentRepo) -> None:
    UpdateAvailabilityWindows(enrollment, lock, FakeAudit()).execute(  # type: ignore[arg-type]
        UpdateAvailabilityWindowsInput(user_id=INTERN, windows=WINDOWS)
    )


def test_travada_por_padrao() -> None:
    lock, enrollment = FakeLockRepo(), FakeEnrollmentRepo()
    with pytest.raises(ForbiddenError):
        _save(lock, enrollment)
    assert enrollment.saved == []


def test_liberacao_vale_para_um_salvamento() -> None:
    lock, enrollment = FakeLockRepo(), FakeEnrollmentRepo()
    GrantAvailabilityUnlock(lock, FakeAudit()).execute(SUPERVISOR, INTERN, hours=48)
    _save(lock, enrollment)
    assert len(enrollment.saved) == 1
    with pytest.raises(ForbiddenError):
        _save(lock, enrollment)


def test_liberacao_vencida_nao_vale() -> None:
    lock, enrollment = FakeLockRepo(), FakeEnrollmentRepo()
    lock.unlock(INTERN, datetime.now() - timedelta(hours=1))
    with pytest.raises(ForbiddenError):
        _save(lock, enrollment)


def test_formulario_invalido_nao_gasta_a_liberacao() -> None:
    lock, enrollment = FakeLockRepo(), FakeEnrollmentRepo()
    GrantAvailabilityUnlock(lock, FakeAudit()).execute(SUPERVISOR, INTERN)
    bad = [AvailabilityWindowInput(weekday=1, start_time="18:00", end_time="14:00")]
    with pytest.raises(ValidationError):
        UpdateAvailabilityWindows(enrollment, lock, FakeAudit()).execute(  # type: ignore[arg-type]
            UpdateAvailabilityWindowsInput(user_id=INTERN, windows=bad)
        )
    _save(lock, enrollment)  # a liberação continua lá
    assert len(enrollment.saved) == 1


def test_so_o_supervisor_responsavel_ou_admin_liberam() -> None:
    lock = FakeLockRepo()
    with pytest.raises(ForbiddenError):
        GrantAvailabilityUnlock(lock, FakeAudit()).execute(OTHER_SUPERVISOR, INTERN)
    GrantAvailabilityUnlock(lock, FakeAudit()).execute(ADMIN, INTERN)
    assert lock.state.unlocked_until is not None


def test_estagiario_inexistente() -> None:
    with pytest.raises(NotFoundError):
        GrantAvailabilityUnlock(FakeLockRepo(), FakeAudit()).execute(ADMIN, "nao-existe")


def test_prazo_fora_dos_limites() -> None:
    with pytest.raises(ValidationError):
        GrantAvailabilityUnlock(FakeLockRepo(), FakeAudit()).execute(SUPERVISOR, INTERN, hours=0)


def test_pedido_exige_motivo_e_revogacao_limpa_tudo() -> None:
    lock = FakeLockRepo()
    with pytest.raises(ValidationError):
        RequestAvailabilityChange(lock, FakeAudit()).execute(INTERN, "   ")
    RequestAvailabilityChange(lock, FakeAudit()).execute(INTERN, "Mudei de turno no trabalho")
    assert lock.state.request_reason == "Mudei de turno no trabalho"
    RevokeAvailabilityUnlock(lock, FakeAudit()).execute(SUPERVISOR, INTERN)
    assert lock.state == AvailabilityLockState(None, None, None)
