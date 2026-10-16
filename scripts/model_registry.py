# SPDX-FileCopyrightText: 2025-2026 Jehanne Dussert <https://www.linkedin.com/in/jehanne-dussert>
# SPDX-License-Identifier: EUPL-1.2
"""Model registry for the analysis scripts — reads docs/benchmark/models.json.

Replaces the per-script hardcoded model lists (sizes, labels, colors, slugs).
"""

import json
from pathlib import Path

REGISTRY_FILE = Path(__file__).resolve().parent.parent / "docs" / "benchmark" / "models.json"

_data = json.loads(REGISTRY_FILE.read_text(encoding="utf-8"))
MODELS: dict[str, dict] = {m["slug"]: m for m in _data["models"]}
SETS: dict[str, list[str]] = _data["sets"]

# Lookups from the other spellings found in result files / the DB.
_BY_ID = {m["id"]: m["slug"] for m in _data["models"]}
_BY_FILE_SLUG = {m.get("file_slug", m["slug"]): m["slug"] for m in _data["models"]}


def short_name(ollama_id: str) -> str:
    """Filename-style slug as written by the benchmark scripts."""
    return ollama_id.removeprefix("ollama/").replace(":", "-").replace("/", "-")


def slug_of(name: str) -> str:
    """Registry slug from an Ollama id ('ollama/gemma3:4b'), a file slug, or a slug."""
    if name in MODELS:
        return name
    if name in _BY_ID:
        return _BY_ID[name]
    if name in _BY_FILE_SLUG:
        return _BY_FILE_SLUG[name]
    s = short_name(name)
    if s in _BY_FILE_SLUG:
        return _BY_FILE_SLUG[s]
    raise KeyError(f"model {name!r} not in {REGISTRY_FILE.name} — add it there")


def select(spec: str | None) -> list[str]:
    """'all' (default), a set name from models.json, or a comma-separated slug list."""
    if not spec or spec == "all":
        return list(MODELS)
    if spec in SETS:
        return list(SETS[spec])
    return [slug_of(s.strip()) for s in spec.split(",")]


def label(slug: str) -> str:
    return MODELS[slug]["label"]


def color(slug: str) -> str:
    return MODELS[slug]["color"]


def family(slug: str) -> str:
    return MODELS[slug]["family"]
