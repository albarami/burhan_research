"""LLM adapter base (AD-04; FR-206/304; NFR-401/402).

Every LLM node subclasses :class:`AdapterBase`, which enforces the
architecture's boundary rules in code, not convention:

- **Closed allowlist** — each adapter declares its input slots
  (``ALLOWED_INPUTS``); anything else is rejected by name at the boundary.
- **No raw data, in any form** — ``Path`` objects, bytes, dataframe-like
  objects, and strings that point at data files (.csv/.xlsx/.sav/…) all
  halt before a prompt is built (FR-206, NFR-401). Only text crosses.
- **Deterministic settings** — ``temperature`` must be 0 in the machine
  config; anything else fails startup (AD-04).
- **Lineage independence** — ``lineage(node_a) == lineage(node_c)`` fails
  startup validation (FR-304; the Sanad principle).
- **Versioned prompts** — templates are files; their version and SHA-256
  enter every run manifest (AD-04, NFR-102).

The provider callable is injected; unit tests never touch the network.
``resolve_provider_call`` builds the real clients for production use.
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path
from typing import Any, ClassVar

# Untyped third-party edge (no stubs in the locked dependency set).
import yaml  # type: ignore[import-untyped]

from burhan.core.artifacts.canonical import sha256_file
from burhan.core.errors import IntegrityHalt, halt

_RAW_DATA_SUFFIXES = (".csv", ".xlsx", ".xls", ".sav", ".dta", ".parquet", ".feather")
_REQUIRED_NODES = ("node_a", "node_b", "node_c")


@dataclass(frozen=True)
class NodeSettings:
    """One node's pinned provider configuration."""

    provider: str
    model: str
    lineage: str
    temperature: float
    api_key_env: str
    max_retries: int


@dataclass(frozen=True)
class LlmSettings:
    """Validated machine-local LLM configuration (04 §5)."""

    nodes: dict[str, NodeSettings]
    source_sha256: str

    def node(self, name: str) -> NodeSettings:
        """Settings for one node; unknown names are defects."""
        settings = self.nodes.get(name)
        if settings is None:
            halt(
                IntegrityHalt(
                    "unknown LLM node",
                    report={"node": name, "known": sorted(self.nodes)},
                )
            )
        return settings


def load_llm_settings(path: Path) -> LlmSettings:
    """Load and validate ``llm.yaml`` (FR-304; AD-04 deterministic settings)."""
    try:
        raw = yaml.safe_load(path.read_text(encoding="utf-8"))
    except OSError as exc:
        halt(IntegrityHalt("llm.yaml unreadable", report={"path": str(path), "error": str(exc)}))
    except yaml.YAMLError as exc:
        halt(
            IntegrityHalt(
                "llm.yaml is not valid YAML", report={"path": str(path), "error": str(exc)}
            )
        )
    if not isinstance(raw, dict) or "nodes" not in raw or "providers" not in raw:
        halt(IntegrityHalt("llm.yaml lacks nodes/providers blocks", report={"path": str(path)}))
    providers = raw["providers"]
    nodes: dict[str, NodeSettings] = {}
    for name in _REQUIRED_NODES:
        spec = raw["nodes"].get(name)
        if not isinstance(spec, dict) or not {"provider", "model", "lineage"} <= spec.keys():
            halt(
                IntegrityHalt(
                    "llm.yaml node incomplete",
                    report={"path": str(path), "node": name},
                )
            )
        temperature = float(spec.get("temperature", -1))
        if temperature != 0:
            halt(
                IntegrityHalt(
                    "non-deterministic temperature configured; adapters run with "
                    "deterministic settings (AD-04)",
                    report={"node": name, "temperature": temperature},
                )
            )
        provider = str(spec["provider"])
        provider_spec = providers.get(provider)
        if not isinstance(provider_spec, dict) or not provider_spec.get("api_key_env"):
            halt(
                IntegrityHalt(
                    "llm.yaml provider has no resolvable api_key_env",
                    report={"node": name, "provider": provider},
                )
            )
        nodes[name] = NodeSettings(
            provider=provider,
            model=str(spec["model"]),
            lineage=str(spec["lineage"]),
            temperature=temperature,
            api_key_env=str(provider_spec["api_key_env"]),
            max_retries=int(spec.get("max_retries", 2)),
        )
    if nodes["node_a"].lineage == nodes["node_c"].lineage:
        halt(
            IntegrityHalt(
                "lineage(node_a) == lineage(node_c) violates FR-304: extraction "
                "and audit must never share a failure mode (Sanad independence)",
                report={"lineage": nodes["node_a"].lineage},
            )
        )
    return LlmSettings(nodes=nodes, source_sha256=sha256_file(path))


def screen_boundary_input(slot: str, value: object) -> str | None:
    """Admit only text through the adapter boundary (FR-206, NFR-401).

    Raw-data vectors — Path objects, bytes, dataframe-like objects, or
    strings pointing at data files — halt by construction.
    """
    if value is None:
        return None
    if isinstance(value, Path):
        halt(
            IntegrityHalt(
                "raw-data path rejected at the adapter boundary (NFR-401)",
                report={"slot": slot, "kind": "path"},
            )
        )
    if isinstance(value, bytes | bytearray):
        halt(
            IntegrityHalt(
                "raw bytes rejected at the adapter boundary (NFR-401)",
                report={"slot": slot, "kind": "bytes"},
            )
        )
    if not isinstance(value, str):
        kind = type(value).__name__
        if hasattr(value, "iloc") or hasattr(value, "columns"):
            kind = "dataframe-like"
        halt(
            IntegrityHalt(
                "non-text input rejected at the adapter boundary (NFR-401)",
                report={"slot": slot, "kind": kind},
            )
        )
    if value.strip().lower().endswith(_RAW_DATA_SUFFIXES):
        halt(
            IntegrityHalt(
                "string points at a raw-data file; rejected at the adapter boundary (NFR-401)",
                report={"slot": slot, "kind": "data-file-path"},
            )
        )
    return value


class AdapterBase:
    """Shared LLM adapter: one door (``complete``), allowlisted and screened."""

    node: ClassVar[str]
    ALLOWED_INPUTS: ClassVar[tuple[str, ...]]

    def __init__(self, settings: LlmSettings, *, provider_call: Callable[[str], str]) -> None:
        self._settings = settings
        self._node_settings = settings.node(self.node)
        self._provider_call = provider_call

    def complete(self, **inputs: object) -> str:
        """Screen the allowlisted inputs, build the prompt, call the provider."""
        unknown = sorted(set(inputs) - set(self.ALLOWED_INPUTS))
        if unknown:
            halt(
                IntegrityHalt(
                    "input outside the adapter allowlist (AD-04)",
                    report={"node": self.node, "unknown": unknown},
                )
            )
        screened = {
            slot: screen_boundary_input(slot, inputs.get(slot)) for slot in self.ALLOWED_INPUTS
        }
        return self._provider_call(self._build_prompt(screened))

    def _build_prompt(self, inputs: dict[str, str | None]) -> str:
        parts = [f"[{slot}]\n{text}" for slot, text in inputs.items() if text is not None]
        return "\n\n".join(parts)


def prompt_manifest_entry(template_path: Path) -> dict[str, Any]:
    """Version + SHA-256 of a prompt template for the run manifest (AD-04)."""
    if not template_path.is_file():
        halt(
            IntegrityHalt(
                "prompt template missing",
                report={"path": str(template_path)},
            )
        )
    return {"version": template_path.stem, "sha256": sha256_file(template_path)}


def resolve_provider_call(settings: LlmSettings, node: str) -> Callable[[str], str]:
    """Build the real provider callable for production use (network edge).

    This is the engine's ONLY network-capable code path (architecture §11:
    compute stages make no network calls; only LLM adapters may egress, to
    configured providers). Unit tests inject fakes instead.
    """
    node_settings = settings.node(node)
    if node_settings.provider == "anthropic":

        def call_anthropic(prompt: str) -> str:
            import anthropic
            from anthropic.types import TextBlock

            client = anthropic.Anthropic()
            response = client.messages.create(
                model=node_settings.model,
                max_tokens=8192,
                temperature=0,
                messages=[{"role": "user", "content": prompt}],
            )
            return "".join(block.text for block in response.content if isinstance(block, TextBlock))

        return call_anthropic
    if node_settings.provider == "openai":

        def call_openai(prompt: str) -> str:
            import openai

            client = openai.OpenAI()
            response = client.chat.completions.create(
                model=node_settings.model,
                temperature=0,
                messages=[{"role": "user", "content": prompt}],
            )
            return str(response.choices[0].message.content)

        return call_openai
    halt(
        IntegrityHalt(
            "unknown provider for node",
            report={"node": node, "provider": node_settings.provider},
        )
    )
