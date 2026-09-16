"""Testes do conteúdo clínico cifrado.

O ponto central aqui é a razão de existir da coluna `content_hash`: o
ciphertext MUDA a cada escrita, então nenhuma regra que precise responder
"isto mudou?" pode ser construída sobre ele.
"""

from __future__ import annotations

from app.shared.crypto.json_field import canonical_json, content_digest, decrypt_json, encrypt_json

CONTEUDO = {"queixa": "Ansiedade", "historico": {"familiar": "sem intercorrências"}, "sessoes": 3}


def test_ida_e_volta_preserva_a_estrutura() -> None:
    assert decrypt_json(encrypt_json(CONTEUDO)) == CONTEUDO


def test_acentuacao_sobrevive() -> None:
    """`ensure_ascii=False` na forma canônica — se virasse \\uXXXX, o hash
    deixaria de bater com o que o backend Node calculava pro mesmo texto."""
    conteudo = {"obs": "Avaliação psicológica — não conclusiva"}
    assert decrypt_json(encrypt_json(conteudo)) == conteudo
    assert "ç" in canonical_json(conteudo)


def test_cifrar_duas_vezes_o_mesmo_conteudo_gera_bytes_diferentes() -> None:
    """IV aleatório por operação. É por isso que o trigger WORM não pode
    comparar `content_enc`: ele acusaria alteração a cada reescrita, mesmo
    quando o conteúdo é idêntico."""
    assert encrypt_json(CONTEUDO) != encrypt_json(CONTEUDO)


def test_o_hash_do_conteudo_e_estavel() -> None:
    """A contrapartida do teste acima: o dígito do texto claro não muda —
    é ele que o trigger de imutabilidade compara, e é o mesmo valor que vai
    para a assinatura do documento."""
    assert content_digest(CONTEUDO) == content_digest(CONTEUDO)
    assert content_digest(CONTEUDO) != content_digest({**CONTEUDO, "sessoes": 4})


def test_forma_canonica_sem_espacos() -> None:
    """Convenção do JSON.stringify do JS. Um espaço a mais depois da
    vírgula muda o hash e, com ele, toda assinatura já emitida."""
    assert canonical_json({"a": 1, "b": 2}) == '{"a":1,"b":2}'
