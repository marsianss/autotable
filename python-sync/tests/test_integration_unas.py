import os
import sys
import unittest
from dotenv import load_dotenv

# Ensure src in path
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '..', 'src')))

from unas.client import UNASClient, UNASError  # noqa: E402

class TestIntegrationUNAS(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        # Load env from project folder
        load_dotenv(os.path.join(os.path.dirname(__file__), '..', '.env'))

    def setUp(self):
        self.base = os.getenv('UNAS_API_BASE', '')
        self.token = os.getenv('UNAS_API_TOKEN', '')
        if not self.base or not self.token:
            self.skipTest('UNAS credentials missing; set UNAS_API_BASE and UNAS_API_TOKEN')

    def test_get_categories_smoke(self):
        client = UNASClient.from_env()
        # Build request for debug visibility
        req = client.build_request(client.categories_endpoint, {"Action": "GetCategories"})
        try:
            # Force login first to ensure token acquisition
            if not client.token:
                client._ensure_token()  # type: ignore[attr-defined]
            data = client.get_categories()
        except UNASError as exc:
            self.fail(
                "UNAS returned error: "
                f"{exc}\nEndpoint={client.categories_endpoint}\nXML Root={client.xml_root}\nSent XML (token masked):\n"
                + req["xml"].replace(os.getenv("UNAS_API_TOKEN", ""), "***")
            )
        self.assertIsInstance(data, dict)

if __name__ == '__main__':
    unittest.main()
