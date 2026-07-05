"""Orchestrator stage adapters (TC-15).

Thin ``Stage``-protocol adapters that wire the already-certified Stage-1A
modules (``prep``/``stats``/``verify``/``contract``/``review``) into the fixed
DAG, plus deterministic Stage-1B certification pass-through stubs (narrate,
gate2, package) whose real behavior is delivered by TC-13/TC-14. The adapters
add no statistical behavior; they call existing functions and serialize their
returns into the results store and provenance.
"""
