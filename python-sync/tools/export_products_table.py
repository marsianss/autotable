#!/usr/bin/env python3
"""Export up to N products from UNAS into a CSV table using paginated requests.

Usage:
    python python-sync\tools\export_products_table.py

Writes `python-sync/data/products_export.csv` and prints a preview.
This script uses safe pagination (Limit/Offset) to avoid full catalog exports.
"""
from __future__ import annotations
import os
import sys
import csv
import json
from dotenv import load_dotenv

load_dotenv(os.path.join(os.path.dirname(__file__), os.pardir, '.env'))

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), os.pardir))
OUT_DIR = os.path.join(ROOT, 'data')
OUT_FILE = os.path.join(OUT_DIR, 'products_export.csv')

# Import local UNAS client
sys.path.insert(0, os.path.join(ROOT, 'src'))
try:
    from unas.client import UNASClient
except Exception as exc:
    print('Failed importing UNASClient:', exc)
    raise

MAX_ITEMS = 100
PAGE_LIMIT = 25

def flatten_product(prod: dict) -> dict:
    """Flatten a product dict to a CSV-friendly row with selected fields."""
    row = {}
    # pick common top-level fields
    for key in ('Id', 'Sku', 'State'):
        v = prod.get(key)
        if isinstance(v, dict) and '#text' in v:
            v = v['#text']
        row[key.lower()] = v if v is not None else ''
    # Name: sometimes at Product.Name or Product.Texts/Name
    name = prod.get('Name') or prod.get('Title') or ''
    if isinstance(name, dict) and '#text' in name:
        name = name['#text']
    row['name'] = name or ''
    # Price fields
    price = ''
    if 'Price' in prod:
        price = prod.get('Price')
    elif 'Prices' in prod:
        p = prod.get('Prices')
        if isinstance(p, dict):
            price = p.get('Price') or ''
    row['price'] = price if price is not None else ''
    # Stock
    stock = ''
    if 'Stock' in prod:
        stock = prod.get('Stock')
    elif 'Stocks' in prod:
        s = prod.get('Stocks')
        if isinstance(s, dict):
            stock = s.get('Stock') or ''
    row['stock'] = stock if stock is not None else ''
    # Category IDs
    cat_ids = []
    cats = prod.get('Categories') or prod.get('CategoryIds') or prod.get('Category')
    if isinstance(cats, dict):
        # maybe {'Category': [{'Id': '...'}, ...]}
        if 'Category' in cats and isinstance(cats['Category'], list):
            for c in cats['Category']:
                if isinstance(c, dict) and 'Id' in c:
                    cat_ids.append(str(c['Id']))
        elif 'Id' in cats:
            cat_ids.append(str(cats['Id']))
    elif isinstance(cats, list):
        for c in cats:
            if isinstance(c, dict) and 'Id' in c:
                cat_ids.append(str(c['Id']))
            else:
                cat_ids.append(str(c))
    row['category_ids'] = ','.join(cat_ids)
    return row


def export():
    os.makedirs(OUT_DIR, exist_ok=True)
    client = UNASClient.from_env()
    items = []
    # Step 1: get categories (small/light) and extract a list of candidate category ids
    try:
        cats_resp = client.get_categories()
    except Exception as exc:
        print('Failed fetching categories:', exc)
        return

    # find all category ids in the response
    def collect_category_ids(node, out):
        if isinstance(node, dict):
            for k, v in node.items():
                if k.lower() in ('id', 'categoryid') and isinstance(v, (str, int)):
                    out.append(str(v))
                else:
                    collect_category_ids(v, out)
        elif isinstance(node, list):
            for item in node:
                collect_category_ids(item, out)

    cat_ids = []
    collect_category_ids(cats_resp, cat_ids)
    # dedupe while preserving order
    seen = set()
    cat_ids = [x for x in cat_ids if not (x in seen or seen.add(x))]

    if not cat_ids:
        print('No category ids discovered; aborting safe export')
        return

    # Step 2: iterate categories and page products filtered by category
    for cid in cat_ids:
        if len(items) >= MAX_ITEMS:
            break
        offset = 0
        while len(items) < MAX_ITEMS:
            limit = min(PAGE_LIMIT, MAX_ITEMS - len(items))
            try:
                page = client.get_products_page(limit=limit, offset=offset, extra={'CategoryId': cid})
            except Exception as exc:
                print(f'Error fetching page for CategoryId={cid} limit={limit} offset={offset}: {exc}')
                break
            # extract products from page
            products = None
            if isinstance(page, dict):
                for k in ('Products', 'products'):
                    if k in page:
                        p = page[k]
                        if isinstance(p, dict) and 'Product' in p:
                            products = p['Product']
                        elif isinstance(p, list):
                            products = p
                if products is None and 'Product' in page:
                    products = page['Product']
            if products is None:
                print(f'No products found for CategoryId={cid}; response keys: {list(page.keys()) if isinstance(page, dict) else type(page)}')
                break
            if isinstance(products, dict):
                products = [products]
            if not isinstance(products, list):
                print('Unexpected products container type:', type(products))
                break
            for p in products:
                row = flatten_product(p if isinstance(p, dict) else {})
                items.append(row)
                if len(items) >= MAX_ITEMS:
                    break
            if len(products) < limit:
                # exhausted this category
                break
            offset += limit
    if not items:
        print('No items exported')
        return
    # Write CSV
    fieldnames = ['id', 'sku', 'state', 'name', 'price', 'stock', 'category_ids']
    with open(OUT_FILE, 'w', encoding='utf-8', newline='') as fh:
        writer = csv.DictWriter(fh, fieldnames=fieldnames)
        writer.writeheader()
        for r in items:
            writer.writerow({k: r.get(k, '') for k in fieldnames})
    print(f'Exported {len(items)} items to {OUT_FILE}')
    # Print preview first 20 rows
    import itertools
    print('\nPreview (first 20 rows):')
    with open(OUT_FILE, 'r', encoding='utf-8') as fh:
        for i, line in enumerate(itertools.islice(fh, 21)):
            print(line.rstrip())

if __name__ == '__main__':
    export()
