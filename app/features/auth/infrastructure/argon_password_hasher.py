"""Hash/verificação de senha com Argon2id.

Porta features/auth/infrastructure/argon-password-hasher.ts. `argon2-cffi`
usa o mesmo algoritmo (Argon2id) que a lib `argon2` do Node — hashes já
gravados no banco continuam válidos, sem re-hash necessário.
"""

from __future__ import annotations

from argon2 import PasswordHasher as Argon2PasswordHasher
from argon2.exceptions import InvalidHashError, VerificationError

from ..application.ports import PasswordHasher

_argon2 = Argon2PasswordHasher()


class ArgonPasswordHasher(PasswordHasher):
    def hash(self, plaintext: str) -> str:
        return _argon2.hash(plaintext)

    def verify(self, hash_: str, plaintext: str) -> bool:
        try:
            return _argon2.verify(hash_, plaintext)
        except (VerificationError, InvalidHashError):
            # VerificationError cobre senha errada; InvalidHashError cobre
            # hash em formato inesperado/corrompido — mesmo resultado do
            # catch genérico do TS original (sempre False), mas sem
            # silenciar nada fora desse escopo conhecido.
            return False
