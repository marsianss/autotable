#!/usr/bin/env python3
"""Quick diagnostic for WooCommerce REST API access.

Prints HTTP status, sample count and one product sample. Tries query-param auth
and falls back to HTTP Basic auth if consumer credentials are present.
"""
import os, sys, requests
from dotenv import load_dotenv
load_dotenv(os.path.join(os.path.dirname(__file__), '..', '.env'))

WP_BASE = os.getenv('WP_BASE_URL')
WP_CK = os.getenv('WP_CONSUMER_KEY')
WP_CS = os.getenv('WP_CONSUMER_SECRET')

if not WP_BASE:
    print('WP_BASE_URL not set in .env')
    sys.exit(1)

API = WP_BASE.rstrip('/') + '/wp-json/wc/v3/products'

def try_request(params=None, auth=None):
    try:
        r = requests.get(API, params=params, auth=auth, timeout=20)
        return r
    except Exception as e:
        print('Request failed:', e)
        return None

print('Testing WooCommerce API at', API)

# First try: query params (consumer key/secret)
params = {'per_page': 5, 'page': 1}
if WP_CK and WP_CS:
    params['consumer_key'] = WP_CK
    params['consumer_secret'] = WP_CS

resp = try_request(params=params)
if resp is None:
    sys.exit(2)

print('Status:', resp.status_code)
ct = resp.headers.get('Content-Type','')
print('Content-Type:', ct)
if resp.status_code == 200:
    try:
        data = resp.json()
        if isinstance(data, list):
            print('Products returned:', len(data))
            if data:
                sample = data[0]
                print('Sample keys:', list(sample.keys()))
                print('Sample sku:', sample.get('sku'))
        else:
            print('Response is not a list; sample:', type(data))
    except Exception as e:
        print('Failed parsing JSON:', e)
else:
    print('First attempt failed. Status', resp.status_code)
    # try Basic Auth if creds present
    if WP_CK and WP_CS:
        print('Trying HTTP Basic auth fallback')
        resp2 = try_request(params={'per_page':5,'page':1}, auth=(WP_CK, WP_CS))
        if resp2:
            print('Fallback status:', resp2.status_code)
            try:
                d2 = resp2.json()
                print('Fallback returned type:', type(d2))
            except Exception as e:
                print('Fallback JSON parse failed:', e)
        else:
            print('Fallback request failed')
