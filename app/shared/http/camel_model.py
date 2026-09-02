"""Base Pydantic com JSON em camelCase (contrato) mas atributos Python em
snake_case (idiomático).

Isto é o ponto mais importante de paridade de contrato de toda a
migração: o Fastify original serializa `accessToken`, `fullName`,
`usuarioRm`, `linkEmail` etc. — os dois frontends (React e Nuxt) esperam
exatamente esse formato. Sem isto, o FastAPI serializaria
`access_token`/`full_name` (snake_case, convenção Python) e quebraria os
dois frontends silenciosamente.
"""

from __future__ import annotations

from pydantic import BaseModel, ConfigDict
from pydantic.alias_generators import to_camel


class CamelModel(BaseModel):
    model_config = ConfigDict(alias_generator=to_camel, populate_by_name=True)
