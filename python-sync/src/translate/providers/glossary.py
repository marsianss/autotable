"""Glossary-based exact term replacement provider."""
from __future__ import annotations
from pathlib import Path
import json

_GLOSSARY_PATH = Path("python-sync/data/glossary.json")
_CACHE: dict[str, str] | None = None

def _load() -> dict[str, str]:
    global _CACHE
    if _CACHE is None:
        try:
            if _GLOSSARY_PATH.exists():
                _CACHE = json.loads(_GLOSSARY_PATH.read_text(encoding="utf-8"))
            else:
                _CACHE = {}
        except Exception:  # noqa: BLE001
            _CACHE = {}
    return _CACHE


def translate(text: str | list[str], source: str, target: str) -> str | list[str]:  # noqa: ARG001 unused lang args by design
    if not text:
        return text
    glossary = _load()
    if isinstance(text, list):
        return [glossary.get(t, t) for t in text]
    return glossary.get(text, text)
