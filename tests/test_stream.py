"""The draw's SHA-256 counter stream: pinned outputs, range, permutations."""

import hashlib
from collections import Counter

import pytest

from seeker.draw.stream import DrawStream


def test_first_outputs_are_pinned() -> None:
    # Pinned forever: changing these breaks every recorded batch.
    stream = DrawStream(7)
    assert [stream.next64() for _ in range(3)] == [
        2510386064442259347,
        14737952818233656434,
        6904206392969484580,
    ]


def test_outputs_follow_the_documented_construction() -> None:
    stream = DrawStream(12345)
    for k in range(5):
        digest = hashlib.sha256(f"seeker/draw/v1:12345:{k}".encode()).digest()
        assert stream.next64() == int.from_bytes(digest[:8], "big")


def test_below_stays_in_range_and_covers_it() -> None:
    stream = DrawStream(1)
    counts = Counter(stream.below(7) for _ in range(7000))
    assert set(counts) == set(range(7))
    assert min(counts.values()) > 800


def test_below_rejects_empty_range() -> None:
    with pytest.raises(ValueError):
        DrawStream(1).below(0)


def test_negative_seed_rejected() -> None:
    with pytest.raises(ValueError):
        DrawStream(-1)


@pytest.mark.parametrize("n", [0, 1, 2, 6, 33])
def test_permutation_is_a_reproducible_permutation(n: int) -> None:
    first = DrawStream(99).permutation(n)
    assert sorted(first) == list(range(n))
    assert DrawStream(99).permutation(n) == first


def test_permutation_is_pinned() -> None:
    assert DrawStream(7).permutation(6) == (1, 5, 2, 0, 4, 3)
