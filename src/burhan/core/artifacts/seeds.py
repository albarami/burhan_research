"""Deterministic seed derivation (architecture §11; NFR-101).

One master seed per run (recorded in the manifest) is expanded into
per-(stage, worker) seeds via HKDF-HMAC-SHA256 (RFC 5869), implemented on the
standard library (``hmac``/``hashlib``) — no third-party dependency.

Domain separation: ``info = stage || 0x00 || worker`` with the worker encoded
fixed-width (4-byte big-endian), so ``("prep", 11)`` and ``("prep1", 1)`` can
never collide by concatenation. Derived seeds are uniform in
``[0, SEED_SPACE - 1]`` = [0, 2^31 - 1], valid for both R ``set.seed`` and
NumPy seeding (consumption lands with the M04 worker harness).
"""

from __future__ import annotations

import hashlib
import hmac

from burhan.core.errors import IntegrityHalt, halt

_SALT = b"burhan:seed:v1"
_HASH_LEN = 32
_MAX_OKM_BLOCKS = 255

MAX_MASTER_SEED = 2**64 - 1
MAX_WORKER = 2**32 - 1
SEED_SPACE = 2**31


def hkdf_sha256(ikm: bytes, salt: bytes, info: bytes, length: int) -> bytes:
    """RFC 5869 HKDF (extract-then-expand) with HMAC-SHA256.

    Args:
        ikm: Input keying material.
        salt: Extract salt (may be empty, per RFC 5869 §2.2).
        info: Context/domain-separation string.
        length: Output length in bytes, 1..255*32.

    Returns:
        ``length`` bytes of output keying material.
    """
    if not 1 <= length <= _MAX_OKM_BLOCKS * _HASH_LEN:
        halt(
            IntegrityHalt(
                "HKDF output length out of RFC 5869 bounds",
                report={"length": length, "max": _MAX_OKM_BLOCKS * _HASH_LEN},
            )
        )
    prk = hmac.new(salt, ikm, hashlib.sha256).digest()
    okm = b""
    block = b""
    for index in range((length + _HASH_LEN - 1) // _HASH_LEN):
        block = hmac.new(prk, block + info + bytes([index + 1]), hashlib.sha256).digest()
        okm += block
    return okm[:length]


def derive(master: int, stage: str, worker: int = 0) -> int:
    """Derive the deterministic seed for ``(stage, worker)`` from ``master``.

    Args:
        master: Run master seed, 0..2^64-1 (run_manifest ``master_seed``).
        stage: Pipeline stage name (non-empty, no NUL bytes).
        worker: Worker index, 0..2^32-1.

    Returns:
        Seed in ``[0, SEED_SPACE - 1]``.
    """
    if not 0 <= master <= MAX_MASTER_SEED:
        halt(
            IntegrityHalt(
                "master seed out of range",
                report={"master": master, "max": MAX_MASTER_SEED},
            )
        )
    if not stage or "\x00" in stage:
        halt(IntegrityHalt("stage name must be non-empty and NUL-free", report={"stage": stage}))
    if not 0 <= worker <= MAX_WORKER:
        halt(
            IntegrityHalt(
                "worker index out of range",
                report={"worker": worker, "max": MAX_WORKER},
            )
        )
    info = stage.encode("utf-8") + b"\x00" + worker.to_bytes(4, "big")
    okm = hkdf_sha256(master.to_bytes(8, "big"), _SALT, info, 4)
    return int.from_bytes(okm, "big") & (SEED_SPACE - 1)
