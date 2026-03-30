#!/usr/bin/env python3
"""Quick integration test: fetch & translate 100 products (Javoli-focused).

Usage: set your `.env` with UNAS credentials, then run:
  & ".\.venv\Scripts\Activate.ps1"
  python .\python-sync\tools\quick_javoli_test.py

This script is conservative: it only scans a single category by default
and stops after `max_items` products. It writes `data/test_javoli_100.csv`.
"""
from __future__ import annotations
import os
import sys
import csv
import time
import shutil
import tempfile
from pathlib import Path
import argparse
import requests
import logging

ROOT = Path(__file__).parents[1]
SRC = ROOT / 'src'
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from dotenv import load_dotenv
load_dotenv(ROOT / '.env')

from unas.client import UNASClient
from translate.factory import TranslationManager

OUT_DIR = ROOT / 'data'
OUT_DIR.mkdir(parents=True, exist_ok=True)
OUT_FILE = OUT_DIR / 'test_javoli_100.csv'

DEFAULT_CATEGORY = os.getenv('QUICK_TEST_CATEGORY', '758587')
DEFAULT_MAX = int(os.getenv('QUICK_TEST_MAX', '100'))
PAGE_LIMIT = int(os.getenv('QUICK_TEST_PAGE_LIMIT', '100'))
DELAY = float(os.getenv('QUICK_TEST_DELAY', '0.3'))
JAVOLI_FILTER = os.getenv('JAVOLI_FILTER', 'javoli')


def is_deleted(p):
    s = None
    if isinstance(p, dict):
        s = p.get('State') or p.get('state') or p.get('@state')
    return str(s).lower() == 'deleted' if s is not None else False


def extract_image(prod):
    imgs = prod.get('Images') or {}
    if not imgs:
        return ''
    img = imgs.get('Image')
    if isinstance(img, dict):
        url = img.get('Url')
        if isinstance(url, dict):
            return url.get('Medium') or url.get('Small') or ''
    return imgs.get('DefaultFilename') or ''


def extract_price(prod):
    price_info = prod.get('Prices') or {}
    if not price_info:
        return ('', '')
    p = price_info.get('Price')
    if isinstance(p, list):
        normal = next((x for x in p if x.get('Type') == 'normal'), p[0])
        gross = normal.get('Gross')
        net = normal.get('Net')
        return (net, gross)
    elif isinstance(p, dict):
        return (p.get('Net', ''), p.get('Gross', ''))
    return ('', '')


def extract_stock(prod):
    stocks = prod.get('Stocks') or {}
    if not stocks:
        return ''
    s = stocks.get('Stock')
    if isinstance(s, list):
        s0 = s[0]
        return s0.get('Qty') or s0.get('Quantity') or ''
    if isinstance(s, dict):
        return s.get('Qty') or s.get('Quantity') or ''
    return ''


def extract_category(prod):
    cats = prod.get('Categories') or {}
    cat = cats.get('Category') if isinstance(cats, dict) else None
    if isinstance(cat, list):
        c0 = cat[0]
        return c0.get('Name') or ''
    if isinstance(cat, dict):
        return cat.get('Name') or ''
    return ''


def extract_sell_unit(prod):
    # flexible lookup for sale/unit of measure fields
    for key in ('SellUnit', 'SellUnitName', 'Unit', 'UnitName', 'SellingUnit', 'MeasureUnit', 'SalesUnit'):
        v = prod.get(key)
        if v:
            if isinstance(v, dict):
                return v.get('Name') or v.get('Unit') or str(v)
            return str(v)
    # sometimes unit appears under Stocks or Attributes
    stocks = prod.get('Stocks') or {}
    if isinstance(stocks, dict):
        s = stocks.get('Unit') or stocks.get('UnitName')
        if s:
            return str(s)
    attrs = prod.get('Attributes') or {}
    if isinstance(attrs, dict):
        a = attrs.get('Attribute')
        if isinstance(a, list):
            for it in a:
                if (it.get('Name') or '').lower() in ('unit', 'verkoopeenheid', 'sell unit'):
                    return it.get('Value') or it.get('Name') or ''
        elif isinstance(a, dict):
            if (a.get('Name') or '').lower() in ('unit', 'verkoopeenheid', 'sell unit'):
                return a.get('Value') or a.get('Name') or ''
    return ''


def flatten(prod):
    return {
        'Id': prod.get('Id') or prod.get('@Id') or '',
        'Sku': prod.get('Sku') or prod.get('@Sku') or '',
        'Name': prod.get('Name') or '',
        'ShortDescription': (prod.get('Description') or {}).get('Short') if isinstance((prod.get('Description') or {}), dict) else '',
        'LongDescription': (prod.get('Description') or {}).get('Long') if isinstance((prod.get('Description') or {}), dict) else '',
        'PriceNet': extract_price(prod)[0],
        'PriceGross': extract_price(prod)[1],
        'Category': extract_category(prod),
        'StockQty': extract_stock(prod),
        'SellUnit': extract_sell_unit(prod),
        'Url': prod.get('Url') or prod.get('SefUrl') or '',
        'ImageUrl': extract_image(prod),
    }


def run(max_items: int = DEFAULT_MAX, page_limit: int = PAGE_LIMIT, category_id: str | None = None, delay: float = DELAY):
    client = UNASClient.from_env()
    translator = TranslationManager()

    # currency conversion support
    convert_eur = bool(int(os.getenv('QUICK_CONVERT_EUR', '0')))
    eur_rate = None
    def get_eur_rate(from_currency: str = 'HUF'):
        nonlocal eur_rate
        if eur_rate is not None:
            return eur_rate
        # 1) Try Frankfurter API (no key required)
        try:
            resp = requests.get(f'https://api.frankfurter.app/latest?from={from_currency}&to=EUR', timeout=10)
            data = resp.json()
            rate = None
            if isinstance(data, dict) and 'rates' in data:
                rate = data['rates'].get('EUR')
            if rate:
                eur_rate = float(rate)
                logging.info('Using Frankfurter rate HUF->EUR: %s', eur_rate)
                return eur_rate
        except Exception as e:
            logging.debug('Frankfurter API failed: %s', e)
        # 2) Try exchangerate.host (supports optional access key via ENV EXCHANGE_ACCESS_KEY)
        try:
            access = os.getenv('EXCHANGE_ACCESS_KEY')
            url = f'https://api.exchangerate.host/latest?base={from_currency}&symbols=EUR'
            if access:
                url += f'&access_key={access}'
            resp = requests.get(url, timeout=10)
            data = resp.json()
            rate = data.get('rates', {}).get('EUR')
            if rate:
                eur_rate = float(rate)
                logging.info('Using exchangerate.host rate HUF->EUR: %s', eur_rate)
                return eur_rate
        except Exception as e:
            logging.debug('exchangerate.host failed: %s', e)
        # 3) Fallback to env-provided static rate
        try:
            env_rate = os.getenv('QUICK_EUR_RATE')
            if env_rate:
                eur_rate = float(env_rate)
                logging.info('Using QUICK_EUR_RATE from env: %s', eur_rate)
                return eur_rate
        except Exception:
            pass
        logging.warning('Could not determine EUR conversion rate; leaving EUR columns empty')
        return None

    def convert(amount):
        try:
            if amount is None or amount == '':
                return ''
            val = float(amount)
            rate = get_eur_rate('HUF')
            if not rate:
                return ''
            return round(val * rate, 2)
        except Exception:
            return ''

    cid = category_id or DEFAULT_CATEGORY
    collected = []
    offset = 0
    while len(collected) < max_items:
        print(f'Fetching category {cid} offset {offset}')
        page = client.get_products_page(limit=page_limit, offset=offset, extra={'CategoryId': str(cid)})
        prods = []
        if isinstance(page, dict):
            if 'Products' in page and page['Products'] and 'Product' in page['Products']:
                p = page['Products']['Product']
                prods = p if isinstance(p, list) else [p]
            elif 'Product' in page:
                p = page['Product']
                prods = p if isinstance(p, list) else [p]
        if not prods:
            break
        for prod in prods:
            if is_deleted(prod):
                continue
            flat = flatten(prod)
            # simple Javoli heuristic: check image/url/description text for javoli
            hay = (flat.get('ImageUrl') or '') + ' ' + (flat.get('Name') or '') + ' ' + (flat.get('ShortDescription') or '')
            if JAVOLI_FILTER.lower() in hay.lower():
                # translate immediately to show speed
                flat['TranslatedName'] = translator.translate(flat.get('Name') or '') if flat.get('Name') else ''
                flat['TranslatedShortDescription'] = translator.translate(flat.get('ShortDescription') or '') if flat.get('ShortDescription') else ''
                flat['TranslatedLongDescription'] = translator.translate(flat.get('LongDescription') or '') if flat.get('LongDescription') else ''
                collected.append(flat)
            if len(collected) >= max_items:
                break
        offset += page_limit
        time.sleep(delay)

    if not collected:
        print('No Javoli-looking products found in category', cid)
        return 1

    keys = ['Id', 'Sku', 'Name', 'TranslatedName', 'ShortDescription', 'TranslatedShortDescription', 'LongDescription', 'TranslatedLongDescription', 'PriceNet', 'PriceGross', 'Category', 'StockQty', 'SellUnit', 'Url', 'ImageUrl']
    if convert_eur:
        # insert EUR columns immediately BEFORE ImageUrl (keep Net then Gross)
        try:
            idx = keys.index('ImageUrl')
        except ValueError:
            idx = len(keys)
        keys.insert(idx, 'PriceNetEUR')
        keys.insert(idx + 1, 'PriceGrossEUR')
    if OUT_FILE.exists():
        bak = OUT_FILE.with_suffix(OUT_FILE.suffix + '.bak')
        shutil.copy2(OUT_FILE, bak)
        print('Backed up existing CSV to', bak)

    tmp_fd, tmp_path = tempfile.mkstemp(prefix=OUT_FILE.name, dir=str(OUT_FILE.parent))
    try:
        with os.fdopen(tmp_fd, 'w', newline='', encoding='utf-8') as fh:
            # Force quoting for all fields so long URLs or commas don't break column alignment
            w = csv.DictWriter(fh, fieldnames=keys, quoting=csv.QUOTE_ALL)
            w.writeheader()
            for r in collected:
                if convert_eur:
                    r['PriceNetEUR'] = convert(r.get('PriceNet'))
                    r['PriceGrossEUR'] = convert(r.get('PriceGross'))
                row = {k: r.get(k, '') for k in keys}
                w.writerow(row)
        os.replace(tmp_path, OUT_FILE)
        print('Wrote', len(collected), 'rows to', OUT_FILE)
    finally:
        try:
            if os.path.exists(tmp_path):
                os.remove(tmp_path)
        except Exception:
            pass
    return 0


if __name__ == '__main__':
    sys.exit(run())