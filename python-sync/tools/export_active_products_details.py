#!/usr/bin/env python3
"""Export up to N active products by scanning categories and pages.
This uses the product objects returned by `get_products_page` (less load than per-id detail).
"""
import os, sys, csv, time
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'src'))
from dotenv import load_dotenv
load_dotenv(os.path.join(os.path.dirname(__file__), '..', '.env'))
from unas.client import UNASClient

OUT_DIR = os.path.join(os.path.dirname(__file__), '..', 'data')
if not os.path.exists(OUT_DIR):
    os.makedirs(OUT_DIR)
OUT_FILE = os.path.join(OUT_DIR, 'active_products_export.csv')

client = UNASClient.from_env()


def is_deleted(p):
    s = None
    if isinstance(p, dict):
        s = p.get('State') or p.get('state') or p.get('@state')
    return str(s).lower() == 'deleted' if s is not None else False


def extract_price(prod):
    price_info = prod.get('Prices') or {}
    if not price_info:
        return ('', '')
    p = price_info.get('Price')
    if isinstance(p, list):
        # find 'normal' or 'actual'
        normal = next((x for x in p if x.get('Type') == 'normal'), p[0])
        gross = normal.get('Gross')
        net = normal.get('Net')
        return (net, gross)
    elif isinstance(p, dict):
        return (p.get('Net', ''), p.get('Gross', ''))
    return ('', '')


def extract_short(prod):
    d = prod.get('Description') or {}
    short = d.get('Short') if isinstance(d, dict) else ''
    return short or ''


def extract_long(prod):
    d = prod.get('Description') or {}
    long = d.get('Long') if isinstance(d, dict) else ''
    return long or ''


def extract_image(prod):
    imgs = prod.get('Images') or {}
    if not imgs:
        return ''
    img = imgs.get('Image')
    if isinstance(img, dict):
        url = img.get('Url')
        if isinstance(url, dict):
            return url.get('Medium') or url.get('Small') or ''
    # fallback default
    return imgs.get('DefaultFilename') or ''


def flatten(prod):
    return {
        'Id': prod.get('Id') or prod.get('@Id') or '',
        'Sku': prod.get('Sku') or prod.get('@Sku') or '',
        'State': prod.get('State') or prod.get('state') or '',
        'Name': prod.get('Name') or '',
        'ShortDescription': extract_short(prod),
        'LongDescription': extract_long(prod),
        'PriceNet': extract_price(prod)[0],
        'PriceGross': extract_price(prod)[1],
        'Category': (prod.get('Categories') or {}).get('Category', {}).get('Name') if isinstance((prod.get('Categories') or {}).get('Category'), dict) else '',
        'Url': prod.get('Url') or prod.get('SefUrl') or '',
        'ImageUrl': extract_image(prod),
        'StockQty': (prod.get('Stocks') or {}).get('Stock', {}).get('Qty') if isinstance((prod.get('Stocks') or {}).get('Stock'), dict) else ''
    }


def run(max_items=100, page_limit=20):
    cats = client.get_categories()
    cat_list = []
    if isinstance(cats, dict):
        if 'Categories' in cats and cats['Categories']:
            c = cats['Categories']
            if isinstance(c, dict) and 'Category' in c:
                cat_list = c['Category'] if isinstance(c['Category'], list) else [c['Category']]
        elif 'Category' in cats:
            cat_list = cats['Category'] if isinstance(cats['Category'], list) else [cats['Category']]
    if isinstance(cats, list):
        cat_list = cats

    collected = []
    for cat in cat_list:
        cid = cat.get('Id') if isinstance(cat, dict) else cat
        offset = 0
        while len(collected) < max_items:
            try:
                print(f'Paging category {cid} offset {offset}')
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
                    if not is_deleted(prod):
                        collected.append(flatten(prod))
                        if len(collected) >= max_items:
                            break
                offset += page_limit
                time.sleep(0.6)
            except Exception as e:
                print('Error paging category', cid, e)
                time.sleep(3)
                break
        if len(collected) >= max_items:
            break
    # write csv
    if collected:
        keys = ['Id','Sku','State','Name','ShortDescription','LongDescription','PriceNet','PriceGross','Category','Url','ImageUrl','StockQty']
        with open(OUT_FILE, 'w', newline='', encoding='utf-8') as f:
            w = csv.DictWriter(f, fieldnames=keys)
            w.writeheader()
            for row in collected:
                w.writerow(row)
        print('Wrote', len(collected), 'rows to', OUT_FILE)
    else:
        print('No active products found')

if __name__ == '__main__':
    run(100, 30)
