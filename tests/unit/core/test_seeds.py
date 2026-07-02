"""Seed derivation tests (AT-M01-3; NFR-101; architecture §11).

HKDF-HMAC-SHA256 correctness is anchored to the RFC 5869 Appendix A
test vectors (source: https://www.rfc-editor.org/rfc/rfc5869, retrieved
2026-07-02; hex reproduced verbatim).
"""

from __future__ import annotations

import pytest

from burhan.core.artifacts.seeds import (
    MAX_MASTER_SEED,
    MAX_WORKER,
    SEED_SPACE,
    derive,
    hkdf_sha256,
)
from burhan.core.errors import IntegrityHalt

# The 13 pipeline stages (provenance/manifest stage enum, schemas/00_README.md)
# x 16 workers (BURHAN_MAX_WORKERS reference budget, 04_ENVIRONMENT_AND_STACK §2).
STAGES = [
    "ingest",
    "contract",
    "gate1",
    "power",
    "prep",
    "assumptions",
    "measurement",
    "structural",
    "effects",
    "robustness",
    "narrate",
    "gate2",
    "package",
]

RFC5869_VECTORS = [
    # (ikm, salt, info, length, okm) — Appendix A.1 / A.2 / A.3 (SHA-256).
    (
        bytes.fromhex("0b" * 22),
        bytes.fromhex("000102030405060708090a0b0c"),
        bytes.fromhex("f0f1f2f3f4f5f6f7f8f9"),
        42,
        bytes.fromhex(
            "3cb25f25faacd57a90434f64d0362f2a2d2d0a90cf1a5a4c5db02d56ecc4c5bf34007208d5b887185865"
        ),
    ),
    (
        bytes.fromhex(
            "000102030405060708090a0b0c0d0e0f"
            "101112131415161718191a1b1c1d1e1f"
            "202122232425262728292a2b2c2d2e2f"
            "303132333435363738393a3b3c3d3e3f"
            "404142434445464748494a4b4c4d4e4f"
        ),
        bytes.fromhex(
            "606162636465666768696a6b6c6d6e6f"
            "707172737475767778797a7b7c7d7e7f"
            "808182838485868788898a8b8c8d8e8f"
            "909192939495969798999a9b9c9d9e9f"
            "a0a1a2a3a4a5a6a7a8a9aaabacadaeaf"
        ),
        bytes.fromhex(
            "b0b1b2b3b4b5b6b7b8b9babbbcbdbebf"
            "c0c1c2c3c4c5c6c7c8c9cacbcccdcecf"
            "d0d1d2d3d4d5d6d7d8d9dadbdcdddedf"
            "e0e1e2e3e4e5e6e7e8e9eaebecedeeef"
            "f0f1f2f3f4f5f6f7f8f9fafbfcfdfeff"
        ),
        82,
        bytes.fromhex(
            "b11e398dc80327a1c8e7f78c596a4934"
            "4f012eda2d4efad8a050cc4c19afa97c"
            "59045a99cac7827271cb41c65e590e09"
            "da3275600c2f09b8367793a9aca3db71"
            "cc30c58179ec3e87c14c01d5c1f3434f"
            "1d87"
        ),
    ),
    (
        bytes.fromhex("0b" * 22),
        b"",
        b"",
        42,
        bytes.fromhex(
            "8da4e775a563c18f715f802a063c5a31b8a11f5c5ee1879ec3454e5f3c738d2d9d201395faa4b61a96c8"
        ),
    ),
]


@pytest.mark.parametrize(("ikm", "salt", "info", "length", "okm"), RFC5869_VECTORS)
def test_hkdf_sha256_matches_rfc5869_vectors(
    ikm: bytes, salt: bytes, info: bytes, length: int, okm: bytes
) -> None:
    assert hkdf_sha256(ikm, salt, info, length) == okm


def test_derive_is_deterministic_across_calls() -> None:  # AT-M01-3
    assert derive(12345, "prep", 3) == derive(12345, "prep", 3)
    assert derive(12345, "prep") == derive(12345, "prep", 0)


def test_derive_values_are_pinned_forever() -> None:  # NFR-101 regression lock
    # Frozen at first implementation: any change to the derivation constants
    # (salt, encodings, output width) silently breaks byte-identical reruns,
    # so these exact values are load-bearing.
    assert derive(424242, "prep", 3) == 781967108
    assert derive(0, "ingest", 0) == 1416785546
    assert derive(2**64 - 1, "package", 2**32 - 1) == 891217379


def test_derive_output_range_fits_r_and_numpy_seeding() -> None:
    for stage in STAGES:
        seed = derive(0, stage, 0)
        assert 0 <= seed < SEED_SPACE


def test_collision_free_across_stage_worker_grid() -> None:  # AT-M01-3
    grid = {derive(2**63 - 42, stage, worker) for stage in STAGES for worker in range(16)}
    assert len(grid) == len(STAGES) * 16
    wide = {derive(7, stage, worker) for stage in STAGES for worker in range(64)}
    assert len(wide) == len(STAGES) * 64


def test_changing_master_seed_changes_all_derived_seeds() -> None:  # AT-M01-3
    pairs = [(stage, worker) for stage in STAGES for worker in range(16)]
    assert all(derive(1001, s, w) != derive(1002, s, w) for s, w in pairs)


def test_domain_separation_is_unambiguous() -> None:
    # Fixed-width worker encoding + separator: ("prep", 11) never collides
    # with ("prep1", 1) by concatenation ambiguity.
    assert derive(5, "prep", 11) != derive(5, "prep1", 1)
    assert derive(5, "prep", 1) != derive(5, "prep", 11)
    assert derive(5, "prep", 1) != derive(5, "power", 1)


def test_invalid_inputs_halt() -> None:
    with pytest.raises(IntegrityHalt):
        derive(-1, "prep", 0)
    with pytest.raises(IntegrityHalt):
        derive(MAX_MASTER_SEED + 1, "prep", 0)
    with pytest.raises(IntegrityHalt):
        derive(1, "", 0)
    with pytest.raises(IntegrityHalt):
        derive(1, "pre\x00p", 0)
    with pytest.raises(IntegrityHalt):
        derive(1, "prep", -1)
    with pytest.raises(IntegrityHalt):
        derive(1, "prep", MAX_WORKER + 1)


def test_hkdf_length_bounds() -> None:
    with pytest.raises(IntegrityHalt):
        hkdf_sha256(b"k", b"s", b"i", 0)
    with pytest.raises(IntegrityHalt):
        hkdf_sha256(b"k", b"s", b"i", 255 * 32 + 1)
    assert len(hkdf_sha256(b"k", b"s", b"i", 255 * 32)) == 255 * 32
