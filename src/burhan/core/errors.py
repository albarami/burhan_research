"""Typed failure taxonomy (architecture §7; standards §4).

The four halt classes map 1:1 to terminal run states:
``IntegrityHalt`` -> ``HALTED_INTEGRITY``, ``VerificationHalt`` ->
``HALTED_VERIFICATION``, ``GateExhausted`` -> ``HALTED_GATE``, and
``AdvisoryStop`` -> ``COMPLETED_TO_BOUNDARY``.

Standards §4 requires every raised halt to write its machine-readable report
before propagating. The mechanism (TC-01 PLAN v2 Fix 5): all raises in guarded
layers go through :func:`halt`, which emits ``to_report()`` to the process
halt sink first. The default sink logs the report as a structured record via
``burhan.core.logging``; the orchestrator (M04) may install a run-directory
sink in addition. Components that own a live working directory use
:func:`halt_with_file` to co-locate a ``halt_report.json`` with their
artifacts before propagating.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any, ClassVar, NoReturn, Protocol

HALT_REPORT_FILENAME = "halt_report.json"


class BurhanHalt(Exception):
    """Base of the typed failure taxonomy.

    Args:
        message: Human-readable condition statement.
        report: Machine-readable details (must be canonical-JSON serializable).
    """

    run_state: ClassVar[str] = "HALTED_INTEGRITY"

    def __init__(self, message: str, *, report: dict[str, Any] | None = None) -> None:
        super().__init__(message)
        self.message = message
        self.details: dict[str, Any] = report if report is not None else {}

    def to_report(self) -> dict[str, Any]:
        """Return the machine-readable halt report (canonical-serializable)."""
        return {
            "halt_class": type(self).__name__,
            "run_state": self.run_state,
            "message": self.message,
            "details": self.details,
        }


class IntegrityHalt(BurhanHalt):
    """Data-document mismatch, invariant failure, worker fault (FR-1204)."""

    run_state: ClassVar[str] = "HALTED_INTEGRITY"


class VerificationHalt(BurhanHalt):
    """Dual-path or parity breach beyond tolerance (FR-501, FR-903)."""

    run_state: ClassVar[str] = "HALTED_VERIFICATION"


class GateExhausted(BurhanHalt):
    """Node C review retries exhausted (FR-303)."""

    run_state: ClassVar[str] = "HALTED_GATE"


class AdvisoryStop(BurhanHalt):
    """Evidence challenges the approved method; defensible boundary (FR-1203)."""

    run_state: ClassVar[str] = "COMPLETED_TO_BOUNDARY"


class HaltSink(Protocol):
    """Receiver of machine-readable halt reports."""

    def emit(self, report: dict[str, Any]) -> None:
        """Persist or forward one halt report."""
        ...


class _LoggingHaltSink:
    """Default sink: emit the report as a structured log record."""

    def emit(self, report: dict[str, Any]) -> None:
        # Deferred import: burhan.core.logging depends on canonical, which
        # depends on this module; the cycle is broken at call time.
        from burhan.core.logging import get_logger

        get_logger("burhan.halt").error("halt", extra={"data": report})


_DEFAULT_SINK: HaltSink = _LoggingHaltSink()
_sink: HaltSink = _DEFAULT_SINK


def get_halt_sink() -> HaltSink:
    """Return the currently installed halt sink."""
    return _sink


def set_halt_sink(sink: HaltSink) -> HaltSink:
    """Install ``sink`` and return the previously installed one."""
    global _sink
    previous = _sink
    _sink = sink
    return previous


def reset_halt_sink() -> None:
    """Restore the default (structured-logging) halt sink."""
    global _sink
    _sink = _DEFAULT_SINK


def halt(exc: BurhanHalt) -> NoReturn:
    """Emit the halt's machine-readable report to the sink, then raise it.

    This is the single sanctioned raise path for taxonomy exceptions in
    guarded layers (standards §4: report written before propagation).
    """
    get_halt_sink().emit(exc.to_report())
    raise exc


def write_halt_report(exc: BurhanHalt, directory: Path) -> Path:
    """Write ``halt_report.json`` (canonical JSON) into ``directory``.

    Does not emit to the sink and does not raise — used by components that
    catch an already-emitted halt and must co-locate its file-form report
    before re-raising.
    """
    # Deferred import: canonical imports this module at module level.
    from burhan.core.artifacts.canonical import dumps

    directory.mkdir(parents=True, exist_ok=True)
    report_path = directory / HALT_REPORT_FILENAME
    report_path.write_text(dumps(exc.to_report()) + "\n", encoding="utf-8")
    return report_path


def halt_with_file(exc: BurhanHalt, directory: Path) -> NoReturn:
    """Write ``halt_report.json`` into ``directory``, then :func:`halt`.

    For components that own a live (unsealed) working directory; never used
    against sealed run directories, which are immutable (architecture §11).
    """
    write_halt_report(exc, directory)
    halt(exc)
