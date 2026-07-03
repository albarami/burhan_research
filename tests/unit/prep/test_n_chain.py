"""N-chain accountant tests (AT-M08-3; FR-506).

The chain is case-level bookkeeping, not arithmetic on totals: every link
records exactly which cases left, sums must reconcile at every link, and a
case dropped twice — a double-count — halts the run.
"""

from __future__ import annotations

import pytest

from burhan.core.errors import IntegrityHalt
from burhan.prep.n_chain import NChainAccountant

CASES = tuple(f"R_{i:03d}" for i in range(1, 11))  # ten raw cases


def test_chain_sums_exactly_at_every_link() -> None:  # AT-M08-3
    accountant = NChainAccountant(CASES)
    accountant.apply("consent", dropped=())
    accountant.apply("duplicates", dropped=("R_002",))
    accountant.apply("attention_checks", dropped=("R_005", "R_007"))
    accountant.apply("straight_liners", dropped=("R_009",))
    accountant.apply("partial_recovery", dropped=("R_004",), recovered=("R_006",))
    accountant.apply("outlier_policy", dropped=())
    chain = accountant.finalize()

    assert chain.raw_n == 10
    assert chain.final_n == 5
    links = {link.name: link for link in chain.links}
    assert links["duplicates"].entering == 10
    assert links["duplicates"].leaving == 9
    assert links["attention_checks"].entering == 9
    assert links["attention_checks"].leaving == 7
    assert links["partial_recovery"].recovered_n == 1
    # every link: leaving == entering - dropped; adjacent links join exactly
    for link in chain.links:
        assert link.leaving == link.entering - link.dropped_n
    for left, right in zip(chain.links, chain.links[1:], strict=False):
        assert left.leaving == right.entering
    assert chain.final_cases == ("R_001", "R_003", "R_006", "R_008", "R_010")


def test_planted_double_count_halts() -> None:  # AT-M08-3 (FR-506)
    accountant = NChainAccountant(CASES)
    accountant.apply("duplicates", dropped=("R_002",))
    with pytest.raises(IntegrityHalt) as excinfo:
        accountant.apply("attention_checks", dropped=("R_002",))  # dropped twice
    assert "double-count" in excinfo.value.message
    assert "R_002" in str(excinfo.value.to_report()["details"])


def test_unknown_case_in_a_drop_list_halts() -> None:
    accountant = NChainAccountant(CASES)
    with pytest.raises(IntegrityHalt) as excinfo:
        accountant.apply("duplicates", dropped=("R_999",))
    assert "unknown" in excinfo.value.message


def test_recovered_case_must_still_be_in_the_sample() -> None:
    accountant = NChainAccountant(CASES)
    accountant.apply("duplicates", dropped=("R_002",))
    with pytest.raises(IntegrityHalt):
        accountant.apply("partial_recovery", recovered=("R_002",))  # already gone


def test_duplicate_raw_case_ids_halt_at_construction() -> None:
    with pytest.raises(IntegrityHalt) as excinfo:
        NChainAccountant(("R_001", "R_001", "R_002"))
    assert "duplicate" in excinfo.value.message


def test_payload_is_deterministic_and_value_free() -> None:
    def build() -> dict[str, object]:
        accountant = NChainAccountant(CASES)
        accountant.apply("duplicates", dropped=("R_002",))
        accountant.apply("partial_recovery", dropped=("R_004",), recovered=("R_006",))
        return accountant.finalize().to_payload()

    payload = build()
    assert payload == build()  # same inputs, byte-identical structure
    assert payload["raw_n"] == 10
    assert payload["final_n"] == 8
    link_names = [link["name"] for link in payload["links"]]  # type: ignore[index]
    assert link_names == ["duplicates", "partial_recovery"]
