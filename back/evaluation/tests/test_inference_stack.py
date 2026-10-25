# SPDX-FileCopyrightText: 2025-2026 Jehanne Dussert <https://www.linkedin.com/in/jehanne-dussert>
# SPDX-License-Identifier: EUPL-1.2

"""Inference stack recorded with every judge run (services/inference_stack.py).

Ollama is not called: its two endpoints are replaced by fixtures.
Run inside the evaluation container:  python -m pytest tests/ -q
"""

import asyncio

import services.inference_stack as stack

TAGS = [
    {"name": "phi4-mini:latest", "model": "phi4-mini:latest", "digest": "78fad5d182a7"},
    {"name": "gemma3:4b", "model": "gemma3:4b", "digest": "a2af6cc3eb7f"},
]


def _patch(monkeypatch, tags, version):
    async def fake_tags():
        return tags

    async def fake_version():
        return version

    monkeypatch.setattr(stack, "ollama_tags", fake_tags)
    monkeypatch.setattr(stack, "ollama_version", fake_version)


def test_requested_models(monkeypatch):
    _patch(monkeypatch, TAGS, "0.32.15")
    s = asyncio.run(stack.get_inference_stack(["ollama/phi4-mini", "ollama/gemma3:4b"]))
    assert s.ollama_version == "0.32.15"
    assert s.model_digests == {"ollama/phi4-mini": "78fad5d182a7", "ollama/gemma3:4b": "a2af6cc3eb7f"}


def test_all_installed_models(monkeypatch):
    _patch(monkeypatch, TAGS, "0.32.15")
    s = asyncio.run(stack.get_inference_stack())
    assert s.model_digests == {"ollama/phi4-mini:latest": "78fad5d182a7", "ollama/gemma3:4b": "a2af6cc3eb7f"}


def test_unknown_model_is_omitted(monkeypatch):
    _patch(monkeypatch, TAGS, "0.32.15")
    s = asyncio.run(stack.get_inference_stack(["ollama/granite4"]))
    assert s.model_digests == {}


def test_ollama_unreachable(monkeypatch):
    _patch(monkeypatch, [], None)
    s = asyncio.run(stack.get_inference_stack(["ollama/phi4-mini"]))
    assert s.ollama_version is None and s.model_digests == {}
