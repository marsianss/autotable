#!/usr/bin/env python3
"""Single-shot probe for UNAS getProduct endpoint to inspect response behavior."""
import os
import sys
import requests
from dotenv import load_dotenv

load_dotenv(os.path.join(os.path.dirname(__file__), os.pardir, '.env'))
BASE = os.getenv('UNAS_API_BASE')
API_KEY = os.getenv('UNAS_API_KEY')
LOGIN_EP = os.getenv('UNAS_LOGIN_ENDPOINT', 'login')
PRODUCT_EP = os.getenv('UNAS_PRODUCTS_ENDPOINT', 'getProduct')
TOKEN_FIELD = os.getenv('UNAS_TOKEN_FIELD', 'Token')
TIMEOUT = int(os.getenv('UNAS_TIMEOUT', '60'))

if not BASE or not API_KEY:
    print('UNAS_API_BASE or UNAS_API_KEY missing in .env')
    sys.exit(1)

login_xml = f"<?xml version='1.0' encoding='UTF-8'?><Params><ApiKey>{API_KEY}</ApiKey><WebshopInfo>true</WebshopInfo></Params>"
login_url = f"{BASE.rstrip('/')}/{LOGIN_EP.lstrip('/')}"
print('Login URL:', login_url)
try:
    r = requests.post(login_url, headers={'Content-Type': 'application/xml', 'Accept':'application/xml'}, data=login_xml, timeout=10)
    print('Login status:', r.status_code)
    print('Login elapsed:', r.elapsed)
    body = r.text
    print('Login body starts:', body[:400])
    # attempt to extract token
    import xml.etree.ElementTree as ET
    try:
        root = ET.fromstring(r.content)
        token_el = root.find('.//'+TOKEN_FIELD)
        token = token_el.text if token_el is not None else None
        print('Token:', token)
    except Exception as e:
        print('Login parse error:', e)
except Exception as e:
    print('Login request failed:', type(e).__name__, e)
    sys.exit(1)

# Build minimal getProduct XML body
prod_xml = "<?xml version='1.0' encoding='UTF-8'?><Params><Action>GetProducts</Action></Params>"
prod_url = f"{BASE.rstrip('/')}/{PRODUCT_EP.lstrip('/')}"
headers = {'Content-Type': 'application/xml', 'Accept': 'application/xml'}
if token:
    headers[os.getenv('UNAS_AUTH_HEADER_NAME','Authorization')] = f"{os.getenv('UNAS_AUTH_HEADER_PREFIX','')}{token}"

print('\nProbing getProduct URL:', prod_url)
print('Headers:', headers)

# Single shot, no redirects, short timeout to observe immediate response or redirect
try:
    r2 = requests.post(prod_url, headers=headers, data=prod_xml, timeout=15, allow_redirects=False)
    print('getProduct status:', r2.status_code)
    print('getProduct elapsed:', r2.elapsed)
    print('getProduct headers:', dict(r2.headers))
    text = r2.text or ''
    print('getProduct body start (first 2000 chars):')
    print(text[:2000])
except Exception as e:
    print('getProduct request failed:', type(e).__name__, e)
    # try streaming to see if server starts sending
    try:
        with requests.post(prod_url, headers=headers, data=prod_xml, timeout=15, stream=True, allow_redirects=False) as s:
            print('streaming status:', s.status_code)
            print('streaming headers:', dict(s.headers))
            chunk = s.raw.read(1024)
            print('first raw 1024 bytes:', chunk[:1024])
    except Exception as e2:
        print('stream attempt failed:', type(e2).__name__, e2)

print('\nDone')
