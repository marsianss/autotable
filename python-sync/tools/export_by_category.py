#!/usr/bin/env python3
"""Export active products from a single category quickly (to avoid timeouts).
Usage: adjust CATEGORY_ID and MAX_ITEMS below or call from CLI by editing file.
"""
import os, sys, csv, time
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'src'))
from dotenv import load_dotenv
load_dotenv(os.path.join(os.path.dirname(__file__), '..', '.env'))
from unas.client import UNASClient

CATEGORY_ID = '758587'  # discovered earlier to contain live products
MAX_ITEMS = 20
PAGE_LIMIT = 10

OUT_DIR = os.path.join(os.path.dirname(__file__), '..', 'data')
if not os.path.exists(OUT_DIR):
    os.makedirs(OUT_DIR)
OUT_FILE = os.path.join(OUT_DIR, f'active_category_{CATEGORY_ID}_export.csv')

client = UNASClient.from_env()


def is_deleted(p):
    s = None
    if isinstance(p, dict):
        s = p.get('State') or p.get('state') or p.get('@state')
    return str(s).lower() == 'deleted' if s is not None else False


def extract_price(prod):
    price_info = prod.get('Prices') or {}
    if not price_info:
        return ''
    p = price_info.get('Price')
    if isinstance(p, list):
        normal = next((x for x in p if x.get('Type') == 'normal'), p[0])
        return normal.get('Gross') or ''
    elif isinstance(p, dict):
        return p.get('Gross', '')
    return ''


def flatten(prod):
    return {
        'Id': prod.get('Id') or prod.get('@Id') or '',
        'Sku': prod.get('Sku') or prod.get('@Sku') or '',
        'State': prod.get('State') or prod.get('state') or '',
        'Name': prod.get('Name') or '',
        'PriceGross': extract_price(prod),
        'Url': prod.get('Url') or prod.get('SefUrl') or ''
    }


def run(category_id=CATEGORY_ID, max_items=MAX_ITEMS, page_limit=PAGE_LIMIT):
    collected = []
    offset = 0
    while len(collected) < max_items:
        print(f'Fetching category {category_id} offset {offset}')
        try:
            page = client.get_products_page(limit=page_limit, offset=offset, extra={'CategoryId': str(category_id)})
            prods = []
            if isinstance(page, dict):
                if 'Products' in page and page['Products'] and 'Product' in page['Products']:
                    p = page['Products']['Product']
                    prods = p if isinstance(p, list) else [p]
                elif 'Product' in page:
                    p = page['Product']
                    prods = p if isinstance(p, list) else [p]
            if not prods:
                print('  No more products on page')
                break
            for prod in prods:
                if not is_deleted(prod):
                    collected.append(flatten(prod))
                    if len(collected) >= max_items:
                        break
            offset += page_limit
            time.sleep(0.6)
        except Exception as e:
            print('Error fetching page:', e)
            time.sleep(2)
            break
    if collected:
        keys = ['Id','Sku','State','Name','PriceGross','Url']
        with open(OUT_FILE, 'w', newline='', encoding='utf-8') as f:
            w = csv.DictWriter(f, fieldnames=keys)
            w.writeheader()
            for row in collected:
                w.writerow(row)
        print('Wrote', len(collected), 'rows to', OUT_FILE)
    else:
        print('No active products found in category', category_id)

if __name__ == '__main__':
    run()
