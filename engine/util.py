"""Small shared utilities."""
from __future__ import annotations

import hashlib


def stable_seed(*parts) -> int:
    """A deterministic 31-bit seed from arbitrary parts.

    Uses blake2b, not the built-in `hash()`, because CPython salts `str.__hash__`
    per process — so `hash()` would give different seeds after every restart and
    across workers, breaking "reproducible per player/run".
    """
    digest = hashlib.blake2b("::".join(str(p) for p in parts).encode("utf-8"), digest_size=8).digest()
    return int.from_bytes(digest, "big") % (2**31)
