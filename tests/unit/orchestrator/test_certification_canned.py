"""AT-M16-2: the certification path stays canned and offline (TC-16 guardrail).

TC-16 adds the live path but must not perturb ``--certification``. These lock the
canned markers: certification settings carry the ``certification-canned`` model
and a placeholder source hash, the certification module never imports the live
network client (``resolve_provider_call``), and its nodes are ``lambda`` echoes.
The behavioural end-to-end proof that certification still reaches COMPLETED under
canned nodes is IT-6 / the AT-M15 suite (kept green by AT-M16-8).
"""

from __future__ import annotations

import inspect

import burhan.cli.certification as certification


def test_certification_settings_are_canned() -> None:
    settings = certification.certification_settings()
    assert settings.node("node_a").model == "certification-canned"
    assert settings.node("node_c").model == "certification-canned"
    assert settings.source_sha256 == "0" * 64


def test_certification_never_wires_a_live_network_client() -> None:
    # The live client lives in llm_base / cli.live; the certification path must
    # not import or reference it — it injects canned providers only.
    assert not hasattr(certification, "resolve_provider_call")
    source = inspect.getsource(certification)
    assert "resolve_provider_call" not in source
    assert "provider_call=lambda" in source  # nodes are canned echoes
