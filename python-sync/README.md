# UNAS → WooCommerce Product Sync (Python)

A Python implementation to fetch products from the UNAS XML API, translate content automatically, and sync them into WooCommerce via REST API.

## Features
- UNAS XML API client with header/body token auth modes
- Translation chain (Google, LibreTranslate, Glossary, Dictionary) with caching
- WooCommerce product creation with SKU existence check
- Modular mapping layer for UNAS → Woo fields
- Robust error handling & retry logic (tenacity)
- Environment-driven configuration (.env)
- Logging via loguru
- Basic unit tests (unittest) for auth logic and translation chain

## Project Structure
```
python-sync/
  src/
    unas/            # UNAS client & XML parsing
    wp/              # WooCommerce REST client
    translate/       # Translation engine & providers
    sync/            # Mapping + sync runner
  data/
    glossary.json    # Glossary terms
    cache/           # Translation cache (auto-generated)
  tests/             # Unittest modules
  requirements.txt
  .env.example
  README.md
```

## Setup
1. Copy `.env.example` → `.env` and fill in values.
2. Install dependencies:
```bash
pip install -r python-sync/requirements.txt
```
3. (Optional) Adjust `data/glossary.json` for exact term replacements.

## Environment Configuration
| Variable | Purpose |
|----------|---------|
| `UNAS_API_TOKEN` | API token for UNAS |
| `UNAS_API_BASE` | Base UNAS API URL |
| `UNAS_AUTH_MODE` | `body` or `header` |
| `UNAS_TOKEN_FIELD` | XML tag name when body auth |
| `UNAS_AUTH_HEADER_NAME` | Header name when header auth |
| `UNAS_AUTH_HEADER_PREFIX` | Optional header token prefix (e.g. `Bearer `) |
| `UNAS_AUTH_BODY_FIELD` | Override token XML field |
| `UNAS_LOGIN_ENDPOINT` | Endpoint for login (default `login`) |
| `UNAS_API_KEY` | API key used to obtain session token via login |
| `UNAS_LOGIN_WEBSHOPINFO` | Include webshop info in login response (`true/false`) |
| `UNAS_PRODUCTS_ENDPOINT` | Endpoint path for product retrieval (e.g. `getProduct`) |
| `UNAS_STOCK_ENDPOINT` | Endpoint path for stock retrieval (e.g. `getStock`) |
| `UNAS_CATEGORIES_ENDPOINT` | Endpoint path for categories retrieval (e.g. `getCategory`) |
| `UNAS_XML_ROOT` | Root XML element name (default `Request`) |
| `TRANSLATE_ENABLED` | Enable translation (`true/false`) |
| `TRANSLATE_SOURCE_LANG` | Source language code |
| `TRANSLATE_TARGET_LANG` | Target language code |
| `TRANSLATE_PROVIDER_ORDER` | Comma list of providers chain |
| `TRANSLATE_API_URL` | LibreTranslate base URL |
| `WP_BASE_URL` | WordPress base URL (no trailing slash) |
| `WP_CONSUMER_KEY` | WooCommerce consumer key |
| `WP_CONSUMER_SECRET` | WooCommerce consumer secret |
| `LOG_LEVEL` | Logging verbosity (INFO, DEBUG, etc.) |

## Running the Sync
Execute:
```bash
python python-sync/src/sync/sync_products.py
```
The script prints a summary: total, created, skipped, errors.

## Server Quickstart (Fetch + Translate CSV)
- Ensure `.env` is filled (UNAS creds, base URL, auth mode). Keep the fast defaults from `.env.example` for paging/yield guards and translation order.
- Make sure `python-sync/data/` is writable; the CSV and progress file are stored there.
- Install deps (`pip install -r python-sync/requirements.txt`) and activate the venv if you use one.
- Smoke test 20 items (fast path, resume-safe):
```bash
python python-sync/tools/fetch_and_translate_unas.py --max-items 20 --page-limit 50 --delay 0 --resume
```
- Full run (resume-friendly):
```bash
python python-sync/tools/fetch_and_translate_unas.py --max-items 1000 --page-limit 50 --delay 0 --resume
```
- Optional flags: `--convert-eur` to add EUR columns, `--category-id` to scope to one category, `--product-id` for a single item fast path, `--no-translate` to skip translation.

## Mapping Customization
Edit `src/sync/mapping.py` to adjust field mapping. Extend pricing, categories, images, attributes by reading additional UNAS response fields and adding to the WooCommerce payload.

## Translation Providers
Order is environment-driven; first provider to change text passes modified version to subsequent ones.
- `google`: Uses `googletrans` (best-effort, may fail silently)
- `libre`: LibreTranslate public/self-hosted endpoint
- `glossary`: Exact term replacement using `data/glossary.json`
- `dictionary`: Static Hungarian → Dutch fallbacks

Caching stored in `data/cache/translations.json` keyed by `source:target:text`.

## Troubleshooting UNAS Auth
- Header mode: ensure `UNAS_AUTH_HEADER_NAME` is set; include prefix via `UNAS_AUTH_HEADER_PREFIX` if required.
- Body mode: token inserted under `UNAS_AUTH_BODY_FIELD` (falls back to `UNAS_TOKEN_FIELD`). Inspect requests by temporarily logging XML or via test helper `build_request`.
- Errors with `<Error>` tag raise `UNASError` — add DEBUG logging to inspect raw responses.
- 400 Bad request with `<Error>` often means wrong endpoint name (set `UNAS_*_ENDPOINT` vars) or wrong XML root/tag.
- Authentication Error: empty Token → you likely skipped login. Ensure `UNAS_API_KEY` is set, leave token blank, client will call `login` to obtain `<Token>`.

## Error Handling & Retries
- Network and XML parse failures retried (up to 3 attempts with exponential backoff) in UNAS client.
- WooCommerce client raises `WooError` on HTTP ≥ 400 or invalid JSON.
- Translation providers fail soft and return original text.

## Tests
Run unit tests:
```bash
python -m unittest discover -s python-sync/tests -v
```
Tests cover:
- Auth header/body insertion
- Translation chain ordering + glossary/dictionary behaviors

## Roadmap
- Add product update (price, stock) rather than skip existing
- Support images and categories mapping
- Implement pagination for large UNAS datasets
- Add rate limiting & circuit breaker
- Include metrics/exporter for monitoring
- Expand dictionary & dynamic glossary editing
- Add CLI arguments (dry-run, limit, verbose)
- Implement structured logging (JSON) and rotating file handler

## Notes
- Actual UNAS XML structure may differ; adjust `map_unas_to_woo` and product list extraction logic accordingly.
- Google provider relies on unofficial API; for production consider official paid APIs.

## License
Internal use example (add license if required).
