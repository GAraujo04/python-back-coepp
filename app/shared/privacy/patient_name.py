"""Quem recebe o NOME do paciente nas respostas da API (LGPD — minimização).

- ADMIN: recebe (recepção/administrativo precisa contatar o paciente).
- INTERN: recebe, mas só dos pacientes vinculados a ele (o escopo já vem
  da consulta) — é quem atende, precisa saber com quem está falando.
- SUPERVISOR: NÃO recebe. Identifica o paciente pelo código; o nome ele
  lê dentro do próprio documento clínico (a ficha de triagem), que é
  conteúdo do prontuário, não navegação.

Lista de quem RECEBE, não de quem não recebe: um papel novo cai no lado
seguro. Aplicado no servidor, e não só na tela, para o nome não trafegar
para quem não deve vê-lo.
"""

from __future__ import annotations

_RECEIVES_PATIENT_NAME = frozenset({"ADMIN", "INTERN"})


def patient_name_for(role: str, name: str) -> str | None:
    return name if role in _RECEIVES_PATIENT_NAME else None
