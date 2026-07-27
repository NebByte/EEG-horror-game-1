"""Small shared utilities."""
from __future__ import annotations

import hashlib


def stable_seed(*parts) -> int:
    """A deterministic 31-bit seed from arbitrary parts.

    Uses blake2b, not the built-in `hash()`, because CPython salts `str.__hash__`
    per process — so `hash()` would give different seeds after every restart and
    across workers, breaking "reproducible per player/run".
    """
    # Length-prefix each part so distinct boundaries never collide, e.g.
    # ("a::b","c") must differ from ("a","b::c").
    payload = b"".join(
        len(b := str(p).encode("utf-8")).to_bytes(8, "big") + b for p in parts
    )
    digest = hashlib.blake2b(payload, digest_size=8).digest()
    return int.from_bytes(digest, "big") % (2**31)
