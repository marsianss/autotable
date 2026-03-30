#!/usr/bin/env python3
"""Scan categories and probe a small page for active (non-deleted) products.
Collect up to `target` active product ids for a detail-export attempt.
"""
import os, sys, time
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'src'))
from dotenv import load_dotenv
load_dotenv(os.path.join(os.path.dirname(__file__), '..', '.env'))
from unas.client import UNASClient

client = UNASClient.from_env()

def is_deleted(p):
    # Guessing structure: Product may be dict with 'State' or 'state'
    s = None
    if isinstance(p, dict):
        s = p.get('State') or p.get('state') or p.get('@state')
    return str(s).lower() == 'deleted' if s is not None else False


def find_active(target=10):
    cats = client.get_categories()
    found = []
    print('Categories fetched, scanning...')
    # categories structure may be {'Categories': {'Category': [...]}}
    cat_list = []
    if isinstance(cats, dict):
        if 'Categories' in cats and cats['Categories']:
            c = cats['Categories']
            if isinstance(c, dict) and 'Category' in c:
                cat_list = c['Category'] if isinstance(c['Category'], list) else [c['Category']]
        elif 'Category' in cats:
            cat_list = cats['Category'] if isinstance(cats['Category'], list) else [cats['Category']]
    # Fallback: if cats is list
    if isinstance(cats, list):
        cat_list = cats
    for cat in cat_list:
        cid = cat.get('Id') if isinstance(cat, dict) else cat
        print('Checking category', cid)
        try:
            page = client.get_products_page(limit=5, offset=0, extra={'CategoryId': str(cid)})
            # inspect
            prods = []
            if isinstance(page, dict):
                if 'Products' in page and page['Products'] and 'Product' in page['Products']:
                    p = page['Products']['Product']
                    prods = p if isinstance(p, list) else [p]
                elif 'Product' in page:
                    p = page['Product']
                    prods = p if isinstance(p, list) else [p]
            if not prods:
                print('  no products on page')
            else:
                for prod in prods:
                    if not is_deleted(prod):
                        print('  Found active product sample in category', cid, '->', prod.get('Id') or prod.get('@Id') or prod.get('Id'))
                        found.append(prod)
                        if len(found) >= target:
                            return found
            time.sleep(1)
        except Exception as e:
            print('  error probing category', cid, e)
            # back off on api limit errors
            time.sleep(5)
    return found

if __name__ == '__main__':
    res = find_active(5)
    print('Done; active samples found:', len(res))
    import json
    print(json.dumps(res, ensure_ascii=False, indent=2)[:4000])
