"""Lê o termo de responsabilidade do estagiário a partir do arquivo
versionado no repositório (Docs-as-Code, item 4.2 da spec original).

Porta features/enrollment/infrastructure/responsibility-term.ts. Diferença
de path: no Fastify o arquivo é resolvido relativo ao CWD do processo
(sempre `apps/api/`, dois níveis abaixo da raiz do monorepo `pep`). Este é
um repositório PRÓPRIO (`python-back-coepp`), sem o monorepo `pep` como
ancestral — o conteúdo do termo foi copiado verbatim para
`docs/legal/termo-responsabilidade-estagiario.md` deste repo (confirmado
idêntico via diff) e o path é resolvido relativo à raiz DESTE repo.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import Path

_TERM_PATH = Path(__file__).resolve().parents[4] / "docs" / "legal" / "termo-responsabilidade-estagiario.md"

# Sem `^` — igual ao original (`/---\n([\s\S]*?)\n---\n([\s\S]*)$/`, sem
# âncora de início): o arquivo real tem um comentário HTML (aviso pra quem
# mantém) ANTES do bloco `---`, então o front-matter começa no meio do
# arquivo, não na primeira linha. Usar `search` (não `match`), senão a
# âncora implícita do `match` faz isso falhar.
_FRONT_MATTER_RE = re.compile(r"---\n(.*?)\n---\n(.*)$", re.DOTALL)
_VERSION_RE = re.compile(r'version:\s*"?([^"\n]+)"?')


@dataclass
class ResponsibilityTerm:
    version: str
    content: str


def read_responsibility_term() -> ResponsibilityTerm:
    """Sem cache: o arquivo só muda por deploy (novo commit), então reler
    a cada chamada é barato e evita servir uma versão velha após um
    deploy sem reiniciar o processo."""
    raw = _TERM_PATH.read_text(encoding="utf-8")
    match = _FRONT_MATTER_RE.search(raw)
    if not match:
        raise RuntimeError(f"Termo de responsabilidade sem front-matter válido: {_TERM_PATH}")
    front_matter, content = match.group(1), match.group(2)
    version_match = _VERSION_RE.search(front_matter)
    if not version_match:
        raise RuntimeError(f'Termo de responsabilidade sem "version" no front-matter: {_TERM_PATH}')
    return ResponsibilityTerm(version=version_match.group(1).strip(), content=content.strip())
