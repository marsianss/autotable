import os
import sys
import unittest

# Ensure src in path
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '..', 'src')))

from unas.client import UNASClient  # noqa: E402

class TestUNASAuth(unittest.TestCase):
    def test_body_auth_inserts_token_field(self):
        client = UNASClient(base_url="https://example.com", token="ABC123", auth_mode="body", body_field="Token")
        req = client.build_request("products", {"Action": "GetProducts"})
        self.assertIn("<Token>ABC123</Token>", req["xml"])
        self.assertNotIn("Authorization", req["headers"])  # default header name absent

    def test_header_auth_sets_header(self):
        client = UNASClient(base_url="https://example.com", token="ABC123", auth_mode="header", header_name="X-Auth")
        req = client.build_request("products", {"Action": "GetProducts"})
        self.assertIn("X-Auth", req["headers"])
        self.assertEqual(req["headers"]["X-Auth"], "ABC123")
        self.assertNotIn("<Token>ABC123</Token>", req["xml"])  # token not in body

    def test_header_prefix(self):
        client = UNASClient(base_url="https://example.com", token="ABC123", auth_mode="header", header_name="Authorization", header_prefix="Bearer ")
        req = client.build_request("products", {"Action": "GetProducts"})
        self.assertEqual(req["headers"]["Authorization"], "Bearer ABC123")

if __name__ == "__main__":
    unittest.main()
