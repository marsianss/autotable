#!/usr/bin/env python3
"""Inspect raw get_product_detail response for a single product id."""
import os, sys, csv
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'src'))
from dotenv import load_dotenv
load_dotenv(os.path.join(os.path.dirname(__file__), '..', '.env'))
try:
    from unas.client import UNASClient
except Exception as e:
    print('Failed import:', e)
    raise
IN_FILE = os.path.join(os.path.dirname(__file__), '..', 'data', 'products_export.csv')
if not os.path.exists(IN_FILE):
    print('No input CSV found at', IN_FILE)
    sys.exit(1)
with open(IN_FILE, 'r', encoding='utf-8') as fh:
    reader = csv.DictReader(fh)
    first = None
    for r in reader:
        if r.get('id'):
            first = r.get('id')
            break
if not first:
    print('No id found in CSV')
    sys.exit(1)
print('Inspecting id', first)
client = UNASClient.from_env()
detail = client.get_product_detail(first)
import json
print('Raw detail type:', type(detail))
try:
    print(json.dumps(detail, indent=2, ensure_ascii=False)[:5000])
except Exception:
    print(repr(detail))
with open(os.path.join(os.path.dirname(__file__), '..', 'data', 'product_detail_debug.json'), 'w', encoding='utf-8') as fh:
    try:
        json.dump(detail, fh, ensure_ascii=False, indent=2)
        print('Wrote debug to product_detail_debug.json')
    except Exception:
        fh.write(str(detail))
        print('Wrote debug as str')
