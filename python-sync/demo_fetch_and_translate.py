#!/usr/bin/env python3
"""Demo: fetch a small set of products (if available) and run translations.

This script is resilient: if UNAS calls fail (wrong endpoint), it will still
exercise the translation chain on sample Hungarian texts so you can verify
translation providers and caching behavior locally.

Run:
    python python-sync\demo_fetch_and_translate.py
"""
from __future__ import annotations
import os
import sys
import traceback
from dotenv import load_dotenv

# Ensure local src is importable when running via script path
ROOT = os.path.dirname(__file__)
SRC = os.path.join(ROOT, "src")
if SRC not in sys.path:
    sys.path.insert(0, SRC)

load_dotenv(os.path.join(ROOT, ".env"))

# Local imports (from project src)
try:
    from unas.client import UNASClient
except Exception:
    UNASClient = None  # type: ignore

try:
    from translate.factory import TranslationManager
except Exception:
    TranslationManager = None  # type: ignore


def demo_translate_samples(tm):
    samples = [
        "Pamut törölköző 70x140 cm, puha és gyorsan száradó",
        "Fürdőlepedő mintás, 100% pamut, gépben mosható",
        "Gyerek ágynemű garnitúra - Disney mintával"
    ]
    print('\n--- Translation demo (HU -> NL) ---')
    for s in samples:
        try:
            out = tm.translate(s)
        except Exception as exc:
            out = f"(translate error: {exc})"
        print('\nHU:', s)
        print('NL:', out)


def main():
    print('Demo: fetch from UNAS (if configured) and translate sample texts')
    if UNASClient is None:
        print('Warning: UNAS client module not available; skipping UNAS calls')
    if TranslationManager is None:
        print('Warning: Translation manager not available; exiting')
        return

    tm = TranslationManager()

    # Try to talk to UNAS, but keep demo resilient
    if UNASClient is not None:
        try:
            client = UNASClient.from_env()
            print('Attempting UNAS login and a small product fetch...')
            try:
                # First fetch categories (small/light) and pick a category to filter products
                cats = client.get_categories()
                print('UNAS get_categories returned (truncated):')
                import json
                print(json.dumps(cats, indent=2, ensure_ascii=False)[:1200])
                # Try to discover a category id in the parsed response
                def find_first_category_id(node):
                    if isinstance(node, dict):
                        for k, v in node.items():
                            if k.lower() in ('id', 'categoryid') and isinstance(v, (str, int)):
                                return str(v)
                            res = find_first_category_id(v)
                            if res:
                                return res
                    elif isinstance(node, list):
                        for item in node:
                            res = find_first_category_id(item)
                            if res:
                                return res
                    return None

                cat_id = find_first_category_id(cats)
                if cat_id:
                    print('Using category id', cat_id, 'to request a small product page')
                    try:
                        prods = client.get_products_page(limit=10, offset=0, extra={'CategoryId': cat_id})
                        print('UNAS get_products (filtered by category) returned (truncated):')
                        print(json.dumps(prods, indent=2, ensure_ascii=False)[:2000])
                    except Exception as exc:
                        print('UNAS filtered product fetch failed:', exc)
                        traceback.print_exc()
                else:
                    print('No category id found; skipping filtered product fetch')
            except Exception as exc:
                print('UNAS category/product flow failed:', exc)
                traceback.print_exc()
        except Exception as exc:
            print('Failed creating UNAS client or during login:', exc)
            traceback.print_exc()

    # Always show translation behavior
    demo_translate_samples(tm)


if __name__ == '__main__':
    main()
