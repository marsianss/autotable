"""Google Translate provider using googletrans."""
from __future__ import annotations
from typing import Any
try:
    from googletrans import Translator  # type: ignore
except Exception:  # noqa: BLE001
    Translator = None  # type: ignore

_translator: Any | None = None

def _get() -> Any | None:
    global _translator
    if _translator is None and Translator is not None:
        try:
            _translator = Translator()
        except Exception:  # noqa: BLE001
            _translator = None
    return _translator


def translate(text: str | list[str], source: str, target: str) -> str | list[str]:
    if not text or Translator is None:
        return text
    translator = _get()
    if translator is None:
        return text
    try:
        result = translator.translate(text, src=source, dest=target)
        if isinstance(text, list):
            return [r.text for r in result]
        return result.text or text
    except Exception:  # noqa: BLE001
        return text
