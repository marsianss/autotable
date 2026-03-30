#!/usr/bin/env python3
"""Complete sync pipeline:
1) Export up to `max_items` active UNAS products (category-scoped)
2) Cache WooCommerce products via REST API
3) Match exported SKUs with cached WP products and update CSV in-place

Usage: adjust CATEGORY_ID and MAX_ITEMS below or run as script and it will use defaults.
"""
import os, sys, time, csv, json, shutil, re
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'src'))
from dotenv import load_dotenv
load_dotenv(os.path.join(os.path.dirname(__file__), '..', '.env'))
from unas.client import UNASClient
import requests
from translate.factory import TranslationManager

# Config
CATEGORY_ID = os.getenv('SYNC_CATEGORY_ID', '758587')
MAX_ITEMS = int(os.getenv('SYNC_MAX_ITEMS', '300'))
PAGE_LIMIT = int(os.getenv('SYNC_PAGE_LIMIT', '30'))
OUT_DIR = os.path.join(os.path.dirname(__file__), '..', 'data')
if not os.path.exists(OUT_DIR):
    os.makedirs(OUT_DIR)
OUT_CSV = os.path.join(OUT_DIR, 'active_products_export.csv')
CACHE_JSON = os.path.join(OUT_DIR, 'wp_products_cache.json')

# WP creds
WP_BASE = os.getenv('WP_BASE_URL')
def run_pipeline(category_id: str = None, max_items: int = None, page_limit: int = None,
                 out_csv: str = None, cache_json: str = None, wp_base: str = None,
                 wp_ck: str = None, wp_cs: str = None, translate: bool = True):
    """Run the pipeline programmatically and return a result dict.

    This function mirrors the previous script behavior but returns status
    instead of exiting the process so it is safe to call from a web server.
    """
    CATEGORY = category_id or CATEGORY_ID
    MAX = max_items or MAX_ITEMS
    PLIMIT = page_limit or PAGE_LIMIT
    OUT_CSV_LOCAL = out_csv or OUT_CSV
    CACHE_JSON_LOCAL = cache_json or CACHE_JSON
    WP_BASE_LOCAL = wp_base or WP_BASE
    WP_CK_LOCAL = wp_ck or WP_CK
    WP_CS_LOCAL = wp_cs or WP_CS

    client = UNASClient.from_env()
    # 1) Export UNAS products (category-scoped)
    collected = []
    offset = 0
    while len(collected) < MAX:
        try:
            page = client.get_products_page(limit=PLIMIT, offset=offset, extra={'CategoryId': str(CATEGORY)})
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
                state = (prod.get('State') or prod.get('state') or '').lower()
                if state == 'deleted':
                    continue
                row = {
                    'Id': prod.get('Id') or prod.get('@Id') or '',
                    'Sku': prod.get('Sku') or prod.get('@Sku') or '',
                    'State': prod.get('State') or prod.get('state') or '',
                    'Name': prod.get('Name') or '',
                    'PriceGross': (prod.get('Prices') or {}).get('Price', {}) if prod.get('Prices') else '' ,
                    'Url': prod.get('Url') or prod.get('SefUrl') or ''
                }
                collected.append(row)
                if len(collected) >= MAX:
                    break
            offset += PLIMIT
            time.sleep(0.4)
        except Exception:
            time.sleep(1)
            break

    if not collected:
        return {'ok': False, 'message': 'No products collected'}

    # write CSV (backup existing)
    if os.path.exists(OUT_CSV_LOCAL):
        bak = OUT_CSV_LOCAL + '.bak'
        shutil.copy2(OUT_CSV_LOCAL, bak)
    keys = ['Id','Sku','State','Name','PriceGross','Url']
    with open(OUT_CSV_LOCAL, 'w', newline='', encoding='utf-8') as f:
        w = csv.DictWriter(f, fieldnames=keys)
        w.writeheader()
        for r in collected:
            w.writerow(r)

    # 2) Cache WooCommerce products (if WP_BASE provided)
    cache = {}
    if WP_BASE_LOCAL:
        API = WP_BASE_LOCAL.rstrip('/') + '/wp-json/wc/v3/products'
        session = requests.Session()
        per_page = 100
        page = 1
        while True:
            params = {'per_page': per_page, 'page': page}
            if WP_CK_LOCAL and WP_CS_LOCAL:
                params['consumer_key'] = WP_CK_LOCAL
                params['consumer_secret'] = WP_CS_LOCAL
            try:
                resp = session.get(API, params=params, timeout=20)
                resp.raise_for_status()
                data = resp.json()
                if not isinstance(data, list) or len(data) == 0:
                    break
                for p in data:
                    sku = p.get('sku')
                    if sku:
                        cache[sku] = p
                if len(data) < per_page:
                    break
                page += 1
                time.sleep(0.3)
            except Exception:
                break
        with open(CACHE_JSON_LOCAL, 'w', encoding='utf-8') as f:
            json.dump(cache, f, ensure_ascii=False)

    # 3) Match SKUs using cache
    rows = []
    with open(OUT_CSV_LOCAL, newline='', encoding='utf-8') as f:
        rows = list(csv.DictReader(f))
    extra_cols = ['Matched','WP_Id','WP_Status','WP_Price','WP_Stock','MatchMethod']
    for r in rows:
        for c in extra_cols:
            if c not in r:
                r[c] = ''

    matches = 0
    if cache:
        def norm_key(s):
            if s is None:
                return ('','')
            s_up = str(s).upper().strip()
            al = re.sub(r'[^A-Z0-9]', '', s_up)
            return (s_up, al)

        norm_map = {}
        for sku, prod in cache.items():
            up, al = norm_key(sku)
            if up and up not in norm_map:
                norm_map[up] = prod
            if al and al not in norm_map:
                norm_map[al] = prod

        for r in rows:
            sku = r.get('Sku')
            if not sku:
                continue
            found = None
            method = ''
            if sku in cache:
                found = cache[sku]; method='exact'
            else:
                up, al = norm_key(sku)
                if up in norm_map:
                    found = norm_map[up]; method='norm_upper'
                elif al in norm_map:
                    found = norm_map[al]; method='norm_alnum'
                else:
                    for csku, prod in cache.items():
                        if sku in csku or csku in sku:
                            found = prod; method='substring'; break
            if found:
                r['Matched'] = 'yes'
                r['WP_Id'] = str(found.get('id',''))
                r['WP_Status'] = found.get('status','')
                r['WP_Price'] = found.get('price','')
                r['WP_Stock'] = str(found.get('stock_quantity',''))
                r['MatchMethod'] = method
                matches += 1
            else:
                r['Matched'] = 'no'

    # 4) Translate selected fields using TranslationManager (if requested)
    if translate:
        try:
            translator = TranslationManager()
        except Exception:
            translator = None
        for r in rows:
            name = r.get('Name') or r.get('name') or ''
            if name and translator:
                try:
                    r['TranslatedName'] = translator.translate(name)
                except Exception:
                    r['TranslatedName'] = name
            else:
                r['TranslatedName'] = ''

    # write back
    keys = list(rows[0].keys()) if rows else ['Id','Sku','Name']
    with open(OUT_CSV_LOCAL, 'w', newline='', encoding='utf-8') as f:
        w = csv.DictWriter(f, fieldnames=keys)
        w.writeheader()
        for r in rows:
            w.writerow(r)

    return {'ok': True, 'products_exported': len(collected), 'wp_cached': len(cache), 'matches': matches, 'csv': OUT_CSV_LOCAL, 'cache': CACHE_JSON_LOCAL}
    w.writeheader()
    for r in rows:
        w.writerow(r)

print('\nPipeline complete. Final CSV:', OUT_CSV)
