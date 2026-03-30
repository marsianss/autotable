#!/usr/bin/env python3
"""Fetch product details for exported product IDs and write a detailed CSV.

Reads `python-sync/data/products_export.csv` (created by export_products_table.py)
and for up to N products calls `get_product_detail(id)` and writes
`python-sync/data/products_export_detailed.csv` with richer fields.
"""
from __future__ import annotations
import os
import sys
import csv
import time
from dotenv import load_dotenv

load_dotenv(os.path.join(os.path.dirname(__file__), os.pardir, '.env'))
ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), os.pardir))
SRC = os.path.join(ROOT, 'src')
if SRC not in sys.path:
    sys.path.insert(0, SRC)

try:
    from unas.client import UNASClient
except Exception as exc:
    print('Failed importing UNASClient:', exc)
    raise

IN_FILE = os.path.join(ROOT, 'data', 'products_export.csv')
OUT_FILE = os.path.join(ROOT, 'data', 'products_export_detailed.csv')
MAX_ITEMS = 100
DELAY = float(os.getenv('UNAS_DETAIL_DELAY', '0.2'))  # seconds between requests


def read_ids(path):
    ids = []
    if not os.path.exists(path):
        print('Input CSV not found:', path)
        return ids
    with open(path, 'r', encoding='utf-8') as fh:
        reader = csv.DictReader(fh)
        for r in reader:
            # Skip deleted or empty-state rows to avoid fetching removed products
            state = r.get('state','').strip().lower()
            if state == 'deleted':
                continue
            if 'id' in r and r['id'].strip():
                ids.append(r['id'].strip())
            if len(ids) >= MAX_ITEMS:
                break
    return ids


def flatten_detail(prod: dict) -> dict:
    # pick commonly useful fields if present
    out = {
        'id': prod.get('Id',''),
        'sku': prod.get('Sku',''),
        'state': prod.get('State',''),
        'name': '',
        'short_description': '',
        'description': '',
        'price': '',
        'stock': '',
        'categories': '',
        'images': ''
    }
    # Name
    if 'Name' in prod:
        n = prod.get('Name')
        if isinstance(n, dict) and '#text' in n:
            n = n['#text']
        out['name'] = n or ''
    # Texts
    texts = prod.get('Texts') or prod.get('Description')
    if isinstance(texts, dict):
        top = texts.get('Top') or texts.get('Short') or ''
        bottom = texts.get('Bottom') or texts.get('Long') or ''
        if isinstance(top, dict) and '#text' in top:
            top = top['#text']
        if isinstance(bottom, dict) and '#text' in bottom:
            bottom = bottom['#text']
        out['short_description'] = top or ''
        out['description'] = bottom or ''
    # Price
    if 'Price' in prod:
        out['price'] = prod.get('Price')
    elif 'Prices' in prod and isinstance(prod['Prices'], dict):
        out['price'] = prod['Prices'].get('Price','')
    # Stock
    if 'Stock' in prod:
        out['stock'] = prod.get('Stock')
    # Categories
    cats = prod.get('Categories') or prod.get('CategoryIds')
    cat_list = []
    if isinstance(cats, dict):
        c = cats.get('Category') or cats.get('Ids')
        if isinstance(c, list):
            for item in c:
                if isinstance(item, dict) and 'Id' in item:
                    cat_list.append(str(item['Id']))
                else:
                    cat_list.append(str(item))
        elif isinstance(c, dict) and 'Id' in c:
            cat_list.append(str(c['Id']))
    elif isinstance(cats, list):
        for item in cats:
            if isinstance(item, dict) and 'Id' in item:
                cat_list.append(str(item['Id']))
            else:
                cat_list.append(str(item))
    out['categories'] = ','.join(cat_list)
    # Images
    imgs = prod.get('Images') or prod.get('Image')
    img_list = []
    if isinstance(imgs, dict):
        if 'Image' in imgs:
            im = imgs['Image']
            if isinstance(im, list):
                for ii in im:
                    url = ii.get('Url') if isinstance(ii, dict) else ii
                    if url:
                        img_list.append(str(url))
            elif isinstance(im, dict) and 'Url' in im:
                img_list.append(str(im.get('Url')))
    out['images'] = '|'.join(img_list)
    return out


def fetch_details():
    ids = read_ids(IN_FILE)
    if not ids:
        print('No ids to process')
        return
    client = UNASClient.from_env()
    rows = []
    for i, pid in enumerate(ids):
        if i >= MAX_ITEMS:
            break
        try:
            detail = client.get_product_detail(pid)
            # the response may be {'Products': {'Product': {...}}} or {'Product': {...}}
            prod = None
            if isinstance(detail, dict):
                if 'Products' in detail and isinstance(detail['Products'], dict) and 'Product' in detail['Products']:
                    prod = detail['Products']['Product']
                elif 'Product' in detail:
                    prod = detail['Product']
                else:
                    # maybe detail is the product directly
                    prod = detail
            if prod is None:
                print(f'No product detail found for id={pid}; response keys: {list(detail.keys()) if isinstance(detail, dict) else type(detail)}')
                continue
            if isinstance(prod, list):
                prod = prod[0]
            row = flatten_detail(prod if isinstance(prod, dict) else {})
            rows.append(row)
        except Exception as exc:
            print('Failed fetching detail for', pid, exc)
        time.sleep(DELAY)
    if not rows:
        print('No detail rows fetched')
        return
    # write CSV
    fieldnames = ['id','sku','state','name','short_description','description','price','stock','categories','images']
    with open(OUT_FILE, 'w', encoding='utf-8', newline='') as fh:
        writer = csv.DictWriter(fh, fieldnames=fieldnames)
        writer.writeheader()
        for r in rows:
            writer.writerow({k: r.get(k,'') for k in fieldnames})
    print(f'Wrote {len(rows)} detailed rows to {OUT_FILE}')
    # preview
    with open(OUT_FILE, 'r', encoding='utf-8') as fh:
        for i, line in enumerate(fh):
            print(line.rstrip())
            if i >= 20:
                break

if __name__ == '__main__':
    fetch_details()
