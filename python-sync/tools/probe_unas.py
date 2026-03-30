#!/usr/bin/env python3
"""Probe likely UNAS API endpoints using the API key in .env (or passed via ENV).

Usage: python tools/probe_unas.py
"""
import os
import requests
from dotenv import load_dotenv

load_dotenv(os.path.join(os.path.dirname(__file__), os.pardir, '.env'))
API_KEY = os.getenv('UNAS_API_KEY')
if not API_KEY:
    print('No UNAS_API_KEY found in .env')
    raise SystemExit(1)

candidates = ['javoli.unasshop.com','javoli.unas.hu','javoli.hu','api.unas.eu','shop.unas.hu','javoli.unas.eu']
for host in candidates:
    if host == 'api.unas.eu':
        url = 'https://api.unas.eu/shop'
    else:
        url = f'https://{host}/api/xml/'
    xml = f"<?xml version='1.0' encoding='UTF-8'?><Login><ApiKey>{API_KEY}</ApiKey><WebshopInfo>true</WebshopInfo></Login>"
    print('='*80)
    print('Probing:', url)
    try:
        r = requests.post(url, headers={'Content-Type': 'application/xml'}, data=xml, timeout=10, verify=False)
        print('Status:', r.status_code)
        body = r.text or ''
        print('Body (first 1200 chars):')
        print(body[:1200])
    except Exception as e:
        print('Error:', e)
print('='*80)
print('Done')
