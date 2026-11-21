"""Unit tests for cloud.usable_api_base (no network)."""
import os
import sys
import unittest

ROOT = os.path.join(os.path.dirname(__file__), "..", "firmware")
sys.path.insert(0, os.path.abspath(ROOT))

import cloud  # noqa: E402


class UsableApiBaseTest(unittest.TestCase):
    def test_accepts_public_https(self):
        self.assertTrue(cloud.usable_api_base("https://www.rcdrift.ro"))
        self.assertTrue(cloud.usable_api_base("https://staging.rcdrift.ro/"))

    def test_rejects_loopback_private_path_and_http(self):
        self.assertFalse(cloud.usable_api_base("https://localhost"))
        self.assertFalse(cloud.usable_api_base("https://127.0.0.1"))
        self.assertFalse(cloud.usable_api_base("https://127.0.0.2"))
        self.assertFalse(cloud.usable_api_base("https://192.168.1.1"))
        self.assertFalse(cloud.usable_api_base("https://10.0.0.5"))
        self.assertFalse(cloud.usable_api_base("http://www.rcdrift.ro"))
        self.assertFalse(cloud.usable_api_base("https://www.rcdrift.ro:443"))
        self.assertFalse(cloud.usable_api_base("https://www.rcdrift.ro/proxy"))
        self.assertFalse(cloud.usable_api_base("https://www..rcdrift.ro"))
        self.assertFalse(cloud.usable_api_base(""))


if __name__ == "__main__":
    unittest.main()
