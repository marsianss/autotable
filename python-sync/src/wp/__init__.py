"""WP package removed.

This module is a placeholder to avoid import errors. WooCommerce support has
been intentionally removed as part of the UNAS-only cleanup.
"""

raise ImportError("wp package removed — UNAS-only repository")
from .client import WooClient
__all__ = ["WooClient"]
