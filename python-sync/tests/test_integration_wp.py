import os
import sys
import unittest
from dotenv import load_dotenv

# Ensure src in path
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '..', 'src')))

from wp.client import WooClient, WooError  # noqa: E402

class TestIntegrationWoo(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        # Load env from project folder
        load_dotenv(os.path.join(os.path.dirname(__file__), '..', '.env'))

    def setUp(self):
        self.base = os.getenv('WP_BASE_URL', '')
        self.key = os.getenv('WP_CONSUMER_KEY', '')
        self.secret = os.getenv('WP_CONSUMER_SECRET', '')
        if not (self.base and self.key and self.secret):
            self.skipTest('Woo credentials missing; set WP_BASE_URL, WP_CONSUMER_KEY, WP_CONSUMER_SECRET')

    def test_list_products_smoke(self):
        client = WooClient.from_env()
        try:
            # Read-only request; ensure endpoint/auth works
            products = client._request('GET', 'products?per_page=1')
        except WooError as exc:
            self.fail(f'WooCommerce returned error: {exc}')
        self.assertTrue(isinstance(products, list))

if __name__ == '__main__':
    unittest.main()
