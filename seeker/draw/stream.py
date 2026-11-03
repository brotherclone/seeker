"""A version-proof random stream for draws.

Python only guarantees that ``random.random()`` itself stays the same across
versions; ``shuffle``, ``choice`` and ``randrange`` have changed between
releases. Draws must replay identically forever, so the stream is built
directly on SHA-256 in counter mode, and every selection uses only ``below``.
"""

from __future__ import annotations

import hashlib

UINT64 = 1 << 64


class DrawStream:
    """Deterministic 64-bit integers derived from a seed.

    Output ``k`` is the first 8 bytes (big-endian) of
    ``sha256(f"{VERSION}:{seed}:{k}")``. Changing the algorithm means bumping
    VERSION, so old batches keep replaying under the old one.
    """

    VERSION = "seeker/draw/v1"

    def __init__(self, seed: int) -> None:
        if seed < 0:
            raise ValueError(f"seed must be non-negative, got {seed}")
        self.seed = seed
        self._counter = 0

    def next64(self) -> int:
        """The next 64-bit unsigned integer."""
        message = f"{self.VERSION}:{self.seed}:{self._counter}".encode("ascii")
        self._counter += 1
        return int.from_bytes(hashlib.sha256(message).digest()[:8], "big")

    def below(self, n: int) -> int:
        """A uniform integer in ``range(n)``, without modulo bias."""
        if n < 1:
            raise ValueError(f"below() needs n >= 1, got {n}")
        limit = UINT64 - UINT64 % n
        while True:
            value = self.next64()
            if value < limit:
                return value % n

    def permutation(self, n: int) -> tuple[int, ...]:
        """A uniform permutation of ``range(n)`` (Fisher-Yates, high to low)."""
        order = list(range(n))
        for i in range(n - 1, 0, -1):
            j = self.below(i + 1)
            order[i], order[j] = order[j], order[i]
        return tuple(order)
