"""Exact N reconciliation chain (FR-506; PB-02 n_chain_exact).

Case-level bookkeeping, not arithmetic on totals: the accountant records
exactly which cases each link removed, so the chain cannot merely *appear*
to sum — the final case set must equal the raw set minus every dropped set,
disjointly. A case dropped twice (a double-count), an unknown case, or a
recovery annotation on a case no longer in the sample halts the run with
``IntegrityHalt``.

Recovery (FR-502) is an annotation, not an arithmetic move: recovered
partials never left the sample, so ``leaving == entering - dropped_n`` at
every link. Payloads carry case IDs and counts only — never respondent
values.
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass
from typing import Any

from burhan.core.errors import IntegrityHalt, halt


@dataclass(frozen=True)
class NChainLink:
    """One link: who entered, who was dropped, who remained."""

    name: str
    entering: int
    dropped_n: int
    recovered_n: int
    leaving: int
    dropped_cases: tuple[str, ...]
    recovered_cases: tuple[str, ...]

    def to_payload(self) -> dict[str, Any]:
        return {
            "name": self.name,
            "entering": self.entering,
            "dropped_n": self.dropped_n,
            "recovered_n": self.recovered_n,
            "leaving": self.leaving,
            "dropped_cases": list(self.dropped_cases),
            "recovered_cases": list(self.recovered_cases),
        }


@dataclass(frozen=True)
class NChain:
    """The finalized chain: raw → links → final analytical N (FR-506)."""

    raw_n: int
    final_n: int
    links: tuple[NChainLink, ...]
    final_cases: tuple[str, ...]

    def to_payload(self) -> dict[str, Any]:
        return {
            "raw_n": self.raw_n,
            "final_n": self.final_n,
            "links": [link.to_payload() for link in self.links],
            "final_cases": list(self.final_cases),
        }


class NChainAccountant:
    """Builds the chain link by link, halting on any accounting defect."""

    def __init__(self, raw_cases: Sequence[str]) -> None:
        duplicates = sorted({case for case in raw_cases if list(raw_cases).count(case) > 1})
        if duplicates:
            halt(
                IntegrityHalt(
                    "N-chain raw case ids contain duplicate identifiers",
                    report={"duplicate_ids": duplicates},
                )
            )
        self._raw: tuple[str, ...] = tuple(raw_cases)
        self._current: tuple[str, ...] = tuple(raw_cases)
        self._dropped_ever: set[str] = set()
        self._links: list[NChainLink] = []

    def apply(
        self,
        name: str,
        *,
        dropped: Sequence[str] = (),
        recovered: Sequence[str] = (),
    ) -> None:
        """Record one link; exactness is enforced at the case level."""
        current = set(self._current)
        for case in dropped:
            if case in self._dropped_ever:
                halt(
                    IntegrityHalt(
                        "N-chain double-count: case dropped by more than one "
                        "link (FR-506 exact sums)",
                        report={"link": name, "case": case},
                    )
                )
            if case not in current:
                halt(
                    IntegrityHalt(
                        "N-chain drop names an unknown case",
                        report={"link": name, "case": case},
                    )
                )
        for case in recovered:
            if case not in current or case in set(dropped):
                halt(
                    IntegrityHalt(
                        "N-chain recovery names a case not in the sample; "
                        "recovered partials never left it (FR-502)",
                        report={"link": name, "case": case},
                    )
                )
        entering = len(self._current)
        leaving_cases = tuple(case for case in self._current if case not in set(dropped))
        self._links.append(
            NChainLink(
                name=name,
                entering=entering,
                dropped_n=len(tuple(dropped)),
                recovered_n=len(tuple(recovered)),
                leaving=len(leaving_cases),
                dropped_cases=tuple(dropped),
                recovered_cases=tuple(recovered),
            )
        )
        self._dropped_ever.update(dropped)
        self._current = leaving_cases

    def finalize(self) -> NChain:
        """Close the chain, re-verifying the case-level identity end to end."""
        reconstructed = tuple(case for case in self._raw if case not in self._dropped_ever)
        if reconstructed != self._current:
            halt(
                IntegrityHalt(
                    "N-chain failed case-level reconciliation (FR-506)",
                    report={
                        "expected_n": len(reconstructed),
                        "actual_n": len(self._current),
                    },
                )
            )
        return NChain(
            raw_n=len(self._raw),
            final_n=len(self._current),
            links=tuple(self._links),
            final_cases=self._current,
        )
