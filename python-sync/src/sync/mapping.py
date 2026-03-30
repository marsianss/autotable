"""UNAS → WooCommerce field mapping utilities."""
from __future__ import annotations
from typing import Dict, Any

# This mapping is illustrative. Adjust according to actual UNAS structure.

def map_unas_to_woo(product: Dict[str, Any], translator) -> Dict[str, Any]:
    """Map a single UNAS product dict to WooCommerce product payload.

    Args:
        product: UNAS product dict.
        translator: TranslationManager.translate function.
    Returns:
        WooCommerce product dict suitable for creation.
    """
    name = product.get("Name") or product.get("name") or "Unnamed"
    description = product.get("Description") or product.get("description") or ""
    short_description = product.get("ShortDescription") or product.get("short_description") or ""

    woo: Dict[str, Any] = {
        "name": translator(name),
        "type": "simple",
        "regular_price": str(product.get("Price") or product.get("price") or "0"),
        "sku": str(product.get("SKU") or product.get("sku") or product.get("Id") or ""),
        "description": translator(description),
        "short_description": translator(short_description),
        "manage_stock": True,
        "stock_quantity": int(product.get("Stock", 0)),
    }
    return woo
