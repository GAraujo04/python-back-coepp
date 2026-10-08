"""Exporta o contrato OpenAPI gerado pelo FastAPI para docs/api/openapi.json.

    .venv/bin/python -m scripts.export_openapi           # regrava o arquivo
    .venv/bin/python -m scripts.export_openapi --check   # falha se estiver desatualizado (CI)

O contrato nasce das rotas e dos modelos Pydantic — este arquivo é só a
fotografia versionada dele, que o front copia (npm run api:sync). O
--check na CI garante que uma mudança de rota venha junto com a do
contrato, em vez de o arquivo apodrecer como a cópia antiga do repo pep.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

from app.main import app

TARGET = Path(__file__).resolve().parent.parent / "docs" / "api" / "openapi.json"


def render() -> str:
    return json.dumps(app.openapi(), ensure_ascii=False, indent=2, sort_keys=True) + "\n"


def main() -> int:
    content = render()
    if "--check" in sys.argv:
        if not TARGET.exists() or TARGET.read_text(encoding="utf-8") != content:
            print(f"{TARGET} desatualizado — rode: python -m scripts.export_openapi", file=sys.stderr)
            return 1
        print("contrato em dia")
        return 0
    TARGET.parent.mkdir(parents=True, exist_ok=True)
    TARGET.write_text(content, encoding="utf-8")
    print(f"gravado {TARGET}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
