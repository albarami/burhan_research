"""Canonical JSON serializer tests (AT-M01-2; NFR-101; standards §1).

Order- and float-stable: permuted dict input yields identical bytes; repeated
runs yield identical hashes. Input domain is closed — anything outside
dict/list/str/int/float/bool/None raises IntegrityHalt.
"""

from __future__ import annotations

import datetime as dt
from pathlib import Path

import pytest

from burhan.core.artifacts.canonical import (
    dumps,
    dumps_bytes,
    sha256_canonical,
    sha256_file,
)
from burhan.core.errors import IntegrityHalt

# Pinned regression constants (computed once at implementation, then frozen).
_PINNED_JSON = '{"a":{"x":null,"y":0.5},"z":[1,2,{"k":"v"}]}'
_PINNED_SHA = "519d113997237911265950455b05c395fbdbc7330518cdff0d06ca9dfc5c2ed1"


def test_permuted_dict_insertion_orders_yield_identical_bytes() -> None:  # AT-M01-2
    a: dict[str, object] = {}
    a["z"] = [1, 2, {"k": "v"}]
    a["a"] = {"y": 0.5, "x": None}
    b: dict[str, object] = {}
    b["a"] = {"x": None, "y": 0.5}
    b["z"] = [1, 2, {"k": "v"}]
    assert dumps(a) == dumps(b) == _PINNED_JSON
    assert dumps_bytes(a) == dumps_bytes(b) == _PINNED_JSON.encode("utf-8")


def test_repeated_runs_yield_identical_pinned_hash() -> None:  # AT-M01-2
    obj = {"z": [1, 2, {"k": "v"}], "a": {"y": 0.5, "x": None}}
    hashes = {sha256_canonical(obj) for _ in range(5)}
    assert hashes == {_PINNED_SHA}


def test_float_formatting_is_stable() -> None:  # AT-M01-2
    assert dumps({"v": 0.1}) == '{"v":0.1}'
    assert dumps({"v": 1.0}) == '{"v":1.0}'
    assert dumps({"v": 1}) == '{"v":1}'  # int stays int, distinct from 1.0
    assert dumps({"v": 0.30000000000000004}) == '{"v":0.30000000000000004}'
    assert dumps({"v": 1e308}) == '{"v":1e+308}'


def test_negative_zero_is_normalized() -> None:  # equal values -> equal bytes
    assert dumps({"v": -0.0}) == '{"v":0.0}'
    assert dumps({"v": [-0.0]}) == dumps({"v": [0.0]})


def test_non_finite_floats_rejected() -> None:
    for bad in (float("nan"), float("inf"), float("-inf")):
        with pytest.raises(IntegrityHalt):
            dumps({"v": bad})


def test_non_string_dict_keys_rejected() -> None:
    with pytest.raises(IntegrityHalt):
        dumps({1: "x"})


@pytest.mark.parametrize(
    "value",
    [
        dt.datetime(2026, 7, 2, tzinfo=dt.UTC),  # models serialize datetimes first
        b"bytes",
        (1, 2),
        {1, 2},
        object(),
    ],
)
def test_unsupported_types_rejected(value: object) -> None:
    with pytest.raises(IntegrityHalt):
        dumps({"v": value})


def test_unicode_is_preserved_not_escaped() -> None:
    assert dumps({"name": "burhān"}) == '{"name":"burhān"}'


def test_top_level_scalars_and_lists_supported() -> None:
    assert dumps([1, "a", None, True]) == '[1,"a",null,true]'
    assert dumps("s") == '"s"'


def test_sha256_file_streams_exact_content(tmp_path: Path) -> None:
    p = tmp_path / "f.txt"
    p.write_bytes(b"burhan\n")
    assert sha256_file(p) == "750dff600e61a43c00dcd3242f0d20aeaf1eda6deb7acee035e93a63b8d45e57"
