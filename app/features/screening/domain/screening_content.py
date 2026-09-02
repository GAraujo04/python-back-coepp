"""Schemas do conteúdo JSON da triagem (content), fiéis aos formulários do
COEPP/FSA. Campos são opcionais: o rascunho salva parcialmente
(auto-save). A obrigatoriedade é exigida apenas na submissão à supervisão
(ver slice documents).

Porta features/screening/domain/screening-content.ts (Zod → Pydantic).
Atributos ficam em camelCase DIRETO (não snake_case+alias como o resto do
projeto): este content é um blob JSON opaco, gravado/lido tal qual pelo
frontend (ver pep/apps/web .../shared/screening/fields.ts) — usar o
gerador de alias automático arriscaria não bater exatamente em casos como
`rendaFamiliarSM` (que um conversor snake→camel padrão produziria como
`rendaFamiliarSm`, com "m" minúsculo).
"""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, ConfigDict
from pydantic import ValidationError as PydanticValidationError

from ....shared.errors.app_error import ValidationError


class _Strict(BaseModel):
    model_config = ConfigDict(extra="forbid")


class Membro(_Strict):
    nome: str | None = None
    vinculo: str | None = None


class AnaliseEncaminhamentos(_Strict):
    entrevistasRealizadas: str | None = None
    analiseObservacoes: str | None = None
    referencias: str | None = None
    entrevistaDevolutiva: str | None = None
    orientacoesEncaminhamentos: str | None = None


class Datas(_Strict):
    inicioTriagem: str | None = None
    entrevistaDevolutiva: str | None = None


class _AdultIdentificacao(_Strict):
    nome: str | None = None
    dataNascimento: str | None = None
    religiao: str | None = None
    rendaFamiliar: str | None = None
    sexo: str | None = None
    telefone: str | None = None
    escolaridade: str | None = None
    ocupacao: str | None = None
    estadoCivil: str | None = None


class _AdultDadosFamiliares(_Strict):
    comQuemReside: str | None = None
    membros: list[Membro] | None = None


class _AdultAnamnese(_Strict):
    vidaInfantil: str | None = None
    vidaAdolescente: str | None = None
    vidaAdulta: str | None = None
    vidaAtualIdoso: str | None = None
    antecedentesFamiliares: str | None = None


class AdultScreening(_Strict):
    """Triagem ADULTO — 5 seções de anamnese."""

    identificacao: _AdultIdentificacao | None = None
    dadosFamiliares: _AdultDadosFamiliares | None = None
    motivoQueixa: str | None = None
    anamnese: _AdultAnamnese | None = None
    analiseEncaminhamentos: AnaliseEncaminhamentos | None = None
    datas: Datas | None = None


class _ChildIdentificacao(_Strict):
    nome: str | None = None
    dataNascimento: str | None = None
    sexo: str | None = None
    telefone: str | None = None
    escolaridade: str | None = None
    escolaSerie: str | None = None
    religiao: str | None = None
    rendaFamiliarSM: str | None = None


class _Genitor(_Strict):
    nome: str | None = None
    idade: str | None = None
    estadoCivil: str | None = None
    escolaridade: str | None = None
    profissao: str | None = None


class _ChildDadosFamiliares(_Strict):
    mae: _Genitor | None = None
    pai: _Genitor | None = None
    entrevistado: str | None = None
    comQuemReside: str | None = None
    membros: list[Membro] | None = None


class _ChildAnamnese(_Strict):
    concepcaoGestacao: str | None = None
    nascimento: str | None = None
    alimentacao: str | None = None
    linguagem: str | None = None
    sono: str | None = None
    desenvolvimentoPsicomotor: str | None = None
    escolaridade: str | None = None
    doencas: str | None = None
    maniasTiques: str | None = None
    sexualidade: str | None = None
    sociabilidadeBrinquedo: str | None = None
    vidaFamiliar: str | None = None


class ChildScreening(_Strict):
    """Triagem CRIANÇA / ADOLESCENTE — 12 seções de anamnese + dados de pai/mãe."""

    identificacao: _ChildIdentificacao | None = None
    dadosFamiliares: _ChildDadosFamiliares | None = None
    motivoQueixa: str | None = None
    anamnese: _ChildAnamnese | None = None
    analiseEncaminhamentos: AnaliseEncaminhamentos | None = None
    datas: Datas | None = None


ScreeningType = Literal["SCREENING_ADULT", "SCREENING_CHILD"]


def validate_screening_content(type_: ScreeningType, content: dict[str, object] | None) -> dict[str, object]:
    """Valida o content conforme o tipo de triagem; lança ValidationError com detalhes."""
    model = AdultScreening if type_ == "SCREENING_ADULT" else ChildScreening
    try:
        parsed = model.model_validate(content or {})
    except PydanticValidationError as exc:
        issues = [{"path": ".".join(str(p) for p in e["loc"]), "message": e["msg"]} for e in exc.errors()]
        raise ValidationError("Conteúdo da triagem inválido.", {"issues": issues}) from exc
    return parsed.model_dump(exclude_none=True)
