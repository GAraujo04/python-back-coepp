"""Quem recebe o nome do paciente nas respostas da API."""

from __future__ import annotations

from app.shared.privacy.patient_name import patient_name_for


def test_admin_e_estagiario_recebem_o_nome() -> None:
    assert patient_name_for("ADMIN", "Nilda Araujo") == "Nilda Araujo"
    assert patient_name_for("INTERN", "Nilda Araujo") == "Nilda Araujo"


def test_supervisor_nao_recebe() -> None:
    assert patient_name_for("SUPERVISOR", "Nilda Araujo") is None


def test_papel_desconhecido_cai_no_lado_seguro() -> None:
    assert patient_name_for("PATIENT", "Nilda Araujo") is None
    assert patient_name_for("", "Nilda Araujo") is None
