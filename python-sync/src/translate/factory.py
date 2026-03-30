"""Translation manager and provider chaining."""
from __future__ import annotations
from typing import Callable, Dict, List
import os
import json
import threading
from pathlib import Path
import re
import html
from loguru import logger
from dotenv import load_dotenv
from diskcache import Cache

load_dotenv()

class TranslationManager:
    """Chains translation providers according to environment configuration.

    Caches translations in data/cache/translations_db to avoid redundant calls.
    """

    def __init__(
        self,
        enabled: bool | None = None,
        source_lang: str | None = None,
        target_lang: str | None = None,
        provider_order: List[str] | None = None,
        cache_path: str | None = None,
    ) -> None:
        self.enabled = enabled if enabled is not None else os.getenv("TRANSLATE_ENABLED", "true").lower() == "true"
        self.source_lang = source_lang or os.getenv("TRANSLATE_SOURCE_LANG", "hu")
        self.target_lang = target_lang or os.getenv("TRANSLATE_TARGET_LANG", "nl")
        # Default order favors glossary/dictionary before MT to preserve domain terms
        order_env = os.getenv("TRANSLATE_PROVIDER_ORDER", "glossary,dictionary,google,libre")
        self.provider_order = provider_order or [p.strip() for p in order_env.split(',') if p.strip()]
        
        # Use diskcache for persistent caching
        cache_dir = cache_path or "python-sync/data/cache/translations_db"
        self.cache = Cache(cache_dir)
        
        self.providers: Dict[str, Callable[[str, str, str], str]] = {}
        self._load_providers()
        self._lock = threading.Lock()

    def save(self) -> None:
        """Force save cache to disk (No-op for diskcache as it auto-saves)."""
        pass

    def _load_providers(self) -> None:
        from .providers import google, libre, glossary, dictionary  # local imports
        available = {
            "google": google.translate,
            "libre": libre.translate,
            "glossary": glossary.translate,
            "dictionary": dictionary.translate,
        }
        for name in self.provider_order:
            func = available.get(name)
            if func:
                self.providers[name] = func
            else:
                logger.warning(f"Unknown translation provider: {name}")

    def _cache_key(self, text: str) -> str:
        return f"{self.source_lang}:{self.target_lang}:{text}"[:500]

    def _strip_html(self, text: str) -> str:
        if not text:
            return text
        # Normalize breaks to spaces to keep sentences separate
        txt = text.replace('<br />', ' ').replace('<br/>', ' ').replace('<br>', ' ')
        # Remove all tags
        txt = re.sub(r"<[^>]+>", " ", txt)
        # Unescape entities and collapse whitespace
        txt = html.unescape(txt)
        txt = re.sub(r"\s+", " ", txt).strip()
        return txt

    def translate(self, text: str) -> str:
        """Translate text through provider chain.

        Returns original text if disabled or no provider changes it.
        """
        if not text:
            return text
        if not self.enabled:
            return text
        cleaned = self._strip_html(text)
        if not cleaned:
            return cleaned
        key = self._cache_key(cleaned)
        
        # Check cache
        if key in self.cache:
            return self.cache[key]
        
        original = text
        google_sleep = float(os.getenv("TRANSLATE_GOOGLE_SLEEP", "0"))
        for name, provider in self.providers.items():
            try:
                # Optional minimal delay for google to reduce rate-limit risk; default 0 (fast)
                if name == 'google' and google_sleep > 0:
                    import time
                    time.sleep(google_sleep)

                new_text = provider(cleaned, self.source_lang, self.target_lang)
            except Exception as exc:  # noqa: BLE001
                logger.warning(f"Provider '{name}' failed: {exc}")
                continue
            if new_text and new_text != cleaned:
                logger.debug(f"Provider '{name}' changed text")
                cleaned = new_text
        
        # Update cache
        self.cache[key] = cleaned
        return cleaned

    def translate_batch(self, texts: List[str]) -> List[str]:
        """Translate a batch of texts."""
        if not texts:
            return []
        if not self.enabled:
            return texts
        
        results = [None] * len(texts)
        missing_indices = []
        missing_texts = []
        
        # 1. Check cache
        for i, text in enumerate(texts):
            if not text:
                results[i] = ""
                continue
            cleaned = self._strip_html(text)
            key = self._cache_key(cleaned)
            cached = self.cache.get(key)
            # Treat "cached == original" as a miss so we can retry translation instead of
            # being stuck with an untranslated entry.
            if cached is not None and cached != cleaned:
                results[i] = cached
            else:
                missing_indices.append(i)
                missing_texts.append(cleaned)
        
        if not missing_texts:
            return results
            
        # 2. Translate missing
        current_texts = list(missing_texts)
        
        google_sleep = float(os.getenv("TRANSLATE_GOOGLE_SLEEP", "0"))
        for name, provider in self.providers.items():
            try:
                if name == 'google' and google_sleep > 0:
                    import time
                    time.sleep(google_sleep)
                
                new_texts = provider(current_texts, self.source_lang, self.target_lang)
                
                if isinstance(new_texts, list) and len(new_texts) == len(current_texts):
                    current_texts = new_texts
                else:
                    logger.warning(f"Provider '{name}' returned invalid batch result")
            except Exception as exc:
                logger.warning(f"Provider '{name}' batch failed: {exc}")
                continue
        
        # 3. Update cache and results
        for i, original_idx in enumerate(missing_indices):
            translated = current_texts[i]
            original_text = missing_texts[i]

            # Fallback: if batch providers returned text unchanged, try single-item translate
            # (google single works even when list mode is a no-op).
            if translated == original_text:
                key = self._cache_key(original_text)
                # avoid returning a stale untranslated cache hit
                if key in self.cache:
                    try:
                        del self.cache[key]
                    except Exception:
                        pass
                translated = self.translate(original_text)

            key = self._cache_key(original_text)
            # only cache if we actually changed the text; otherwise leave it uncached so
            # future runs can still attempt translation.
            if translated != original_text:
                self.cache[key] = translated
            results[original_idx] = translated
            
        return results

__all__ = ["TranslationManager"]
