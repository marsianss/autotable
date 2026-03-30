#!/usr/bin/env python3
"""Probe possible 'active-only' filter names for get_products_page.
Tries a small set of likely parameter names and prints whether any return products.
"""
import os, sys
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'src'))
from dotenv import load_dotenv
load_dotenv(os.path.join(os.path.dirname(__file__), '..', '.env'))
from unas.client import UNASClient

candidates = [
    {'OnlyActive': '1'},
    {'ActiveOnly': '1'},
    {'Active': '1'},
    {'OnlyActive': 'true'},
    {'Active': 'true'},
    {'OnlyActive': 'yes'},
    {'OnlyActive': 'True'},
]
client = UNASClient.from_env()
for cand in candidates:
    print('Trying filter:', cand)
    try:
        resp = client.get_products_page(limit=5, offset=0, extra=cand)
        print('Response type:', type(resp))
        import json
        s = json.dumps(resp, ensure_ascii=False)
        print('Response preview:', s[:1000])
        # check for products
        found = False
        if isinstance(resp, dict):
            if 'Products' in resp and resp['Products'] and 'Product' in resp['Products']:
                print('Found Products->Product')
                found = True
            elif 'Product' in resp:
                print('Found Product key')
                found = True
        if not found:
            print('No products found with this filter')
    except Exception as e:
        print('Error with filter', cand, e)
    print('---')
print('Done')
