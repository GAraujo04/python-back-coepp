"""Schemas do conteúdo JSON dos documentos clínicos (content), fiéis aos
formulários do COEPP/FSA — as duas triagens e os cinco documentos de
estágio (ficha de evolução, laudo, relatórios). Campos são opcionais: o rascunho salva parcialmente
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

from typing import Literal, get_args

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


# --- Documentos do estágio (além das duas triagens) -----------------------
#
# Os cinco modelos abaixo vêm dos formulários .docx do COEPP (em
# nuxt-front-coepp/docs/). Mesma convenção das triagens: campos todos
# opcionais, porque o rascunho salva parcial; a obrigatoriedade é exigida
# só na submissão à supervisão.
#
# Os campos de identificação do paciente (nome, data de nascimento) são
# gravados como SNAPSHOT no momento da criação, a partir do cadastro — não
# são digitados nem lidos ao vivo do cadastro. Snapshot porque estes são
# documentos legais: depois de APROVADO_LOCKED o conteúdo é imutável
# (trigger WORM sobre content_hash), e um nome lido ao vivo mudaria o laudo
# já assinado se alguém corrigisse o cadastro depois.


class SessaoEvolucao(_Strict):
    """Um atendimento na Ficha de Evolução — o bloco que o .docx repete na folha."""

    dataAtendimento: str | None = None
    sinteseAtendimento: str | None = None
    estagiarioResponsavel: str | None = None
    supervisorResponsavel: str | None = None


class FichaEvolucao(_Strict):
    """FICHA DE EVOLUÇÃO — uma por paciente, acumulando as sessões numa lista.

    O cabeçalho do papel (Prontuário nº / Usuário) não entra no content: o
    número é o `numero` do próprio ClinicalDocument e o nome vem do
    paciente do vínculo.
    """

    sessoes: list[SessaoEvolucao] | None = None


class _IdentificacaoCFP(_Strict):
    """"I. Identificação" da Resolução CFP nº 06/2019 (laudo e relatório psicológico)."""

    nome: str | None = None  # snapshot do cadastro
    dataNascimento: str | None = None  # snapshot do cadastro
    solicitante: str | None = None
    finalidade: str | None = None
    autores: str | None = None


class _EntregaCFP(_Strict):
    """Recibo de entrega ao responsável, no fim do laudo/relatório psicológico."""

    responsavelNome: str | None = None
    responsavelPor: str | None = None
    dataRecebimento: str | None = None


class _DocumentoCFP(_Strict):
    """Estrutura comum ao Laudo e ao Relatório Psicológico.

    Os dois .docx são iguais seção por seção (I. Identificação a
    V. Conclusão, mais referências e recibo) — divergem só no título e na
    observação de rodapé, que são texto fixo da tela, não campo. Ficam como
    TIPOS distintos porque são documentos distintos perante o CFP, mas
    compartilham a definição de conteúdo.
    """

    identificacao: _IdentificacaoCFP | None = None
    descricaoDemanda: str | None = None
    procedimentos: str | None = None
    analise: str | None = None
    conclusao: str | None = None
    localData: str | None = None
    referencias: str | None = None
    entrega: _EntregaCFP | None = None


class LaudoPsicologico(_DocumentoCFP):
    """LAUDO PSICOLÓGICO (Resolução CFP nº 06/2019)."""


class RelatorioPsicologico(_DocumentoCFP):
    """RELATÓRIO PSICOLÓGICO (Resolução CFP nº 06/2019)."""


class _IdentificacaoAcompanhamento(_Strict):
    pacienteInstituicao: str | None = None  # snapshot do cadastro
    dataAtendimento: str | None = None
    objetivoAtendimento: str | None = None
    numeroAtendimento: str | None = None


class RelatorioAcompanhamentoSemanal(_Strict):
    """RELATÓRIO DE ACOMPANHAMENTO SEMANAL DE ESTÁGIO."""

    identificacao: _IdentificacaoAcompanhamento | None = None
    relatoAtendimento: str | None = None
    analise: str | None = None
    referencias: str | None = None


class _RelatorioEstagio(_Strict):
    """Estrutura comum ao relatório parcial e ao final.

    Um .docx só ("RELATÓRIO FINAL (OU PARCIAL)") serve os dois momentos do
    estágio, com as mesmas oito seções. Viraram dois TIPOS por decisão de
    produto — aparecem separados no prontuário — mas a definição de
    conteúdo é uma.
    """

    introducao: str | None = None
    caracterizacaoInstituicao: str | None = None
    referencialTeorico: str | None = None
    procedimentosTecnicas: str | None = None
    relatoriosAcompanhamento: str | None = None
    analise: str | None = None
    consideracoesFinais: str | None = None
    referencias: str | None = None


class RelatorioParcial(_RelatorioEstagio):
    """RELATÓRIO PARCIAL DE ESTÁGIO EM PSICOLOGIA."""


class RelatorioFinal(_RelatorioEstagio):
    """RELATÓRIO FINAL DE ESTÁGIO EM PSICOLOGIA."""


ScreeningType = Literal[
    "SCREENING_ADULT",
    "SCREENING_CHILD",
    "EVOLUTION",
    "PSYCH_ASSESSMENT",
    "WEEKLY_REPORT",
    "PARTIAL_REPORT",
    "FINAL_REPORT",
    "PSYCH_REPORT",
]

# Tabela em vez do `if/else` que havia aqui: com oito tipos, o encadeamento
# de ternários erra calado (um tipo novo cairia no modelo do último `else`
# e teria o content validado pelo schema errado). Com a tabela, tipo sem
# modelo é KeyError na hora.
_CONTENT_MODELS: dict[str, type[_Strict]] = {
    "SCREENING_ADULT": AdultScreening,
    "SCREENING_CHILD": ChildScreening,
    "EVOLUTION": FichaEvolucao,
    "PSYCH_ASSESSMENT": LaudoPsicologico,
    "WEEKLY_REPORT": RelatorioAcompanhamentoSemanal,
    "PARTIAL_REPORT": RelatorioParcial,
    "FINAL_REPORT": RelatorioFinal,
    "PSYCH_REPORT": RelatorioPsicologico,
}

# O Literal acima e a tabela precisam andar juntos — se divergirem, um tipo
# aceito na borda HTTP explodiria só ao validar o content, com KeyError.
assert set(_CONTENT_MODELS) == set(get_args(ScreeningType)), (
    "ScreeningType e _CONTENT_MODELS divergiram: "
    f"{set(get_args(ScreeningType)) ^ set(_CONTENT_MODELS)}"
)


def validate_screening_content(type_: ScreeningType, content: dict[str, object] | None) -> dict[str, object]:
    """Valida o content conforme o tipo de documento; lança ValidationError com detalhes."""
    model = _CONTENT_MODELS[type_]
    try:
        parsed = model.model_validate(content or {})
    except PydanticValidationError as exc:
        issues = [{"path": ".".join(str(p) for p in e["loc"]), "message": e["msg"]} for e in exc.errors()]
        raise ValidationError("Conteúdo do documento inválido.", {"issues": issues}) from exc
    return parsed.model_dump(exclude_none=True)
