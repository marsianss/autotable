#!/usr/bin/env python3
"""Enrich `data/active_products_export.csv` by fetching per-product details from UNAS
and adding `ShortDescription` and `LongDescription` columns when available.

Backups the original CSV to `*.bak` before writing.
Requires UNAS credentials in the parent `.env` (UNAS_API_BASE / UNAS_API_KEY etc.).
"""
from __future__ import annotations
import os, sys, csv, time, shutil
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'src'))
from dotenv import load_dotenv
load_dotenv(os.path.join(os.path.dirname(__file__), '..', '.env'))

try:
    from unas.client import UNASClient
except Exception as exc:
    print('Failed importing UNASClient:', exc)
    raise

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), '..'))
CSV_PATH = os.path.join(ROOT, 'data', 'active_products_export.csv')

DELAY = float(os.getenv('UNAS_DETAIL_DELAY', '0.25'))


def extract_texts_from_prod(prod: dict) -> tuple[str, str]:
    # prod may contain 'Texts' or 'Description'
    texts = prod.get('Texts') or prod.get('Description') or {}
    short = ''
    long = ''
    if isinstance(texts, dict):
        top = texts.get('Top') or texts.get('Short') or ''
        bottom = texts.get('Bottom') or texts.get('Long') or ''
        if isinstance(top, dict) and '#text' in top:
            top = top['#text']
        if isinstance(bottom, dict) and '#text' in bottom:
            bottom = bottom['#text']
        short = top or ''
        long = bottom or ''
    return short, long


def enrich():
    if not os.path.exists(CSV_PATH):
        print('CSV not found:', CSV_PATH)
        return
    with open(CSV_PATH, newline='', encoding='utf-8') as fh:
        rows = list(csv.DictReader(fh))

    if not rows:
        print('CSV is empty')
        return

    # Ensure columns exist
    for r in rows:
        if 'ShortDescription' not in r:
            r['ShortDescription'] = ''
        if 'LongDescription' not in r:
            r['LongDescription'] = ''

    client = UNASClient.from_env()

    updated = 0
    for i, r in enumerate(rows):
        pid = r.get('Id') or r.get('id')
        if not pid:
            continue
        # skip if already present
        if r.get('ShortDescription') or r.get('LongDescription'):
            continue
        try:
            detail = client.get_product_detail(pid)
            prod = None
            if isinstance(detail, dict):
                if 'Products' in detail and isinstance(detail['Products'], dict) and 'Product' in detail['Products']:
                    prod = detail['Products']['Product']
                elif 'Product' in detail:
                    prod = detail['Product']
                else:
                    prod = detail
            if isinstance(prod, list):
                prod = prod[0]
            if isinstance(prod, dict):
                short, long = extract_texts_from_prod(prod)
                if short:
                    r['ShortDescription'] = short
                if long:
                    r['LongDescription'] = long
                updated += 1
            else:
                print('No product object for id', pid)
        except Exception as exc:
            print('Error fetching detail for', pid, exc)
        time.sleep(DELAY)

    # backup and write
    bak = CSV_PATH + '.bak'
    shutil.copy2(CSV_PATH, bak)
    print('Backed up original to', bak)

    keys = list(rows[0].keys())
    with open(CSV_PATH, 'w', newline='', encoding='utf-8') as fh:
        writer = csv.DictWriter(fh, fieldnames=keys)
        writer.writeheader()
        for r in rows:
            writer.writerow(r)

    print(f'Enriched {updated} rows and wrote back to {CSV_PATH}')


if __name__ == '__main__':
    enrich()
