"""Fallback static dictionary provider for common HU->NL terms."""
from __future__ import annotations

_DICTIONARY = {
    "számítógép": "computer",
    "egér": "muis",
    "billentyűzet": "toetsenbord",
    "monitor": "monitor",
    "kábel": "kabel",
}

def translate(text: str | list[str], source: str, target: str) -> str | list[str]:  # noqa: ARG001
    if isinstance(text, list):
        return [_DICTIONARY.get(t, t) for t in text]
    return _DICTIONARY.get(text, text)
