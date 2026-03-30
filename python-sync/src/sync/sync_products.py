"""Main product sync runner."""
from __future__ import annotations
import os
from dotenv import load_dotenv
from loguru import logger
from unas import UNASClient, UNASError
from wp import WooClient, WooError
from translate import TranslationManager
from .mapping import map_unas_to_woo

load_dotenv()


def run_sync() -> None:
    """Execute the UNAS → WooCommerce product synchronization."""
    level = os.getenv("LOG_LEVEL", "INFO")
    logger.remove()
    logger.add(lambda msg: print(msg, end=""), level=level.upper())

    unas_client = UNASClient.from_env()
    woo_client = WooClient.from_env()
    translator = TranslationManager()

    summary = {"total": 0, "created": 0, "skipped": 0, "errors": 0}

    try:
        products_resp = unas_client.get_products()
    except UNASError as exc:
        logger.error(f"Failed to fetch UNAS products: {exc}")
        return

    # Heuristic: find product list in response.
    raw_products = []
    for key in ["Products", "products", "ProductList"]:
        if key in products_resp:
            candidate = products_resp[key]
            if isinstance(candidate, dict) and "Product" in candidate:
                raw_products = candidate["Product"] if isinstance(candidate["Product"], list) else [candidate["Product"]]
            elif isinstance(candidate, list):
                raw_products = candidate
            break

    if not raw_products:
        logger.warning("No products found in UNAS response")
        return

    summary["total"] = len(raw_products)

    for p in raw_products:
        try:
            sku = str(p.get("SKU") or p.get("Id") or p.get("sku") or "")
            if not sku:
                logger.warning("Skipping product without SKU")
                summary["skipped"] += 1
                continue
            existing = woo_client.find_product_by_sku(sku)
            if existing:
                logger.info(f"Skip existing SKU {sku}")
                summary["skipped"] += 1
                continue
            woo_payload = map_unas_to_woo(p, translator.translate)
            created = woo_client.create_product(woo_payload)
            if created.get("id"):
                summary["created"] += 1
                logger.info(f"Created product {sku}")
            else:
                summary["errors"] += 1
                logger.error(f"Unknown creation result for {sku}")
        except (WooError, UNASError) as exc:
            summary["errors"] += 1
            logger.error(f"Error processing product: {exc}")
        except Exception as exc:  # noqa: BLE001
            summary["errors"] += 1
            logger.error(f"Unexpected error: {exc}")

    logger.info("\nSync Summary:")
    logger.info(f"Total: {summary['total']}")
    logger.info(f"Created: {summary['created']}")
    logger.info(f"Skipped: {summary['skipped']}")
    logger.info(f"Errors: {summary['errors']}")

if __name__ == "__main__":  # pragma: no cover
    run_sync()
