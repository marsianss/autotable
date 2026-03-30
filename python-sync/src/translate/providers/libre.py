"""LibreTranslate provider via REST API."""
from __future__ import annotations
import os
import requests

API_URL_ENV = "TRANSLATE_API_URL"

def translate(text: str | list[str], source: str, target: str) -> str | list[str]:
    if not text:
        return text
    base = os.getenv(API_URL_ENV, "https://libretranslate.com").rstrip("/")
    url = f"{base}/translate"
    
    # Handle batch
    if isinstance(text, list):
        payload = {"q": text, "source": source, "target": target, "format": "text"}
        try:
            r = requests.post(url, json=payload, timeout=15) # Increased timeout for batch
            if r.status_code >= 400:
                return text
            data = r.json()
            # LibreTranslate returns { "translatedText": [...] } for batch or list of results?
            # Official API: returns { "translatedText": ["..."] } if q is list
            translated = data.get("translatedText")
            if translated and isinstance(translated, list):
                return translated
        except Exception:
            return text
        return text

    payload = {"q": text, "source": source, "target": target, "format": "text"}
    try:
        r = requests.post(url, data=payload, timeout=8)
        if r.status_code >= 400:
            return text
        data = r.json()
        translated = data.get("translatedText")
        if translated and isinstance(translated, str):
            return translated
    except Exception:  # noqa: BLE001
        return text
    return text
