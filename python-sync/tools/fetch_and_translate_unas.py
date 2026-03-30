#!/usr/bin/env python3
"""Fetch products from UNAS and translate name & descriptions into CSV.
Writes `python-sync/data/active_products_export.csv` with translated fields.
"""
from __future__ import annotations
import os, sys, csv, time, shutil
from pathlib import Path

ROOT = Path(__file__).parents[1]
SRC = ROOT / 'src'
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from dotenv import load_dotenv
load_dotenv(ROOT / '.env')

from unas.client import UNASClient, UNASError
from translate.factory import TranslationManager
import json
import signal
import threading
import random
from datetime import datetime
import requests
import argparse
from loguru import logger
import tempfile
import math
import hashlib
from tqdm import tqdm

OUT_DIR = ROOT / 'data'
OUT_DIR.mkdir(parents=True, exist_ok=True)
OUT_FILE = OUT_DIR / 'active_products_export.csv'
PROGRESS_FILE = OUT_DIR / 'progress.json'

# Graceful shutdown flag + lock for progress file
STOP_REQUESTED = False
progress_lock = threading.Lock()

client = UNASClient.from_env()
translator = TranslationManager()

DEFAULT_MAX = int(os.getenv('UNAS_EXPORT_MAX', '500'))
PAGE_LIMIT = int(os.getenv('UNAS_PAGE_LIMIT', '50'))
DELAY = float(os.getenv('UNAS_PAGE_DELAY', '0.5'))
MAX_EMPTY_PAGES = int(os.getenv('UNAS_MAX_EMPTY_PAGES', '10'))  # consecutive pages with zero kept products before skipping category
MIN_YIELD_PAGES = int(os.getenv('UNAS_MIN_YIELD_PAGES', '20'))  # evaluate yield after this many pages
MIN_KEEP_RATIO = float(os.getenv('UNAS_MIN_KEEP_RATIO', '0.01'))  # minimum kept/page_limit ratio before skipping category
ALLOWED_STATES = {s.strip().lower() for s in os.getenv('UNAS_ALLOWED_STATES', 'live').split(',') if s.strip()}
MIN_STOCK_QTY = os.getenv('UNAS_MIN_STOCK_QTY')
if MIN_STOCK_QTY is not None:
    try:
        MIN_STOCK_QTY = float(MIN_STOCK_QTY)
    except Exception:
        MIN_STOCK_QTY = None


def is_deleted(p):
    s = None
    if isinstance(p, dict):
        s = p.get('State') or p.get('state') or p.get('@state')
    return str(s).lower() == 'deleted' if s is not None else False


def is_inactive(p):
    """Return True if product should be skipped based on state/stock filters."""
    if is_deleted(p):
        return True
    state = str((p.get('State') or p.get('state') or p.get('@state') or '')).lower()
    if ALLOWED_STATES and state and state not in ALLOWED_STATES:
        return True
    if MIN_STOCK_QTY is not None:
        try:
            qty = (p.get('Stocks') or {}).get('Stock', {}).get('Qty') if isinstance((p.get('Stocks') or {}).get('Stock'), dict) else None
            if qty is not None and float(qty) < MIN_STOCK_QTY:
                return True
        except Exception:
            pass
    return False


def compute_hash(row):
    """Compute hash of translatable fields to detect changes."""
    content = f"{row.get('Name')}|{row.get('ShortDescription')}|{row.get('LongDescription')}|{row.get('Category')}"
    return hashlib.md5(content.encode('utf-8')).hexdigest()


def extract_price(prod):
    price_info = prod.get('Prices') or {}
    if not price_info:
        return ('', '')
    p = price_info.get('Price')
    if isinstance(p, list):
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
    return imgs.get('DefaultFilename') or ''


def flatten(prod):
    return {
        'Id': prod.get('Id') or prod.get('@Id') or '',
        'Sku': prod.get('Sku') or prod.get('@Sku') or '',
        'EAN': prod.get('Ean') or prod.get('Barcode') or '',
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


def _safe_get_products_page(cid, offset, limit, retries=2, backoff=1.0):
    """Fetch a page; on auth error try to re-login once then retry."""
    attempt = 0
    last_exc = None
    while attempt <= retries:
        try:
            return client.get_products_page(limit=limit, offset=offset, extra={'CategoryId': str(cid)})
        except UNASError as ue:
            logger.warning(f'UNAS error while fetching page (attempt {attempt + 1}): {ue}')
            last_exc = ue
            if 'expired token' in str(ue).lower():
                client.token = None  # force fresh login
            # Try re-login and retry a limited number of times
            try:
                logger.info('Attempting re-login due to UNAS error')
                client._ensure_token()
            except Exception as e:
                logger.error(f'Re-login failed: {e}')
                # fall through to backoff/retry
            attempt += 1
        except Exception as exc:
            logger.warning(f'Network/other error fetching page (attempt {attempt + 1}): {exc}')
            last_exc = exc
            attempt += 1

        if attempt <= retries:
            # exponential backoff with jitter
            sleep = backoff * (2 ** (attempt - 1)) if attempt > 0 else backoff
            sleep = sleep * (0.8 + random.random() * 0.4)
            logger.debug(f'Sleeping {sleep:.2f}s before retrying')
            time.sleep(sleep)
            continue
        if last_exc:
            raise last_exc
        raise UNASError('UNAS paging failed')


def _get_categories_safe(retries=2, backoff=1.0):
    """Fetch categories with auto re-login and retry to recover from token expiry."""
    attempt = 0
    last_exc = None
    while attempt <= retries:
        try:
            client._ensure_token()
        except Exception as e:
            logger.warning(f'Could not ensure token before categories: {e}')
            client.token = None
        try:
            return client.get_categories()
        except UNASError as ue:
            last_exc = ue
            if 'expired token' in str(ue).lower():
                client.token = None
            logger.warning(f'UNAS error while fetching categories (attempt {attempt + 1}): {ue}')
        except Exception as exc:
            last_exc = exc
            logger.warning(f'Network/other error fetching categories (attempt {attempt + 1}): {exc}')

        attempt += 1
        if attempt <= retries:
            sleep = backoff * (2 ** (attempt - 1))
            sleep = sleep * (0.8 + random.random() * 0.4)
            logger.debug(f'Sleeping {sleep:.2f}s before retrying categories')
            time.sleep(sleep)
            continue
        break
    if last_exc:
        raise last_exc
    raise UNASError('Failed to fetch categories')


def load_progress() -> dict:
    try:
        if PROGRESS_FILE.exists():
            with PROGRESS_FILE.open('r', encoding='utf-8') as fh:
                return json.load(fh)
    except Exception as e:
        logger.warning(f'Could not read progress file: {e}')
    return {}


def save_progress(progress: dict):
    try:
        with progress_lock:
            tmp = str(PROGRESS_FILE) + '.tmp'
            with open(tmp, 'w', encoding='utf-8') as fh:
                json.dump(progress, fh, ensure_ascii=False, indent=2)
            os.replace(tmp, PROGRESS_FILE)
    except Exception as e:
        logger.warning(f'Could not write progress file: {e}')


def _request_stop(signum, frame):
    global STOP_REQUESTED
    logger.info(f'Stop requested (signal {signum}) — will finish current page and persist progress')
    STOP_REQUESTED = True


def _extract_products_from_detail(detail):
    """Extract product dict(s) from a GetProduct response."""
    if not isinstance(detail, dict):
        return []
    if 'Product' in detail:
        p = detail['Product']
        return p if isinstance(p, list) else [p]
    if 'Products' in detail and detail['Products']:
        p = detail['Products']
        if isinstance(p, dict) and 'Product' in p:
            prod = p['Product']
            return prod if isinstance(prod, list) else [prod]
        return p if isinstance(p, list) else []
    return []


def run(max_items: int = DEFAULT_MAX, page_limit: int = PAGE_LIMIT, category_id: str | None = None, delay: float = float(DELAY), resume: bool = False, no_translate: bool = False, product_id: str | None = None):
    logger.info(f'Starting UNAS fetch+translate: max_items={max_items} page_limit={page_limit} product_id={product_id}')
    # install signal handlers for graceful shutdown
    signal.signal(signal.SIGINT, _request_stop)
    try:
        signal.signal(signal.SIGTERM, _request_stop)
    except Exception:
        # SIGTERM not available on Windows in some contexts
        pass

    # Fast path: fetch a single product directly by Id to avoid paging thousands of items
    if product_id:
        try:
            detail = client.get_product_detail(product_id)
            prods = _extract_products_from_detail(detail)
            if not prods:
                logger.warning(f'No product found for Id {product_id}')
                return
            collected = [flatten(prods[0])]
        except Exception as exc:  # noqa: BLE001
            logger.error(f'Failed fetching product {product_id}: {exc}')
            return

        # Translate or skip
        if not no_translate:
            logger.info('Translating single product...')
            row = collected[0]
            try:
                row['TranslatedName'] = translator.translate(row.get('Name', '')) if row.get('Name') else ''
                row['TranslatedShortDescription'] = translator.translate(row.get('ShortDescription', '')) if row.get('ShortDescription') else ''
                row['TranslatedLongDescription'] = translator.translate(row.get('LongDescription', '')) if row.get('LongDescription') else ''
                row['TranslatedCategory'] = translator.translate(row.get('Category', '')) if row.get('Category') else ''
            except Exception as exc:  # noqa: BLE001
                logger.warning(f'Translation error for {product_id}: {exc}')
            translator.save()

        # Write CSV atomically (single row)
        keys = ['Id', 'Sku', 'EAN', 'State', 'Name', 'TranslatedName', 'ShortDescription', 'TranslatedShortDescription', 'LongDescription', 'TranslatedLongDescription', 'PriceNet', 'PriceGross', 'Category', 'TranslatedCategory', 'Url', 'ImageUrl', 'StockQty']
        convert_eur = bool(int(os.getenv('QUICK_CONVERT_EUR', '0')))
        if convert_eur:
            idx = keys.index('ImageUrl') if 'ImageUrl' in keys else len(keys)
            keys.insert(idx, 'PriceNetEUR')
            keys.insert(idx + 1, 'PriceGrossEUR')

        if OUT_FILE.exists():
            bak = OUT_FILE.with_suffix(OUT_FILE.suffix + '.bak')
            shutil.copy2(OUT_FILE, bak)
            logger.info(f'Backed up existing CSV to {bak}')

        def convert(amount):
            try:
                if amount is None or amount == '':
                    return ''
                v = float(amount)
                env_rate = os.getenv('QUICK_EUR_RATE')
                rate = float(env_rate) if env_rate else None
                return round(v * rate, 2) if rate else ''
            except Exception:
                return ''

        tmp_fd, tmp_path = tempfile.mkstemp(prefix=OUT_FILE.name, dir=str(OUT_FILE.parent))
        try:
            with os.fdopen(tmp_fd, 'w', newline='', encoding='utf-8') as fh:
                writer = csv.DictWriter(fh, fieldnames=keys, quoting=csv.QUOTE_ALL)
                writer.writeheader()
                row = collected[0]
                if convert_eur:
                    row['PriceNetEUR'] = convert(row.get('PriceNet'))
                    row['PriceGrossEUR'] = convert(row.get('PriceGross'))
                writer.writerow({k: row.get(k, '') for k in keys})
            os.replace(tmp_path, OUT_FILE)
            logger.info(f'Wrote 1 row to {OUT_FILE}')
        finally:
            try:
                if os.path.exists(tmp_path):
                    os.remove(tmp_path)
            except Exception:
                pass
        return
    cats = _get_categories_safe()
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

    # Load existing data for Delta Sync
    existing_data = {}
    if OUT_FILE.exists():
        try:
            with open(OUT_FILE, 'r', encoding='utf-8') as fh:
                reader = csv.DictReader(fh)
                for r in reader:
                    if r.get('Id'):
                        existing_data[r['Id']] = r
            logger.info(f"Loaded {len(existing_data)} existing products for Delta Sync")
        except Exception as e:
            logger.warning(f"Failed to load existing CSV: {e}")

    collected = []
    progress = load_progress() if resume else {}
    if 'categories' not in progress:
        progress.setdefault('categories', {})
    progress.setdefault('fetched', 0)
    # If a specific category_id is requested, filter categories
    if category_id:
        cat_list = [c for c in cat_list if (c.get('Id') if isinstance(c, dict) else c) == str(category_id)]
    for cat in cat_list:
        cid = cat.get('Id') if isinstance(cat, dict) else cat
        # ensure we have a fresh token before paging this category
        try:
            client._ensure_token()
        except Exception as e:
            logger.warning(f'Could not refresh token before category {cid}: {e}')
        
        # resume offset if requested
        offset = int(progress.get('categories', {}).get(str(cid), 0)) if resume else 0
        cat_kept = 0
        cat_pages = 0
        empty_pages = 0
        while len(collected) < max_items:
            if STOP_REQUESTED:
                logger.info(f'Stop requested; breaking out of paging loop for category {cid}')
                break
            try:
                logger.info(f'Paging category {cid} offset {offset}')
                page = _safe_get_products_page(cid, offset, page_limit)
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
                kept_this_page = 0
                for prod in prods:
                    if not is_inactive(prod):
                        # avoid duplicating already persisted items when resuming
                        fid = str(prod.get('Id') or prod.get('@Id') or '')
                        # naive de-duplication: ignore if we've already fetched this ID in this run
                        if any(str(x.get('Id')) == fid for x in collected):
                            continue
                        
                        flat = flatten(prod)
                        current_hash = compute_hash(flat)
                        flat['Hash'] = current_hash
                        
                        # Delta Sync Check
                        if fid in existing_data:
                            old = existing_data[fid]
                            if old.get('Hash') == current_hash:
                                # Content unchanged, copy translations
                                flat['TranslatedName'] = old.get('TranslatedName', '')
                                flat['TranslatedShortDescription'] = old.get('TranslatedShortDescription', '')
                                flat['TranslatedLongDescription'] = old.get('TranslatedLongDescription', '')
                                flat['TranslatedCategory'] = old.get('TranslatedCategory', '')
                                flat['_skip_translation'] = True
                        
                        collected.append(flat)
                        progress['fetched'] = progress.get('fetched', 0) + 1
                        kept_this_page += 1
                        if len(collected) >= max_items:
                            break
                cat_pages += 1
                cat_kept += kept_this_page
                if kept_this_page == 0:
                    empty_pages += 1
                    if empty_pages >= MAX_EMPTY_PAGES:
                        logger.info(f'Skipping category {cid} after {empty_pages} empty pages (no live/unique products kept)')
                        break
                else:
                    empty_pages = 0

                if cat_pages >= MIN_YIELD_PAGES:
                    # keep rate vs theoretical maximum page_limit
                    keep_ratio = (cat_kept / (cat_pages * page_limit)) if page_limit else 0
                    if keep_ratio < MIN_KEEP_RATIO:
                        logger.info(f'Skipping category {cid} after {cat_pages} pages due to low yield (kept {cat_kept}, ratio {keep_ratio:.4f}, threshold {MIN_KEEP_RATIO})')
                        break
                offset += page_limit
                # update progress after successful page
                progress.setdefault('categories', {})[str(cid)] = offset
                save_progress(progress)
                time.sleep(delay)
            except Exception as e:
                logger.error(f'Error paging category {cid}: {e}')
                time.sleep(3)
                break
        if len(collected) >= max_items:
            break

    if not collected:
        print('No products collected')
        return

    # Translate name & descriptions (unless disabled)
    if not no_translate:
        to_translate = [r for r in collected if not r.get('_skip_translation')]
        skipped_count = len(collected) - len(to_translate)
        logger.info(f'Translating {len(to_translate)} products (Skipped {skipped_count} unchanged)...')
        
        if to_translate:
            from concurrent.futures import ThreadPoolExecutor
            
            def translate_chunk(chunk):
                try:
                    all_texts = []
                    for row in chunk:
                        all_texts.extend([
                            row.get('Name') or '',
                            row.get('ShortDescription') or '',
                            row.get('LongDescription') or '',
                            row.get('Category') or ''
                        ])
                    
                    translated_texts = translator.translate_batch(all_texts)
                    
                    idx = 0
                    for row in chunk:
                        row['TranslatedName'] = translated_texts[idx]
                        row['TranslatedShortDescription'] = translated_texts[idx+1]
                        row['TranslatedLongDescription'] = translated_texts[idx+2]
                        row['TranslatedCategory'] = translated_texts[idx+3]
                        idx += 4
                except Exception as exc:
                    logger.warning(f'Batch translation error: {exc}')
                return chunk

            # Chunk size for batching
            BATCH_SIZE = 20
            chunks = [to_translate[i:i + BATCH_SIZE] for i in range(0, len(to_translate), BATCH_SIZE)]
            
            # Increased workers for parallel batch processing
            with ThreadPoolExecutor(max_workers=20) as executor:
                 list(tqdm(executor.map(translate_chunk, chunks), total=len(chunks), desc="Translating Batches", unit="batch"))
             
            translator.save()
    else:
        logger.info('Skipping translation step (no_translate=True)')

    # Optional currency conversion HUF -> EUR
    convert_eur = bool(int(os.getenv('QUICK_CONVERT_EUR', '0')))
    eur_rate = None
    def get_eur_rate(from_currency: str = 'HUF'):
        nonlocal eur_rate
        if eur_rate is not None:
            return eur_rate
        # try Frankfurter API first (no key)
        try:
            resp = requests.get(f'https://api.frankfurter.app/latest?from={from_currency}&to=EUR', timeout=10)
            data = resp.json()
            if isinstance(data, dict) and 'rates' in data:
                r = data['rates'].get('EUR')
                if r:
                    eur_rate = float(r)
                    logger.info(f'Using Frankfurter HUF->EUR rate: {eur_rate}')
                    return eur_rate
        except Exception:
            pass
        # try exchangerate.host (supports optional key)
        try:
            access = os.getenv('EXCHANGE_ACCESS_KEY')
            url = f'https://api.exchangerate.host/latest?base={from_currency}&symbols=EUR'
            if access:
                url += f'&access_key={access}'
            resp = requests.get(url, timeout=10)
            data = resp.json()
            r = data.get('rates', {}).get('EUR')
            if r:
                eur_rate = float(r)
                logger.info(f'Using exchangerate.host HUF->EUR rate: {eur_rate}')
                return eur_rate
        except Exception:
            pass
        # fallback to env rate
        try:
            env_rate = os.getenv('QUICK_EUR_RATE')
            if env_rate:
                eur_rate = float(env_rate)
                logger.info(f'Using QUICK_EUR_RATE from env: {eur_rate}')
                return eur_rate
        except Exception:
            pass
        logger.warning('EUR conversion rate not available; EUR columns will be empty')
        return None

    def convert(amount):
        try:
            if amount is None or amount == '':
                return ''
            v = float(amount)
            rate = get_eur_rate('HUF')
            if not rate:
                return ''
            return round(v * rate, 2)
        except Exception:
            return ''

    # Backup existing CSV and write atomically
    keys = ['Id', 'Sku', 'EAN', 'State', 'Name', 'TranslatedName', 'ShortDescription', 'TranslatedShortDescription', 'LongDescription', 'TranslatedLongDescription', 'PriceNet', 'PriceGross', 'Category', 'TranslatedCategory', 'Url', 'ImageUrl', 'StockQty', 'Hash']
    if convert_eur:
        # insert EUR columns immediately BEFORE ImageUrl (Net then Gross)
        try:
            idx = keys.index('ImageUrl')
        except ValueError:
            idx = len(keys)
        keys.insert(idx, 'PriceNetEUR')
        keys.insert(idx + 1, 'PriceGrossEUR')
    if OUT_FILE.exists():
        bak = OUT_FILE.with_suffix(OUT_FILE.suffix + '.bak')
        shutil.copy2(OUT_FILE, bak)
        logger.info(f'Backed up existing CSV to {bak}')

    # atomic write: write to tmp then rename
    tmp_fd, tmp_path = tempfile.mkstemp(prefix=OUT_FILE.name, dir=str(OUT_FILE.parent))
    try:
        with os.fdopen(tmp_fd, 'w', newline='', encoding='utf-8') as fh:
            # Force quoting for all fields so URLs or commas do not merge columns
            writer = csv.DictWriter(fh, fieldnames=keys, quoting=csv.QUOTE_ALL)
            writer.writeheader()
            for r in collected:
                if convert_eur:
                    r['PriceNetEUR'] = convert(r.get('PriceNet'))
                    r['PriceGrossEUR'] = convert(r.get('PriceGross'))
                row = {k: r.get(k, '') for k in keys}
                writer.writerow(row)
        os.replace(tmp_path, OUT_FILE)
        logger.info(f'Wrote {len(collected)} rows to {OUT_FILE}')
    finally:
        try:
            if os.path.exists(tmp_path):
                os.remove(tmp_path)
        except Exception:
            pass


def _build_cli():
    p = argparse.ArgumentParser(description='Fetch products from UNAS and translate')
    p.add_argument('--max-items', type=int, default=DEFAULT_MAX, help='Maximum number of products to fetch')
    p.add_argument('--page-limit', type=int, default=PAGE_LIMIT, help='UNAS page limit')
    p.add_argument('--category-id', type=str, default=None, help='Only fetch products from this category id')
    p.add_argument('--product-id', type=str, default=None, help='Fetch a single product by Id (fast path, bypass paging)')
    p.add_argument('--delay', type=float, default=float(DELAY), help='Delay between pages (s)')
    p.add_argument('--no-translate', action='store_true', help='Skip translation step')
    p.add_argument('--resume', action='store_true', help='Resume from last progress file')
    p.add_argument('--convert-eur', action='store_true', help='Convert HUF prices to EUR and include EUR columns')
    p.add_argument('--log-level', default=os.getenv('LOG_LEVEL', 'INFO'))
    return p


if __name__ == '__main__':
    parser = _build_cli()
    args = parser.parse_args()
    logger.remove()
    logger.add(sys.stderr, level=args.log_level.upper(), format='<green>{time:YYYY-MM-DD HH:mm:ss}</green> | <level>{level: <8}</level> | <level>{message}</level>')
    # re-create client & translator in case ENV changed
    # (these were created at import time)
    try:
        # honor CLI flag or env QUICK_CONVERT_EUR
        if args.convert_eur:
            os.environ['QUICK_CONVERT_EUR'] = '1'
        run(max_items=args.max_items, page_limit=args.page_limit, category_id=args.category_id, delay=args.delay, resume=args.resume, no_translate=args.no_translate, product_id=args.product_id)
    except Exception as e:
        logger.exception(f'Fatal error during run: {e}')
        raise
