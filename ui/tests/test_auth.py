import os
import unittest
from unittest.mock import patch

from auth import OIDCAuthentication
from config import UIConfig


class OIDCAuthenticationTests(unittest.TestCase):
    def setUp(self):
        self.auth = OIDCAuthentication(frozenset({"owner@example.com"}))

    def test_verified_allowlisted_email_is_accepted_case_insensitively(self):
        self.assertTrue(
            self.auth.is_allowed(
                {"email": "Owner@Example.com", "email_verified": True}
            )
        )

    def test_unverified_or_unlisted_email_is_rejected(self):
        self.assertFalse(
            self.auth.is_allowed(
                {"email": "owner@example.com", "email_verified": False}
            )
        )
        self.assertFalse(
            self.auth.is_allowed(
                {"email": "intruder@example.com", "email_verified": True}
            )
        )


class UIAuthenticationConfigTests(unittest.TestCase):
    BASE = {
        "LUNALUMIA_API_URL": "http://backend:8000",
        "LUNALUMIA_API_TOKEN": "x" * 32,
        "LUNALUMIA_ALLOWED_EMAILS": " Owner@Example.com, second@example.com ",
    }

    def test_authentication_settings_are_normalized(self):
        with patch.dict(os.environ, self.BASE, clear=True):
            config = UIConfig.from_env()
        self.assertEqual(config.api_token, "x" * 32)
        self.assertEqual(
            config.allowed_emails,
            frozenset({"owner@example.com", "second@example.com"}),
        )

    def test_api_token_and_allowlist_are_required(self):
        with patch.dict(
            os.environ,
            {"LUNALUMIA_API_URL": "http://backend:8000", "LUNALUMIA_API_TOKEN": "short"},
            clear=True,
        ):
            with self.assertRaisesRegex(RuntimeError, "at least 32"):
                UIConfig.from_env()
        without_allowlist = dict(self.BASE)
        without_allowlist["LUNALUMIA_ALLOWED_EMAILS"] = ""
        with patch.dict(os.environ, without_allowlist, clear=True):
            with self.assertRaisesRegex(RuntimeError, "LUNALUMIA_ALLOWED_EMAILS"):
                UIConfig.from_env()


if __name__ == "__main__":
    unittest.main()
